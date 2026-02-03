"""Enrichment pipeline - orchestrates all enrichment agents."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.config import Settings
from src.enrichment.contract_analyzer import ContractAnalyzer
from src.enrichment.dev_osint import DevOSINTAgent
from src.enrichment.onchain_metrics import OnChainMetricsAgent
from src.models import (
    AnalysisJob,
    AnalysisStatus,
    ContractAnalysis,
    DevProfile,
    OnChainMetrics,
    TokenEvent,
)

logger = logging.getLogger(__name__)


class EnrichmentPipeline:
    """Orchestrates token data enrichment."""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Initialize agents
        self.contract_analyzer = ContractAnalyzer(settings)
        self.dev_osint = DevOSINTAgent(settings)
        self.onchain_metrics = OnChainMetricsAgent(settings)

        # Processing state
        self._processing: dict[str, AnalysisJob] = {}

    async def initialize(self) -> None:
        """Initialize all enrichment agents."""
        await asyncio.gather(
            self.contract_analyzer.initialize(),
            self.dev_osint.initialize(),
            self.onchain_metrics.initialize(),
        )
        logger.info("Enrichment pipeline initialized")

    async def close(self) -> None:
        """Close all enrichment agents."""
        await asyncio.gather(
            self.contract_analyzer.close(),
            self.dev_osint.close(),
            self.onchain_metrics.close(),
        )
        logger.info("Enrichment pipeline closed")

    async def enrich(
        self, event: TokenEvent, job: Optional[AnalysisJob] = None
    ) -> tuple[ContractAnalysis, DevProfile, OnChainMetrics]:
        """
        Run full enrichment pipeline for a token.

        All agents run in parallel for maximum speed.
        """
        logger.info(f"Starting enrichment for: {event.token_address}")
        start_time = datetime.utcnow()

        # Update job status if provided
        if job:
            job.status = AnalysisStatus.ENRICHING
            job.updated_at = start_time

        # Run all enrichment agents in parallel
        try:
            # First, get contract analysis (needed for dev OSINT)
            contract_analysis = await self.contract_analyzer.analyze(event)

            # Now run dev OSINT and on-chain metrics in parallel
            dev_osint_task = self.dev_osint.research(event, contract_analysis)
            metrics_task = self.onchain_metrics.fetch_metrics(event)

            dev_profile, onchain_metrics = await asyncio.gather(
                dev_osint_task, metrics_task
            )

            # Update job if provided
            if job:
                job.contract_analysis = contract_analysis
                job.dev_profile = dev_profile
                job.on_chain_metrics = onchain_metrics
                job.updated_at = datetime.utcnow()

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Enrichment complete in {elapsed:.2f}s for {event.token_address}")

            return contract_analysis, dev_profile, onchain_metrics

        except Exception as e:
            logger.error(f"Enrichment failed for {event.token_address}: {e}")
            if job:
                job.status = AnalysisStatus.FAILED
                job.error_message = str(e)
                job.updated_at = datetime.utcnow()
            raise

    async def enrich_fast(
        self, event: TokenEvent
    ) -> tuple[ContractAnalysis, Optional[DevProfile], OnChainMetrics]:
        """
        Fast enrichment - skip slow operations for quick assessment.

        Useful for initial filtering before full analysis.
        """
        logger.info(f"Fast enrichment for: {event.token_address}")

        # Run contract analysis and metrics in parallel
        # Skip dev OSINT (slowest)
        contract_task = self.contract_analyzer.analyze(event)
        metrics_task = self.onchain_metrics.fetch_metrics(event)

        contract_analysis, onchain_metrics = await asyncio.gather(
            contract_task, metrics_task
        )

        return contract_analysis, None, onchain_metrics

    async def should_skip_token(
        self, event: TokenEvent, onchain_metrics: OnChainMetrics
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if token should be skipped based on quick checks.

        Returns (should_skip, reason).
        """
        # Check minimum liquidity
        if onchain_metrics.liquidity_usd < self.settings.analysis.min_liquidity_usd:
            return True, f"Low liquidity: ${onchain_metrics.liquidity_usd:,.0f}"

        # Check minimum holders
        if onchain_metrics.holder_count < self.settings.analysis.min_holder_count:
            return True, f"Low holder count: {onchain_metrics.holder_count}"

        # Check for excessive top holder concentration
        if (
            onchain_metrics.top_10_holder_pct
            > self.settings.analysis.max_top_holder_percentage
        ):
            return True, f"High concentration: {onchain_metrics.top_10_holder_pct:.1f}%"

        # Check token age (skip very old tokens)
        if onchain_metrics.token_age_hours > 168:  # > 1 week
            return True, "Token too old (>1 week)"

        return False, None

    async def refresh_before_publish(
        self, job: AnalysisJob
    ) -> OnChainMetrics:
        """
        Refresh on-chain metrics just before publishing.

        This ensures we have the latest FDV and price data.
        """
        if not job.on_chain_metrics:
            raise ValueError("No existing metrics to refresh")

        event = TokenEvent(
            token_address=job.token_address,
            pair_address=job.on_chain_metrics.pair_address,
            source=job.event.source if job.event else EventSource.MANUAL,
            detected_at=datetime.utcnow(),
        )

        fresh_metrics = await self.onchain_metrics.fetch_metrics(event)
        job.on_chain_metrics = fresh_metrics
        job.updated_at = datetime.utcnow()

        return fresh_metrics

    def get_processing_jobs(self) -> dict[str, AnalysisJob]:
        """Get currently processing jobs."""
        return self._processing.copy()


# Import for type hint
from src.models import EventSource
