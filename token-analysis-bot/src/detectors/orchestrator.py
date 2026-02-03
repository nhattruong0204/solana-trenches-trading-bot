"""Detector orchestrator - coordinates all event detection sources."""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from src.config import Settings
from src.detectors.base_chain import BaseChainDetector
from src.detectors.moltbook import MoltbookDetector
from src.detectors.twitter import TwitterDetector
from src.models import TokenEvent

logger = logging.getLogger(__name__)


class DetectorOrchestrator:
    """Orchestrates all token detection sources."""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Initialize detectors
        self.chain_detector = BaseChainDetector(settings)
        self.moltbook_detector = MoltbookDetector(settings)
        self.twitter_detector = TwitterDetector(settings)

        # Unified event queue
        self._event_queue: asyncio.Queue[TokenEvent] = asyncio.Queue()
        self._callbacks: list[Callable[[TokenEvent], asyncio.Future]] = []

        # Deduplication across sources
        self._seen_tokens: dict[str, TokenEvent] = {}  # address -> first event
        self._dedup_window_seconds = 300  # 5 minutes

        # Tasks
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start all detectors."""
        logger.info("Starting detector orchestrator...")
        self._running = True

        # Register internal callback for all detectors
        self.chain_detector.register_callback(self._on_event)
        self.moltbook_detector.register_callback(self._on_event)
        self.twitter_detector.register_callback(self._on_event)

        # Connect to sources
        await self.chain_detector.connect()
        await self.moltbook_detector.connect()
        await self.twitter_detector.connect()

        # Start detector tasks
        self._tasks = [
            asyncio.create_task(self.chain_detector.start_listening()),
            asyncio.create_task(self.moltbook_detector.start_polling()),
            asyncio.create_task(self.twitter_detector.start_polling()),
            asyncio.create_task(self._process_queue()),
            asyncio.create_task(self._cleanup_dedup_cache()),
        ]

        logger.info("All detectors started")

    async def stop(self) -> None:
        """Stop all detectors."""
        logger.info("Stopping detector orchestrator...")
        self._running = False

        # Stop detectors
        await self.chain_detector.stop_listening()
        await self.moltbook_detector.stop_polling()
        await self.twitter_detector.stop_polling()

        # Cancel tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Disconnect
        await self.chain_detector.disconnect()
        await self.moltbook_detector.disconnect()
        await self.twitter_detector.disconnect()

        logger.info("Detector orchestrator stopped")

    def register_callback(self, callback: Callable[[TokenEvent], asyncio.Future]) -> None:
        """Register callback for deduplicated token events."""
        self._callbacks.append(callback)

    async def _on_event(self, event: TokenEvent) -> None:
        """Handle event from any detector."""
        await self._event_queue.put(event)

    async def _process_queue(self) -> None:
        """Process events from the queue with deduplication."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )

                # Deduplicate
                token_key = event.token_address.lower()
                existing = self._seen_tokens.get(token_key)

                if existing:
                    # Merge metadata if from different source
                    if existing.source != event.source:
                        logger.debug(
                            f"Token {event.token_address} also seen from {event.source.value}"
                        )
                        # Could merge metadata here if needed
                    continue

                # New token - record and notify
                self._seen_tokens[token_key] = event
                logger.info(
                    f"New unique token: {event.token_symbol or 'UNKNOWN'} "
                    f"({event.token_address}) from {event.source.value}"
                )

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        await callback(event)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing event queue: {e}")

    async def _cleanup_dedup_cache(self) -> None:
        """Periodically clean up old entries from dedup cache."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Run every minute

                now = datetime.utcnow()
                cutoff = now.timestamp() - self._dedup_window_seconds

                # Remove old entries
                to_remove = []
                for address, event in self._seen_tokens.items():
                    if event.detected_at.timestamp() < cutoff:
                        to_remove.append(address)

                for address in to_remove:
                    del self._seen_tokens[address]

                if to_remove:
                    logger.debug(f"Cleaned up {len(to_remove)} old tokens from dedup cache")

            except Exception as e:
                logger.error(f"Error cleaning dedup cache: {e}")

    async def submit_manual_token(
        self, token_address: str, metadata: Optional[dict] = None
    ) -> TokenEvent:
        """Manually submit a token for analysis."""
        from src.models import EventSource

        event = TokenEvent(
            token_address=token_address,
            pair_address=None,
            source=EventSource.MANUAL,
            detected_at=datetime.utcnow(),
            chain_id=self.settings.chain.chain_id,
            source_metadata=metadata or {},
        )

        await self._event_queue.put(event)
        logger.info(f"Manual token submitted: {token_address}")
        return event

    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "running": self._running,
            "unique_tokens_seen": len(self._seen_tokens),
            "queue_size": self._event_queue.qsize(),
            "active_tasks": len([t for t in self._tasks if not t.done()]),
        }
