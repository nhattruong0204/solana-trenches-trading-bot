#!/usr/bin/env python3
"""Main application entry point for Telegram Alpha Radar.

Orchestrates all components:
  - Telegram listener (Telethon user client)
  - Contract parser
  - PostgreSQL storage
  - Trending detection loop
  - Notification system
  - Optional Prometheus metrics
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from telethon.tl.types import Message

from .config import AppConfig
from .parser import extract_contracts
from .storage import Storage
from .listener import TelegramListener
from .trending import detect_trending_tokens
from .notifier import Notifier

logger = logging.getLogger("alpha_radar")

# ---------------------------------------------------------------------------
# Optional Prometheus metrics (imported lazily to avoid hard dependency)
# ---------------------------------------------------------------------------
_prom_messages_total = None
_prom_contracts_total = None
_prom_alerts_total = None
_prom_trending_gauge = None


def _setup_metrics(port: int) -> None:
    """Start Prometheus metrics HTTP server if the library is available."""
    global _prom_messages_total, _prom_contracts_total, _prom_alerts_total, _prom_trending_gauge
    try:
        from prometheus_client import Counter, Gauge, start_http_server

        _prom_messages_total = Counter(
            "alpha_radar_messages_total", "Total messages processed"
        )
        _prom_contracts_total = Counter(
            "alpha_radar_contracts_total",
            "Total contract mentions recorded",
            ["chain"],
        )
        _prom_alerts_total = Counter(
            "alpha_radar_alerts_total", "Total alerts sent"
        )
        _prom_trending_gauge = Gauge(
            "alpha_radar_trending_tokens", "Number of currently trending tokens"
        )
        start_http_server(port)
        logger.info("Prometheus metrics server started on port %d", port)
    except ImportError:
        logger.warning(
            "prometheus_client not installed — metrics endpoint disabled"
        )


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(level: str, debug: bool) -> None:
    effective_level = "DEBUG" if debug else level.upper()
    logging.basicConfig(
        level=effective_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Silence noisy third-party loggers
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logger.info("Log level set to %s", effective_level)


# ---------------------------------------------------------------------------
# Core application
# ---------------------------------------------------------------------------

class AlphaRadarApp:
    """Main application orchestrator."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.storage = Storage(config.database)
        self.listener: TelegramListener | None = None
        self.notifier: Notifier | None = None
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def _on_message(self, msg: Message) -> None:
        """Callback invoked for every incoming Telegram message."""
        if _prom_messages_total:
            _prom_messages_total.inc()

        contracts = extract_contracts(msg.text)
        if not contracts:
            return

        chat_id = msg.chat_id or 0
        message_id = msg.id
        ts = msg.date or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        for c in contracts:
            await self.storage.record_mention(
                contract=c.address,
                chain=c.chain,
                chat_id=chat_id,
                message_id=message_id,
                mentioned_at=ts,
            )
            if _prom_contracts_total:
                _prom_contracts_total.labels(chain=c.chain).inc()

        logger.info(
            "Processed msg %s from chat %s — %d contract(s)",
            message_id,
            chat_id,
            len(contracts),
        )

    async def _trending_loop(self) -> None:
        """Periodically check for trending tokens and send alerts."""
        interval = self.config.trending.check_interval_seconds
        logger.info("Trending detection loop started (interval=%ds)", interval)

        while not self._shutdown_event.is_set():
            try:
                tokens = await detect_trending_tokens(
                    storage=self.storage,
                    trending_config=self.config.trending,
                    dex_config=(
                        self.config.dexscreener
                        if self.config.dexscreener.enabled
                        else None
                    ),
                )

                if _prom_trending_gauge:
                    _prom_trending_gauge.set(len(tokens))

                if tokens and self.notifier:
                    sent = await self.notifier.notify(tokens)
                    if _prom_alerts_total and sent:
                        _prom_alerts_total.inc(sent)

                # Periodic cooldown cleanup
                if self.notifier:
                    self.notifier.cleanup_expired_cooldowns()

            except Exception:
                logger.exception("Error in trending detection loop")

            # Sleep in small increments so we can respond to shutdown quickly
            for _ in range(interval):
                if self._shutdown_event.is_set():
                    break
                await asyncio.sleep(1)

        logger.info("Trending detection loop stopped")

    async def start(self) -> None:
        """Initialize all components and run."""
        _setup_logging(self.config.log_level, self.config.debug)
        self.config.validate()

        # Metrics
        if self.config.metrics.enabled:
            _setup_metrics(self.config.metrics.port)

        # Storage
        await self.storage.connect()

        # Listener
        self.listener = TelegramListener(
            config=self.config.telegram,
            filters=self.config.filters,
            on_message=self._on_message,
        )
        await self.listener.start()

        # Notifier (reuse the Telethon client)
        assert self.listener._client is not None
        self.notifier = Notifier(self.listener._client, self.config.trending)

        # Background trending loop
        trending_task = asyncio.create_task(self._trending_loop())
        self._tasks.append(trending_task)

        logger.info("Alpha Radar is fully operational")

        # Block until client disconnects or shutdown signal
        await self.listener.run_until_disconnected()

    async def shutdown(self) -> None:
        """Gracefully stop all components."""
        logger.info("Shutting down Alpha Radar…")
        self._shutdown_event.set()

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.listener:
            await self.listener.stop()
        await self.storage.close()
        logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telegram Alpha Radar — trending token detection"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging (overrides LOG_LEVEL env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig()
    if args.debug:
        config.debug = True

    app = AlphaRadarApp(config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Graceful shutdown on SIGINT / SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: loop.create_task(app.shutdown()))

    try:
        loop.run_until_complete(app.start())
    except (KeyboardInterrupt, SystemExit):
        loop.run_until_complete(app.shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
