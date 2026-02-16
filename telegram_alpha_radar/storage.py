"""PostgreSQL storage layer using asyncpg.

Handles connection pooling, schema creation, mention persistence,
and time-window aggregation queries.
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

import asyncpg

from .config import DatabaseConfig

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS contract_mentions (
    id              BIGSERIAL PRIMARY KEY,
    contract        TEXT NOT NULL,
    chain           TEXT NOT NULL,
    chat_id         BIGINT NOT NULL,
    message_id      BIGINT NOT NULL,
    mentioned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint to deduplicate: same contract in same message
CREATE UNIQUE INDEX IF NOT EXISTS uq_contract_chat_message
    ON contract_mentions (contract, chat_id, message_id);

-- Index for time-window trending queries
CREATE INDEX IF NOT EXISTS idx_contract_mentioned_at
    ON contract_mentions (contract, mentioned_at);

-- Index for unique-chat counting
CREATE INDEX IF NOT EXISTS idx_contract_chat_mentioned_at
    ON contract_mentions (contract, chat_id, mentioned_at);
"""

_INSERT_MENTION_SQL = """
INSERT INTO contract_mentions (contract, chain, chat_id, message_id, mentioned_at)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (contract, chat_id, message_id) DO NOTHING;
"""

_TRENDING_QUERY_SQL = """
SELECT
    contract,
    chain,
    COUNT(*) AS mention_count,
    COUNT(DISTINCT chat_id) AS unique_chats
FROM contract_mentions
WHERE mentioned_at >= $1
GROUP BY contract, chain
HAVING COUNT(*) >= $2 AND COUNT(DISTINCT chat_id) >= $3
ORDER BY COUNT(*) DESC, COUNT(DISTINCT chat_id) DESC;
"""

_PREVIOUS_WINDOW_COUNT_SQL = """
SELECT COUNT(*) AS cnt
FROM contract_mentions
WHERE contract = $1 AND mentioned_at >= $2 AND mentioned_at < $3;
"""


@dataclass
class TrendingToken:
    """Aggregated trending token data."""

    contract: str
    chain: str
    mention_count: int
    unique_chats: int
    velocity_ratio: float = 0.0
    score: float = 0.0


class Storage:
    """Async PostgreSQL storage for contract mentions."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create the connection pool and ensure schema exists."""
        logger.info(
            "Connecting to PostgreSQL at %s:%s/%s",
            self._config.host,
            self._config.port,
            self._config.database,
        )
        self._pool = await asyncpg.create_pool(
            dsn=self._config.dsn,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)
        logger.info("Database schema ensured")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Database connection pool closed")

    async def record_mention(
        self,
        contract: str,
        chain: str,
        chat_id: int,
        message_id: int,
        mentioned_at: Optional[datetime] = None,
    ) -> None:
        """Insert a contract mention, deduplicating on (contract, chat_id, message_id)."""
        if not self._pool:
            raise RuntimeError("Storage not connected")
        ts = mentioned_at or datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                _INSERT_MENTION_SQL, contract, chain, chat_id, message_id, ts
            )
        logger.debug(
            "Recorded mention: contract=%s chain=%s chat=%s msg=%s",
            contract,
            chain,
            chat_id,
            message_id,
        )

    async def get_trending(
        self,
        since: datetime,
        min_mentions: int,
        min_unique_chats: int,
    ) -> list[TrendingToken]:
        """Return tokens that are trending within the given time window."""
        if not self._pool:
            raise RuntimeError("Storage not connected")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                _TRENDING_QUERY_SQL, since, min_mentions, min_unique_chats
            )
        results: list[TrendingToken] = []
        for row in rows:
            results.append(
                TrendingToken(
                    contract=row["contract"],
                    chain=row["chain"],
                    mention_count=row["mention_count"],
                    unique_chats=row["unique_chats"],
                )
            )
        return results

    async def get_mention_count_in_range(
        self,
        contract: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """Count mentions of a contract in a specific time range."""
        if not self._pool:
            raise RuntimeError("Storage not connected")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                _PREVIOUS_WINDOW_COUNT_SQL, contract, start, end
            )
        return row["cnt"] if row else 0
