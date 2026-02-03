"""Database repository for token analysis."""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional

import asyncpg

from src.config import Settings
from src.models import (
    AnalysisJob,
    AnalysisStatus,
    BlacklistEntry,
    ContractAnalysis,
    DevProfile,
    OnChainMetrics,
    TokenBreakdown,
    TokenEvent,
)

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """Repository for analysis data persistence."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        """Initialize database connection pool."""
        self._pool = await asyncpg.create_pool(
            self.settings.database.url,
            min_size=2,
            max_size=self.settings.database.pool_size,
        )
        logger.info("Database connection pool initialized")

        # Create tables if not exist
        await self._create_tables()

    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
        logger.info("Database connection pool closed")

    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_analyses (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(64) UNIQUE NOT NULL,
                    token_address VARCHAR(42) NOT NULL,
                    symbol VARCHAR(32),
                    name VARCHAR(128),
                    chain_id INTEGER DEFAULT 8453,
                    source VARCHAR(32),
                    detected_at TIMESTAMP NOT NULL,
                    risk_rating VARCHAR(16),
                    fdv_usd FLOAT DEFAULT 0,
                    liquidity_usd FLOAT DEFAULT 0,
                    holder_count INTEGER DEFAULT 0,
                    top_10_holder_pct FLOAT DEFAULT 0,
                    dev_twitter_handle VARCHAR(32),
                    dev_twitter_followers INTEGER DEFAULT 0,
                    dev_is_anonymous BOOLEAN DEFAULT TRUE,
                    deployer_address VARCHAR(42),
                    is_honeypot BOOLEAN DEFAULT FALSE,
                    is_renounced BOOLEAN DEFAULT FALSE,
                    status VARCHAR(32) DEFAULT 'pending',
                    error_message TEXT,
                    telegram_message_id INTEGER,
                    published_at TIMESTAMP,
                    contract_analysis_json JSONB,
                    dev_profile_json JSONB,
                    onchain_metrics_json JSONB,
                    breakdown_json JSONB,
                    processing_time_seconds FLOAT DEFAULT 0,
                    confidence_score FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_token_address ON token_analyses(token_address);
                CREATE INDEX IF NOT EXISTS idx_symbol ON token_analyses(symbol);
                CREATE INDEX IF NOT EXISTS idx_status ON token_analyses(status);
                CREATE INDEX IF NOT EXISTS idx_detected_at ON token_analyses(detected_at);

                CREATE TABLE IF NOT EXISTS blacklist (
                    id SERIAL PRIMARY KEY,
                    identifier VARCHAR(128) UNIQUE NOT NULL,
                    category VARCHAR(32) NOT NULL,
                    reason TEXT NOT NULL,
                    added_by VARCHAR(64) DEFAULT 'system',
                    added_at TIMESTAMP DEFAULT NOW(),
                    evidence_json JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_blacklist_category ON blacklist(category);

                CREATE TABLE IF NOT EXISTS analysis_stats (
                    id SERIAL PRIMARY KEY,
                    date TIMESTAMP NOT NULL,
                    total_detected INTEGER DEFAULT 0,
                    total_analyzed INTEGER DEFAULT 0,
                    total_published INTEGER DEFAULT 0,
                    total_rejected INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    rating_green INTEGER DEFAULT 0,
                    rating_yellow INTEGER DEFAULT 0,
                    rating_orange INTEGER DEFAULT 0,
                    rating_red INTEGER DEFAULT 0,
                    source_chain INTEGER DEFAULT 0,
                    source_moltbook INTEGER DEFAULT 0,
                    source_twitter INTEGER DEFAULT 0,
                    source_manual INTEGER DEFAULT 0,
                    avg_processing_time FLOAT DEFAULT 0,
                    avg_confidence_score FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_stats_date ON analysis_stats(date);
            """)
        logger.info("Database tables created/verified")

    async def save_analysis(self, job: AnalysisJob) -> None:
        """Save or update an analysis job."""
        async with self._pool.acquire() as conn:
            # Serialize nested objects
            contract_json = None
            dev_json = None
            metrics_json = None
            breakdown_json = None

            if job.contract_analysis:
                contract_json = json.dumps(asdict(job.contract_analysis), default=str)
            if job.dev_profile:
                dev_json = json.dumps(asdict(job.dev_profile), default=str)
            if job.on_chain_metrics:
                metrics_json = json.dumps(asdict(job.on_chain_metrics), default=str)
            if job.breakdown:
                # Don't include nested objects in breakdown JSON
                breakdown_dict = {
                    "token_address": job.breakdown.token_address,
                    "symbol": job.breakdown.symbol,
                    "name": job.breakdown.name,
                    "fdv_usd": job.breakdown.fdv_usd,
                    "fdv_display": job.breakdown.fdv_display,
                    "risk_rating": job.breakdown.risk_rating.value,
                    "overall_confidence": job.breakdown.overall_confidence,
                    "dev_twitter_url": job.breakdown.dev_twitter_url,
                    "pros": [{"text": p.text, "confidence": p.confidence} for p in job.breakdown.pros],
                    "cons": [{"text": c.text, "confidence": c.confidence} for c in job.breakdown.cons],
                    "dexscreener_url": job.breakdown.dexscreener_url,
                    "processing_time_seconds": job.breakdown.processing_time_seconds,
                }
                breakdown_json = json.dumps(breakdown_dict, default=str)

            await conn.execute("""
                INSERT INTO token_analyses (
                    job_id, token_address, symbol, name, chain_id,
                    source, detected_at, risk_rating, fdv_usd, liquidity_usd,
                    holder_count, top_10_holder_pct, dev_twitter_handle,
                    dev_twitter_followers, dev_is_anonymous, deployer_address,
                    is_honeypot, is_renounced, status, error_message,
                    telegram_message_id, published_at, contract_analysis_json,
                    dev_profile_json, onchain_metrics_json, breakdown_json,
                    processing_time_seconds, confidence_score, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                    $21, $22, $23, $24, $25, $26, $27, $28, NOW()
                )
                ON CONFLICT (job_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    telegram_message_id = EXCLUDED.telegram_message_id,
                    published_at = EXCLUDED.published_at,
                    breakdown_json = EXCLUDED.breakdown_json,
                    processing_time_seconds = EXCLUDED.processing_time_seconds,
                    confidence_score = EXCLUDED.confidence_score,
                    updated_at = NOW()
            """,
                job.job_id,
                job.token_address,
                job.breakdown.symbol if job.breakdown else None,
                job.breakdown.name if job.breakdown else None,
                job.event.chain_id if job.event else 8453,
                job.event.source.value if job.event else None,
                job.event.detected_at if job.event else datetime.utcnow(),
                job.breakdown.risk_rating.value if job.breakdown else None,
                job.breakdown.fdv_usd if job.breakdown else 0,
                job.on_chain_metrics.liquidity_usd if job.on_chain_metrics else 0,
                job.on_chain_metrics.holder_count if job.on_chain_metrics else 0,
                job.on_chain_metrics.top_10_holder_pct if job.on_chain_metrics else 0,
                job.dev_profile.twitter_handle if job.dev_profile else None,
                job.dev_profile.twitter_followers if job.dev_profile else 0,
                job.dev_profile.is_anonymous if job.dev_profile else True,
                job.contract_analysis.deployer_address if job.contract_analysis else None,
                job.contract_analysis.is_honeypot if job.contract_analysis else False,
                job.contract_analysis.is_renounced if job.contract_analysis else False,
                job.status.value,
                job.error_message,
                job.telegram_message_id,
                job.published_at,
                contract_json,
                dev_json,
                metrics_json,
                breakdown_json,
                job.breakdown.processing_time_seconds if job.breakdown else 0,
                job.breakdown.overall_confidence if job.breakdown else 0,
            )

    async def get_analysis(self, job_id: str) -> Optional[dict]:
        """Get analysis by job ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM token_analyses WHERE job_id = $1", job_id
            )
            return dict(row) if row else None

    async def get_by_token_address(self, token_address: str) -> list[dict]:
        """Get all analyses for a token address."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM token_analyses WHERE token_address = $1 ORDER BY created_at DESC",
                token_address.lower(),
            )
            return [dict(row) for row in rows]

    async def is_token_analyzed(self, token_address: str, hours: int = 24) -> bool:
        """Check if token was analyzed recently."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT 1 FROM token_analyses
                   WHERE token_address = $1 AND created_at > $2 LIMIT 1""",
                token_address.lower(),
                cutoff,
            )
            return row is not None

    async def add_to_blacklist(self, entry: BlacklistEntry) -> None:
        """Add entry to blacklist."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO blacklist (identifier, category, reason, added_by, evidence_json)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (identifier) DO UPDATE SET
                    reason = EXCLUDED.reason,
                    added_by = EXCLUDED.added_by,
                    added_at = NOW()
            """,
                entry.address.lower(),
                entry.category,
                entry.reason,
                entry.added_by,
                None,
            )

    async def is_blacklisted(self, identifier: str) -> Optional[dict]:
        """Check if identifier is blacklisted."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM blacklist WHERE identifier = $1",
                identifier.lower(),
            )
            return dict(row) if row else None

    async def get_blacklist(self, category: Optional[str] = None) -> list[dict]:
        """Get blacklist entries."""
        async with self._pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    "SELECT * FROM blacklist WHERE category = $1", category
                )
            else:
                rows = await conn.fetch("SELECT * FROM blacklist")
            return [dict(row) for row in rows]

    async def get_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> dict:
        """Get analysis statistics."""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=7)
        if not end_date:
            end_date = datetime.utcnow()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'published') as published,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE risk_rating = 'green') as green,
                    COUNT(*) FILTER (WHERE risk_rating = 'yellow') as yellow,
                    COUNT(*) FILTER (WHERE risk_rating = 'orange') as orange,
                    COUNT(*) FILTER (WHERE risk_rating = 'red') as red,
                    AVG(processing_time_seconds) as avg_time,
                    AVG(confidence_score) as avg_confidence
                FROM token_analyses
                WHERE created_at BETWEEN $1 AND $2
            """, start_date, end_date)

            return dict(row) if row else {}

    async def get_recent_analyses(self, limit: int = 20) -> list[dict]:
        """Get recent analyses."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT job_id, token_address, symbol, risk_rating, status,
                          fdv_usd, liquidity_usd, created_at
                   FROM token_analyses
                   ORDER BY created_at DESC LIMIT $1""",
                limit,
            )
            return [dict(row) for row in rows]
