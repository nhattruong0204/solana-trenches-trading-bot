"""Moltbook detector - polls Moltbook API for new agent deployments."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Optional

import httpx

from src.config import Settings
from src.models import EventSource, TokenEvent

logger = logging.getLogger(__name__)


class MoltbookDetector:
    """Detects new tokens from Moltbook platform."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._running = False
        self._callbacks: list[Callable[[TokenEvent], asyncio.Future]] = []
        self._seen_tokens: set[str] = set()
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Initialize HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "TokenAnalysisBot/1.0",
                "Accept": "application/json",
            },
        )
        logger.info(f"Moltbook detector initialized: {self.settings.moltbook.api_url}")

    async def disconnect(self) -> None:
        """Close HTTP client."""
        self._running = False
        if self._client:
            await self._client.aclose()
        logger.info("Moltbook detector disconnected")

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

    async def _fetch_agents(self, page: int = 1, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch agents from Moltbook API."""
        if not self._client:
            await self.connect()

        try:
            # Adjust endpoint based on actual Moltbook API structure
            response = await self._client.get(
                f"{self.settings.moltbook.api_url}/agents",
                params={"page": page, "limit": limit, "sort": "created_desc"},
            )
            response.raise_for_status()

            data = response.json()

            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "agents" in data:
                return data["agents"]
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            else:
                logger.warning(f"Unexpected Moltbook response format: {type(data)}")
                return []

        except httpx.HTTPError as e:
            logger.error(f"Moltbook API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching Moltbook agents: {e}")
            return []

    def _parse_agent_to_event(self, agent: dict[str, Any]) -> Optional[TokenEvent]:
        """Parse a Moltbook agent entry to a TokenEvent."""
        try:
            # Extract token address - adjust field names based on actual API
            token_address = (
                agent.get("contract_address")
                or agent.get("token_address")
                or agent.get("address")
            )

            if not token_address:
                logger.debug(f"No token address in agent: {agent.get('id', 'unknown')}")
                return None

            # Normalize address
            token_address = token_address.strip()
            if not token_address.startswith("0x"):
                token_address = f"0x{token_address}"

            # Check if already seen
            if token_address.lower() in self._seen_tokens:
                return None
            self._seen_tokens.add(token_address.lower())

            # Extract metadata
            symbol = agent.get("symbol") or agent.get("ticker")
            name = agent.get("name")
            dev_twitter = agent.get("twitter") or agent.get("dev_twitter")
            created_at = agent.get("created_at") or agent.get("deployed_at")

            # Parse timestamp
            if created_at:
                if isinstance(created_at, str):
                    try:
                        detected_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except ValueError:
                        detected_at = datetime.utcnow()
                elif isinstance(created_at, (int, float)):
                    detected_at = datetime.fromtimestamp(created_at)
                else:
                    detected_at = datetime.utcnow()
            else:
                detected_at = datetime.utcnow()

            logger.info(f"New Moltbook agent detected: {symbol or 'UNKNOWN'} ({token_address})")

            return TokenEvent(
                token_address=token_address,
                pair_address=agent.get("pair_address"),
                source=EventSource.MOLTBOOK,
                detected_at=detected_at,
                chain_id=8453,  # Base mainnet
                token_symbol=symbol,
                token_name=name,
                source_metadata={
                    "moltbook_id": agent.get("id"),
                    "dev_twitter": dev_twitter,
                    "description": agent.get("description"),
                    "website": agent.get("website"),
                    "telegram": agent.get("telegram"),
                    "image_url": agent.get("image") or agent.get("logo"),
                    "agent_type": agent.get("type"),
                    "tags": agent.get("tags", []),
                },
            )

        except Exception as e:
            logger.error(f"Error parsing Moltbook agent: {e}")
            return None

    async def poll_once(self) -> list[TokenEvent]:
        """Poll Moltbook API once and return new events."""
        events: list[TokenEvent] = []

        agents = await self._fetch_agents()
        for agent in agents:
            event = self._parse_agent_to_event(agent)
            if event:
                events.append(event)

        return events

    async def start_polling(self) -> None:
        """Start continuous polling of Moltbook API."""
        if not self._client:
            await self.connect()

        self._running = True
        poll_interval = self.settings.moltbook.poll_interval_seconds

        logger.info(f"Starting Moltbook poller (interval: {poll_interval}s)")

        while self._running:
            try:
                events = await self.poll_once()

                for event in events:
                    await self._notify_callbacks(event)

                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error in Moltbook polling loop: {e}")
                await asyncio.sleep(poll_interval)

    async def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
        logger.info("Stopped Moltbook poller")

    async def get_agent_details(self, agent_id: str) -> Optional[dict[str, Any]]:
        """Get detailed information about a specific agent."""
        if not self._client:
            await self.connect()

        try:
            response = await self._client.get(
                f"{self.settings.moltbook.api_url}/agents/{agent_id}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching agent details for {agent_id}: {e}")
            return None
