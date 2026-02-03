"""Dev OSINT agent - researches developer/team background."""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.config import Settings
from src.constants import DEV_RED_FLAGS, ConfidenceLevel
from src.models import ContractAnalysis, DevProfile, TokenEvent

logger = logging.getLogger(__name__)


class DevOSINTAgent:
    """Researches developer/team OSINT data."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None
        self._twitter_client: Optional[httpx.AsyncClient] = None

        # Known scam wallets/devs database (load from file or DB)
        self._known_scammers: set[str] = set()

    async def initialize(self) -> None:
        """Initialize HTTP clients."""
        self._http_client = httpx.AsyncClient(timeout=30.0)

        if self.settings.twitter.bearer_token:
            self._twitter_client = httpx.AsyncClient(
                base_url="https://api.twitter.com/2",
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.settings.twitter.bearer_token}",
                },
            )

        logger.info("Dev OSINT agent initialized")

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._http_client:
            await self._http_client.aclose()
        if self._twitter_client:
            await self._twitter_client.aclose()

    async def research(
        self, event: TokenEvent, contract_analysis: Optional[ContractAnalysis] = None
    ) -> DevProfile:
        """Research developer background."""
        logger.info(f"Researching dev for: {event.token_address}")

        profile = DevProfile(
            token_address=event.token_address,
            analyzed_at=datetime.utcnow(),
        )

        try:
            # Extract Twitter handle from various sources
            twitter_handle = await self._find_twitter_handle(event, contract_analysis)

            if twitter_handle:
                profile.twitter_handle = twitter_handle
                profile.twitter_url = f"https://twitter.com/{twitter_handle}"

                # Get Twitter profile data
                twitter_data = await self._get_twitter_profile(twitter_handle)
                if twitter_data:
                    profile.twitter_followers = twitter_data.get("followers", 0)
                    profile.twitter_verified = twitter_data.get("verified", False)
                    profile.twitter_account_age_days = twitter_data.get("age_days", 0)
                    profile.twitter_engagement_rate = twitter_data.get(
                        "engagement_rate", 0.0
                    )

                    # Get real name if available
                    profile.real_name = twitter_data.get("name")

                # Get recent tweets
                profile.recent_tweets = await self._get_recent_tweets(twitter_handle)

                # Search for prior projects
                profile.prior_projects = await self._search_prior_projects(
                    twitter_handle, profile.real_name
                )

                # Check for red flags
                profile.red_flags = await self._check_red_flags(
                    twitter_handle, profile, contract_analysis
                )

                # Check reputation databases
                profile.reputation_score = await self._calculate_reputation(profile)

                # Check attribution verification
                profile.attribution_verified = await self._verify_attribution(
                    event.token_address, twitter_handle, contract_analysis
                )
                if profile.attribution_verified:
                    profile.attribution_method = "on-chain verification"

            # Determine if anonymous
            profile.is_anonymous = not twitter_handle or profile.twitter_followers < 100

            # Set confidence level
            if profile.attribution_verified:
                profile.confidence = ConfidenceLevel.VERIFIED
            elif twitter_handle and profile.twitter_followers > 1000:
                profile.confidence = ConfidenceLevel.HIGH
            elif twitter_handle:
                profile.confidence = ConfidenceLevel.MEDIUM
            else:
                profile.confidence = ConfidenceLevel.LOW

            logger.info(
                f"Dev research complete: @{twitter_handle or 'anonymous'}, "
                f"followers={profile.twitter_followers}, "
                f"red_flags={len(profile.red_flags)}"
            )

        except Exception as e:
            logger.error(f"Error researching dev: {e}")
            profile.confidence = ConfidenceLevel.UNVERIFIED

        return profile

    async def _find_twitter_handle(
        self, event: TokenEvent, contract_analysis: Optional[ContractAnalysis]
    ) -> Optional[str]:
        """Find Twitter handle from various sources."""
        # Check event metadata first (from Moltbook)
        metadata = event.source_metadata
        twitter = metadata.get("dev_twitter") or metadata.get("twitter")
        if twitter:
            # Clean handle
            handle = self._clean_twitter_handle(twitter)
            if handle:
                return handle

        # Try to find from token metadata on-chain (if stored)
        # This would require parsing contract storage or events

        # Try searching for token symbol + chain
        if event.token_symbol:
            handle = await self._search_twitter_for_token(event.token_symbol)
            if handle:
                return handle

        return None

    def _clean_twitter_handle(self, raw: str) -> Optional[str]:
        """Clean and validate Twitter handle."""
        if not raw:
            return None

        # Remove URL prefix
        raw = raw.strip()
        raw = re.sub(r"https?://(www\.)?(twitter|x)\.com/", "", raw)
        raw = raw.lstrip("@")
        raw = raw.split("/")[0]  # Remove any path suffix
        raw = raw.split("?")[0]  # Remove query params

        # Validate
        if re.match(r"^[A-Za-z0-9_]{1,15}$", raw):
            return raw

        return None

    async def _get_twitter_profile(self, handle: str) -> Optional[dict[str, Any]]:
        """Get Twitter profile information."""
        if not self._twitter_client:
            return None

        try:
            response = await self._twitter_client.get(
                f"/users/by/username/{handle}",
                params={
                    "user.fields": "created_at,description,name,public_metrics,"
                    "verified,verified_type,profile_image_url"
                },
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            if not data:
                return None

            # Parse creation date
            created_at = data.get("created_at")
            age_days = 0
            if created_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = (datetime.utcnow() - created.replace(tzinfo=None)).days
                except ValueError:
                    pass

            metrics = data.get("public_metrics", {})

            return {
                "name": data.get("name"),
                "handle": handle,
                "followers": metrics.get("followers_count", 0),
                "following": metrics.get("following_count", 0),
                "tweets": metrics.get("tweet_count", 0),
                "verified": data.get("verified", False),
                "verified_type": data.get("verified_type"),
                "age_days": age_days,
                "description": data.get("description"),
                "engagement_rate": self._calculate_engagement_rate(metrics),
            }

        except Exception as e:
            logger.error(f"Error getting Twitter profile for @{handle}: {e}")
            return None

    def _calculate_engagement_rate(self, metrics: dict) -> float:
        """Calculate estimated engagement rate."""
        followers = metrics.get("followers_count", 0)
        if followers == 0:
            return 0.0

        # Simple heuristic based on follower/following ratio
        following = metrics.get("following_count", 1)
        ratio = followers / max(following, 1)

        # Normalize to 0-1 scale
        return min(ratio / 10, 1.0)

    async def _get_recent_tweets(self, handle: str, count: int = 10) -> list[str]:
        """Get recent tweets from user."""
        if not self._twitter_client:
            return []

        try:
            # Get user ID first
            user_response = await self._twitter_client.get(
                f"/users/by/username/{handle}"
            )
            user_response.raise_for_status()
            user_id = user_response.json().get("data", {}).get("id")

            if not user_id:
                return []

            # Get tweets
            response = await self._twitter_client.get(
                f"/users/{user_id}/tweets",
                params={
                    "max_results": count,
                    "tweet.fields": "text,created_at",
                },
            )
            response.raise_for_status()
            tweets = response.json().get("data", [])

            return [t.get("text", "") for t in tweets]

        except Exception as e:
            logger.error(f"Error getting tweets for @{handle}: {e}")
            return []

    async def _search_twitter_for_token(self, symbol: str) -> Optional[str]:
        """Search Twitter for token mentions to find dev."""
        if not self._twitter_client:
            return None

        try:
            # Search for token symbol + common launch phrases
            response = await self._twitter_client.get(
                "/tweets/search/recent",
                params={
                    "query": f"${symbol} (launched OR deploying OR built) -is:retweet",
                    "max_results": 10,
                    "expansions": "author_id",
                    "user.fields": "username",
                },
            )
            response.raise_for_status()
            data = response.json()

            # Get first author with significant followers
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            for tweet in data.get("data", []):
                author_id = tweet.get("author_id")
                user = users.get(author_id, {})
                if user.get("username"):
                    return user["username"]

        except Exception as e:
            logger.debug(f"Twitter search failed: {e}")

        return None

    async def _search_prior_projects(
        self, handle: str, real_name: Optional[str]
    ) -> list[dict[str, Any]]:
        """Search for prior crypto projects by this dev."""
        projects = []

        # Search Google for prior projects
        search_queries = [
            f'"{handle}" crypto token',
            f'"{handle}" blockchain project',
        ]

        if real_name:
            search_queries.extend([
                f'"{real_name}" crypto',
                f'"{real_name}" blockchain',
            ])

        # Note: Would need SerpAPI or similar for Google search
        # This is a placeholder for the implementation
        logger.debug(f"Prior project search for @{handle} (not implemented)")

        return projects

    async def _check_red_flags(
        self,
        handle: str,
        profile: DevProfile,
        contract_analysis: Optional[ContractAnalysis],
    ) -> list[str]:
        """Check for red flags about the developer."""
        red_flags = []

        # Check account age
        if profile.twitter_account_age_days < 30:
            red_flags.append("Twitter account less than 30 days old")

        # Check followers
        if profile.twitter_followers < 100:
            red_flags.append("Very low follower count (<100)")

        # Check for known scammer
        if handle.lower() in self._known_scammers:
            red_flags.append("Known scammer/rugger")

        # Check deployer history if available
        if contract_analysis and contract_analysis.deployer_prior_tokens:
            # Would need to check if any prior tokens were rugs
            if len(contract_analysis.deployer_prior_tokens) > 5:
                red_flags.append(
                    f"Deployer has {len(contract_analysis.deployer_prior_tokens)} "
                    "prior token deployments"
                )

        # Check for fake followers indicators
        if profile.twitter_followers > 10000 and profile.twitter_engagement_rate < 0.01:
            red_flags.append("Possible fake followers (low engagement)")

        # Search for controversy mentions
        controversy_found = await self._search_controversy(handle)
        if controversy_found:
            red_flags.append("Controversy/scam mentions found")

        return red_flags

    async def _search_controversy(self, handle: str) -> bool:
        """Search for controversy mentions about the handle."""
        if not self._twitter_client:
            return False

        try:
            response = await self._twitter_client.get(
                "/tweets/search/recent",
                params={
                    "query": f"@{handle} (scam OR rug OR fraud OR fake)",
                    "max_results": 10,
                },
            )
            response.raise_for_status()
            data = response.json()

            tweets = data.get("data", [])
            return len(tweets) >= 3  # Multiple controversy mentions

        except Exception as e:
            logger.debug(f"Controversy search failed: {e}")
            return False

    async def _calculate_reputation(self, profile: DevProfile) -> float:
        """Calculate overall reputation score (0-100)."""
        score = 50.0  # Start neutral

        # Positive factors
        if profile.twitter_verified:
            score += 15
        if profile.twitter_account_age_days > 365:
            score += 10
        elif profile.twitter_account_age_days > 180:
            score += 5
        if profile.twitter_followers > 10000:
            score += 15
        elif profile.twitter_followers > 1000:
            score += 10
        elif profile.twitter_followers > 500:
            score += 5
        if profile.attribution_verified:
            score += 20
        if not profile.is_anonymous:
            score += 5

        # Negative factors
        for flag in profile.red_flags:
            if "scammer" in flag.lower():
                score -= 50
            elif "fake followers" in flag.lower():
                score -= 15
            elif "less than" in flag.lower():
                score -= 10
            else:
                score -= 5

        return max(0, min(100, score))

    async def _verify_attribution(
        self,
        token_address: str,
        twitter_handle: str,
        contract_analysis: Optional[ContractAnalysis],
    ) -> bool:
        """Verify on-chain attribution of Twitter to contract."""
        # Methods for verification:
        # 1. ENS name resolves to deployer and contains Twitter handle
        # 2. Contract metadata contains verified Twitter
        # 3. Signed message from deployer linking Twitter

        # This is a placeholder - would need implementation based on available data
        logger.debug(
            f"Attribution verification not implemented for @{twitter_handle}"
        )

        return False

    def add_known_scammer(self, identifier: str) -> None:
        """Add a known scammer to the database."""
        self._known_scammers.add(identifier.lower())

    def load_scammer_database(self, path: str) -> None:
        """Load known scammers from file."""
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._known_scammers.add(line.lower())
            logger.info(f"Loaded {len(self._known_scammers)} known scammers")
        except Exception as e:
            logger.error(f"Error loading scammer database: {e}")
