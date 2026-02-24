"""Main application entry point — orchestrates all components.

Usage:
    python -m telegram_alpha_radar.app
    python -m telegram_alpha_radar.app --debug
    python -m telegram_alpha_radar.app --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from typing import Any

from telethon import events

from telegram_alpha_radar.config import AppConfig
from telegram_alpha_radar.core.models import HealthStatus
from telegram_alpha_radar.core.types import Chain, DetectorRegistry
from telegram_alpha_radar.core.utils import setup_logging, utcnow
from telegram_alpha_radar.detectors import EvmDetector, SolanaDetector
from telegram_alpha_radar.listener import TelegramListener
from telegram_alpha_radar.notifier import TelegramNotifier
from telegram_alpha_radar.storage import PostgresRepository
from telegram_alpha_radar.trending import TrendingEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional Prometheus metrics (graceful if library missing)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Gauge, start_http_server

    PROM_AVAILABLE = True
    MESSAGES_TOTAL = Counter(
        "radar_messages_total",
        "Total messages processed",
        ["chain"],
    )
    MENTIONS_TOTAL = Counter(
        "radar_mentions_total",
        "Total contract mentions recorded",
        ["chain"],
    )
    ALERTS_TOTAL = Counter(
        "radar_alerts_total",
        "Total alerts sent",
    )
    TRENDING_GAUGE = Gauge(
        "radar_trending_count",
        "Current number of trending tokens",
        ["chain"],
    )
except ImportError:
    PROM_AVAILABLE = False


class AlphaRadarApp:
    """Top-level orchestrator: wires listener -> detectors -> storage -> trending -> notifier."""

    def __init__(self, config: AppConfig, dry_run: bool = False) -> None:
        self._config = config
        self._dry_run = dry_run
        self._start_time = time.monotonic()

        # Components (initialized in start())
        self._repo = PostgresRepository(config.database)
        self._detectors: DetectorRegistry = [
            SolanaDetector(),
            EvmDetector(),
        ]
        self._listener: TelegramListener | None = None
        self._notifier: TelegramNotifier | None = None
        self._engine: TrendingEngine | None = None

        # Background tasks
        self._tasks: list[asyncio.Task[Any]] = []

        # Counters for health
        self._messages_processed = 0
        self._mentions_recorded = 0
        self._alerts_sent = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize all components and begin processing."""
        logger.info("Starting Alpha Radar (dry_run=%s)", self._dry_run)

        # 1. Database
        await self._repo.connect()

        # 2. Telegram listener
        self._listener = TelegramListener(
            config=self._config.telegram,
            filters=self._config.filters,
            on_message=self._on_message,
        )
        client = await self._listener.start()

        # 3. Notifier (needs the Telethon client)
        self._notifier = TelegramNotifier(
            client=client,
            config=self._config.trending,
            dry_run=self._dry_run,
        )

        # 4. Trending engine
        self._engine = TrendingEngine(
            repository=self._repo,
            trending_config=self._config.trending,
            dexscreener_config=self._config.dexscreener,
        )

        # 5. Prometheus metrics endpoint
        if PROM_AVAILABLE and self._config.metrics.enabled:
            start_http_server(self._config.metrics.port)
            logger.info(
                "Prometheus metrics on :%d/metrics",
                self._config.metrics.port,
            )

        # 6. Health check endpoint
        if self._config.health.enabled:
            self._tasks.append(
                asyncio.create_task(self._health_server(), name="health")
            )

        # 7. Background trending loop
        self._tasks.append(
            asyncio.create_task(self._trending_loop(), name="trending")
        )

        # 8. Periodic cleanup
        self._tasks.append(
            asyncio.create_task(self._cleanup_loop(), name="cleanup")
        )

        logger.info(
            "Alpha Radar fully started — %d detectors loaded: %s",
            len(self._detectors),
            ", ".join(d.chain_name for d in self._detectors),
        )

        # Block until disconnect
        await self._listener.run_until_disconnected()

    async def shutdown(self) -> None:
        """Graceful shutdown — cancel tasks, close connections."""
        logger.info("Shutting down Alpha Radar...")

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self._listener:
            await self._listener.stop()

        await self._repo.close()
        logger.info("Shutdown complete")

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        """Process a single incoming Telegram message through all detectors."""
        text = event.raw_text
        chat_id = event.chat_id
        message_id = event.message.id

        self._messages_processed += 1

        for detector in self._detectors:
            try:
                matches = await detector.detect(text, chat_id, message_id)
            except Exception:
                logger.exception(
                    "Detector %s failed on chat=%d msg=%d",
                    detector.chain_name,
                    chat_id,
                    message_id,
                )
                continue

            for match in matches:
                is_new = await self._repo.record_mention(match)
                if is_new:
                    self._mentions_recorded += 1
                    logger.info(
                        "New mention: %s [%s] in chat=%d",
                        match.contract[:12],
                        match.chain,
                        match.chat_id,
                    )
                    if PROM_AVAILABLE and self._config.metrics.enabled:
                        MENTIONS_TOTAL.labels(chain=match.chain).inc()

        if PROM_AVAILABLE and self._config.metrics.enabled:
            MESSAGES_TOTAL.labels(chain="all").inc()

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    async def _trending_loop(self) -> None:
        """Periodically detect trending tokens and send alerts."""
        assert self._engine is not None
        assert self._notifier is not None
        interval = self._config.trending.check_interval_seconds

        while True:
            try:
                await asyncio.sleep(interval)

                # Detect per-chain independently
                by_chain = await self._engine.detect_by_chain()

                for chain_name, tokens in by_chain.items():
                    if not tokens:
                        continue

                    sent = await self._notifier.notify(tokens)
                    self._alerts_sent += sent

                    if PROM_AVAILABLE and self._config.metrics.enabled:
                        ALERTS_TOTAL.inc(sent)
                        TRENDING_GAUGE.labels(chain=chain_name).set(
                            len(tokens)
                        )

                # Cleanup expired cooldowns
                self._notifier.cleanup_expired_cooldowns()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in trending loop")
                await asyncio.sleep(5)

    async def _cleanup_loop(self) -> None:
        """Periodically clean up old mentions to keep DB lean."""
        from datetime import timedelta

        while True:
            try:
                # Run every hour; delete mentions older than 24h
                await asyncio.sleep(3600)
                cutoff = utcnow() - timedelta(hours=24)
                await self._repo.cleanup_old_mentions(cutoff)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in cleanup loop")
                await asyncio.sleep(60)

    # ------------------------------------------------------------------
    # Health check HTTP server
    # ------------------------------------------------------------------

    async def _health_server(self) -> None:
        """Minimal HTTP health check endpoint on configured port."""
        import json

        from aiohttp import web

        async def handle_health(_request: web.Request) -> web.Response:
            status = await self._get_health()
            code = 200 if status.db_connected and status.telegram_connected else 503
            return web.json_response(
                {
                    "status": "ok" if code == 200 else "degraded",
                    "uptime_seconds": round(status.uptime_seconds, 1),
                    "messages_processed": status.messages_processed,
                    "mentions_recorded": status.mentions_recorded,
                    "alerts_sent": status.alerts_sent,
                    "db_connected": status.db_connected,
                    "telegram_connected": status.telegram_connected,
                    "detectors": status.detectors_loaded,
                },
                status=code,
            )

        app = web.Application()
        app.router.add_get("/health", handle_health)
        app.router.add_get("/", handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._config.health.port)
        await site.start()
        logger.info("Health endpoint on :%d/health", self._config.health.port)

        # Keep running until cancelled
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await runner.cleanup()

    async def _get_health(self) -> HealthStatus:
        db_ok = await self._repo.is_connected()
        tg_ok = (
            self._listener is not None
            and self._listener.client is not None
            and self._listener.client.is_connected()
        )
        return HealthStatus(
            uptime_seconds=time.monotonic() - self._start_time,
            messages_processed=self._messages_processed,
            mentions_recorded=self._mentions_recorded,
            alerts_sent=self._alerts_sent,
            db_connected=db_ok,
            telegram_connected=tg_ok,
            detectors_loaded=[d.chain_name for d in self._detectors],
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telegram Alpha Radar — multi-chain trending token monitor"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log alerts instead of sending them",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()

    config = AppConfig()

    # Override log level if --debug
    log_level = "DEBUG" if args.debug else config.log_level
    setup_logging(level=log_level, json_format=config.log_json)

    config.validate()

    app = AlphaRadarApp(config=config, dry_run=args.dry_run)

    # Graceful shutdown on SIGINT / SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))

    try:
        await app.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.shutdown()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
