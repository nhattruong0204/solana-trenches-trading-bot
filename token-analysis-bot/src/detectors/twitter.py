"""Twitter/X detector - monitors for new token mentions and dev activity."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable, Optional

import httpx

from src.config import Settings
from src.models import EventSource, TokenEvent

logger = logging.getLogger(__name__)


# Regex patterns for token addresses
BASE_ADDRESS_PATTERN = re.compile(r"0x[a-fA-F0-9]{40}")
TOKEN_MENTION_PATTERN = re.compile(r"\$([A-Z]{2,10})\b")


class TwitterDetector:
    """Detects new tokens from Twitter/X mentions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._running = False
        self._callbacks: list[Callable[[TokenEvent], asyncio.Future]] = []
        self._seen_addresses: set[str] = set()
        self._client: Optional[httpx.AsyncClient] = None

        # Accounts to monitor (add more as needed)
        self.monitored_accounts = [
            "moltbook",
            "moltbook_ai",
            # Add known devs, KOLs, etc.
        ]

        # Keywords to search
        self.search_keywords = [
            "$MOLT",
            "moltbook",
            "launched on base",
            "new token base chain",
        ]

    async def connect(self) -> None:
        """Initialize Twitter API client."""
        if not self.settings.twitter.bearer_token:
            logger.warning("Twitter bearer token not configured")
            return

        self._client = httpx.AsyncClient(
            base_url="https://api.twitter.com/2",
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.settings.twitter.bearer_token}",
                "User-Agent": "TokenAnalysisBot/1.0",
            },
        )
        logger.info("Twitter detector initialized")

    async def disconnect(self) -> None:
        """Close HTTP client."""
        self._running = False
        if self._client:
            await self._client.aclose()
        logger.info("Twitter detector disconnected")

    def register_callback(self, callback: Callable[[TokenEvent], asyncio.Future]) -> None:
        """Register callback for new token events."""
        self._callbacks.append(callback)

    async def _notify_callbacks(self, event: TokenEvent) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    async def _search_recent_tweets(self, query: str, max_results: int = 10) -> list[dict]:
        """Search recent tweets using Twitter API v2."""
        if not self._client:
            return []

        try:
            response = await self._client.get(
                "/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": max_results,
                    "tweet.fields": "created_at,author_id,text,entities",
                    "expansions": "author_id",
                    "user.fields": "username,name,verified,public_metrics",
                },
            )
            response.raise_for_status()
            data = response.json()

            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

            # Attach user info to tweets
            for tweet in tweets:
                tweet["user"] = users.get(tweet.get("author_id", ""))

            return tweets

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Twitter rate limit hit, backing off...")
            else:
                logger.error(f"Twitter API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error searching tweets: {e}")
            return []

    async def _get_user_timeline(
        self, username: str, max_results: int = 10
    ) -> list[dict]:
        """Get recent tweets from a specific user."""
        if not self._client:
            return []

        try:
            # First get user ID
            user_response = await self._client.get(
                f"/users/by/username/{username}"
            )
            user_response.raise_for_status()
            user_data = user_response.json()
            user_id = user_data.get("data", {}).get("id")

            if not user_id:
                return []

            # Get timeline
            response = await self._client.get(
                f"/users/{user_id}/tweets",
                params={
                    "max_results": max_results,
                    "tweet.fields": "created_at,text,entities",
                },
            )
            response.raise_for_status()
            return response.json().get("data", [])

        except Exception as e:
            logger.error(f"Error fetching timeline for @{username}: {e}")
            return []

    def _extract_token_from_tweet(self, tweet: dict) -> Optional[TokenEvent]:
        """Extract token information from a tweet."""
        text = tweet.get("text", "")

        # Look for Base chain addresses
        addresses = BASE_ADDRESS_PATTERN.findall(text)
        if not addresses:
            return None

        # Use first address found
        token_address = addresses[0]

        # Check if already seen
        if token_address.lower() in self._seen_addresses:
            return None
        self._seen_addresses.add(token_address.lower())

        # Extract symbol if mentioned
        symbol_match = TOKEN_MENTION_PATTERN.search(text)
        symbol = symbol_match.group(1) if symbol_match else None

        # Parse timestamp
        created_at = tweet.get("created_at")
        if created_at:
            try:
                detected_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                detected_at = datetime.utcnow()
        else:
            detected_at = datetime.utcnow()

        # Get user info
        user = tweet.get("user", {})
        username = user.get("username", "unknown")

        logger.info(
            f"New token from Twitter @{username}: {symbol or 'UNKNOWN'} ({token_address})"
        )

        return TokenEvent(
            token_address=token_address,
            pair_address=None,
            source=EventSource.TWITTER,
            detected_at=detected_at,
            chain_id=8453,
            token_symbol=symbol,
            source_metadata={
                "tweet_id": tweet.get("id"),
                "tweet_text": text,
                "author_username": username,
                "author_name": user.get("name"),
                "author_verified": user.get("verified", False),
                "author_followers": user.get("public_metrics", {}).get(
                    "followers_count", 0
                ),
            },
        )

    async def poll_once(self) -> list[TokenEvent]:
        """Poll Twitter once and return new events."""
        events: list[TokenEvent] = []

        # Search for keywords
        for keyword in self.search_keywords:
            tweets = await self._search_recent_tweets(f"{keyword} -is:retweet")
            for tweet in tweets:
                event = self._extract_token_from_tweet(tweet)
                if event:
                    events.append(event)

            # Rate limit between searches
            await asyncio.sleep(1)

        # Monitor specific accounts
        for account in self.monitored_accounts:
            tweets = await self._get_user_timeline(account)
            for tweet in tweets:
                event = self._extract_token_from_tweet(tweet)
                if event:
                    events.append(event)

            await asyncio.sleep(1)

        return events

    async def start_polling(self, interval_seconds: int = 60) -> None:
        """Start continuous polling of Twitter."""
        if not self._client:
            await self.connect()

        if not self._client:
            logger.warning("Twitter client not available, skipping polling")
            return

        self._running = True
        logger.info(f"Starting Twitter poller (interval: {interval_seconds}s)")

        while self._running:
            try:
                events = await self.poll_once()

                for event in events:
                    await self._notify_callbacks(event)

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.error(f"Error in Twitter polling loop: {e}")
                await asyncio.sleep(interval_seconds)

    async def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("Stopped Twitter poller")

    async def get_user_profile(self, username: str) -> Optional[dict[str, Any]]:
        """Get user profile information."""
        if not self._client:
            return None

        try:
            response = await self._client.get(
                f"/users/by/username/{username}",
                params={
                    "user.fields": "created_at,description,location,name,pinned_tweet_id,"
                    "profile_image_url,public_metrics,url,verified"
                },
            )
            response.raise_for_status()
            return response.json().get("data")
        except Exception as e:
            logger.error(f"Error fetching profile for @{username}: {e}")
            return None

    async def get_user_tweets(
        self, username: str, max_results: int = 100
    ) -> list[dict]:
        """Get user's recent tweets for analysis."""
        if not self._client:
            return []

        try:
            # Get user ID
            user_response = await self._client.get(
                f"/users/by/username/{username}"
            )
            user_response.raise_for_status()
            user_id = user_response.json().get("data", {}).get("id")

            if not user_id:
                return []

            # Get tweets with pagination
            all_tweets = []
            pagination_token = None

            while len(all_tweets) < max_results:
                params = {
                    "max_results": min(100, max_results - len(all_tweets)),
                    "tweet.fields": "created_at,text,public_metrics",
                }
                if pagination_token:
                    params["pagination_token"] = pagination_token

                response = await self._client.get(
                    f"/users/{user_id}/tweets", params=params
                )
                response.raise_for_status()
                data = response.json()

                tweets = data.get("data", [])
                all_tweets.extend(tweets)

                pagination_token = data.get("meta", {}).get("next_token")
                if not pagination_token:
                    break

                await asyncio.sleep(1)  # Rate limiting

            return all_tweets

        except Exception as e:
            logger.error(f"Error fetching tweets for @{username}: {e}")
            return []
