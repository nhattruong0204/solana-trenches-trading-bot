"""Main orchestrator - coordinates all components."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

from src.config import Settings, get_settings
from src.db.repository import AnalysisRepository
from src.delivery.telegram_bot import TelegramDeliveryBot
from src.detectors.orchestrator import DetectorOrchestrator
from src.enrichment.pipeline import EnrichmentPipeline
from src.models import AnalysisJob, AnalysisStatus, TokenBreakdown, TokenEvent
from src.synthesis.synthesizer import TokenSynthesizer
from src.utils.helpers import generate_job_id

logger = logging.getLogger(__name__)


class TokenAnalysisOrchestrator:
    """Main orchestrator that coordinates all analysis components."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

        # Initialize components
        self.detector = DetectorOrchestrator(self.settings)
        self.enrichment = EnrichmentPipeline(self.settings)
        self.synthesizer = TokenSynthesizer(self.settings)
        self.delivery = TelegramDeliveryBot(self.settings)
        self.repository = AnalysisRepository(self.settings)

        # Processing state
        self._running = False
        self._processing_queue: asyncio.Queue[TokenEvent] = asyncio.Queue()
        self._active_jobs: dict[str, AnalysisJob] = {}
        self._tasks: list[asyncio.Task] = []

        # Statistics
        self._stats = {
            "total_detected": 0,
            "total_analyzed": 0,
            "total_published": 0,
            "total_failed": 0,
        }

    async def start(self) -> None:
        """Start the orchestrator and all components."""
        logger.info("Starting Token Analysis Orchestrator...")

        try:
            # Initialize all components
            await self.repository.initialize()
            await self.enrichment.initialize()
            await self.synthesizer.initialize()
            await self.delivery.initialize()

            # Register detector callback
            self.detector.register_callback(self._on_token_detected)

            # Start components
            await self.detector.start()
            await self.delivery.start()

            # Start processing workers
            self._running = True
            self._tasks = [
                asyncio.create_task(self._process_queue_worker()),
                asyncio.create_task(self._stats_reporter()),
            ]

            logger.info("Token Analysis Orchestrator started successfully")

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the orchestrator and all components."""
        logger.info("Stopping Token Analysis Orchestrator...")
        self._running = False

        # Cancel worker tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop components
        await self.detector.stop()
        await self.delivery.stop()
        await self.synthesizer.close()
        await self.enrichment.close()
        await self.repository.close()

        logger.info("Token Analysis Orchestrator stopped")

    async def _on_token_detected(self, event: TokenEvent) -> None:
        """Handle new token detection event."""
        self._stats["total_detected"] += 1
        logger.info(
            f"Token detected: {event.token_symbol or 'UNKNOWN'} "
            f"({event.token_address}) from {event.source.value}"
        )

        # Check if already analyzed recently
        if await self.repository.is_token_analyzed(event.token_address):
            logger.debug(f"Token {event.token_address} already analyzed recently, skipping")
            return

        # Check blacklist
        blacklist_entry = await self.repository.is_blacklisted(event.token_address)
        if blacklist_entry:
            logger.warning(
                f"Token {event.token_address} is blacklisted: {blacklist_entry.get('reason')}"
            )
            return

        # Add to processing queue
        await self._processing_queue.put(event)

    async def _process_queue_worker(self) -> None:
        """Worker that processes tokens from the queue."""
        while self._running:
            try:
                # Get next event with timeout
                event = await asyncio.wait_for(
                    self._processing_queue.get(), timeout=1.0
                )

                # Process the token
                await self._analyze_token(event)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue worker: {e}")

    async def _analyze_token(self, event: TokenEvent) -> Optional[TokenBreakdown]:
        """Run full analysis pipeline on a token."""
        job_id = generate_job_id(event.token_address)

        job = AnalysisJob(
            job_id=job_id,
            token_address=event.token_address,
            status=AnalysisStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            event=event,
        )

        self._active_jobs[job_id] = job

        try:
            logger.info(f"Starting analysis for {event.token_address} (job: {job_id})")

            # Step 1: Quick enrichment to check if we should continue
            contract, _, metrics = await self.enrichment.enrich_fast(event)

            # Check if token meets minimum criteria
            should_skip, reason = await self.enrichment.should_skip_token(event, metrics)
            if should_skip:
                logger.info(f"Skipping {event.token_address}: {reason}")
                job.status = AnalysisStatus.REJECTED
                job.error_message = reason
                await self.repository.save_analysis(job)
                return None

            # Step 2: Full enrichment
            contract, dev_profile, metrics = await self.enrichment.enrich(event, job)

            # Step 3: Synthesis
            breakdown = await self.synthesizer.synthesize(
                contract, dev_profile, metrics, job
            )

            # Step 4: Refresh metrics before publishing
            metrics = await self.enrichment.refresh_before_publish(job)

            # Update breakdown with fresh metrics
            breakdown.fdv_usd = metrics.fdv_usd
            breakdown.fdv_display = format_fdv(metrics.fdv_usd)
            breakdown.on_chain_metrics = metrics

            # Step 5: Publish
            message_id = await self.delivery.publish_breakdown(breakdown, job)

            if message_id:
                self._stats["total_published"] += 1
                logger.info(
                    f"Analysis complete for ${breakdown.symbol}: "
                    f"{breakdown.risk_rating.value} rating"
                )
            else:
                logger.warning(f"Analysis complete but not published for {event.token_address}")

            # Save to database
            await self.repository.save_analysis(job)

            self._stats["total_analyzed"] += 1
            return breakdown

        except Exception as e:
            logger.error(f"Analysis failed for {event.token_address}: {e}")
            job.status = AnalysisStatus.FAILED
            job.error_message = str(e)
            await self.repository.save_analysis(job)
            self._stats["total_failed"] += 1
            return None

        finally:
            self._active_jobs.pop(job_id, None)

    async def analyze_manual(self, token_address: str) -> Optional[TokenBreakdown]:
        """Manually submit a token for analysis."""
        event = await self.detector.submit_manual_token(token_address)
        return await self._analyze_token(event)

    async def _stats_reporter(self) -> None:
        """Periodically report statistics."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                logger.info(
                    f"Stats: detected={self._stats['total_detected']}, "
                    f"analyzed={self._stats['total_analyzed']}, "
                    f"published={self._stats['total_published']}, "
                    f"failed={self._stats['total_failed']}, "
                    f"queue_size={self._processing_queue.qsize()}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stats reporter: {e}")

    def get_stats(self) -> dict:
        """Get orchestrator statistics."""
        return {
            **self._stats,
            "queue_size": self._processing_queue.qsize(),
            "active_jobs": len(self._active_jobs),
            "detector_stats": self.detector.get_stats(),
            "delivery_stats": self.delivery.get_stats(),
        }

    def get_active_jobs(self) -> dict[str, AnalysisJob]:
        """Get currently active analysis jobs."""
        return self._active_jobs.copy()


# Helper import
from src.synthesis.prompts import format_fdv


async def run_orchestrator():
    """Run the orchestrator (for direct execution)."""
    from src.utils.logging_config import setup_logging

    settings = get_settings()
    setup_logging(
        level=settings.log_level,
        log_file=settings.paths.log_file,
        debug=settings.debug,
    )

    orchestrator = TokenAnalysisOrchestrator(settings)

    try:
        await orchestrator.start()

        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(run_orchestrator())
