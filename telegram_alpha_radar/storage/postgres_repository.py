"""PostgreSQL storage backend using asyncpg."""

from __future__ import annotations

import logging
from datetime import datetime

import asyncpg

from telegram_alpha_radar.config import DatabaseConfig
from telegram_alpha_radar.core.models import TokenMatch, TrendingToken
from telegram_alpha_radar.storage.base_repository import BaseRepository

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contract_mentions (
    id              BIGSERIAL       PRIMARY KEY,
    contract        TEXT            NOT NULL,
    chain           TEXT            NOT NULL,
    chat_id         BIGINT          NOT NULL,
    message_id      BIGINT          NOT NULL,
    mentioned_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (contract, chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_mentions_contract_time
    ON contract_mentions (contract, mentioned_at);

CREATE INDEX IF NOT EXISTS idx_mentions_contract_chat_time
    ON contract_mentions (contract, chat_id, mentioned_at);

CREATE INDEX IF NOT EXISTS idx_mentions_chain_time
    ON contract_mentions (chain, mentioned_at);
"""


class PostgresRepository(BaseRepository):
    """asyncpg-backed storage with connection pooling."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=self._config.dsn,
            min_size=self._config.pool_min,
            max_size=self._config.pool_max,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(_SCHEMA_SQL)
        logger.info(
            "PostgreSQL pool created (%d-%d) and schema ensured",
            self._config.pool_min,
            self._config.pool_max,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL pool closed")

    async def is_connected(self) -> bool:
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def record_mention(self, match: TokenMatch) -> bool:
        """Insert mention; return True if new, False if duplicate."""
        assert self._pool is not None
        sql = """
            INSERT INTO contract_mentions
                (contract, chain, chat_id, message_id, mentioned_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (contract, chat_id, message_id) DO NOTHING
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                match.contract,
                match.chain,
                match.chat_id,
                match.message_id,
                match.timestamp,
            )
        return row is not None

    async def get_trending(
        self,
        *,
        since: datetime,
        min_mentions: int,
        min_unique_chats: int,
        chain: str | None = None,
    ) -> list[TrendingToken]:
        assert self._pool is not None

        if chain:
            sql = """
                SELECT contract, chain,
                       COUNT(*)::int                       AS mention_count,
                       COUNT(DISTINCT chat_id)::int        AS unique_chats
                FROM contract_mentions
                WHERE mentioned_at >= $1
                  AND chain = $2
                GROUP BY contract, chain
                HAVING COUNT(*) >= $3
                   AND COUNT(DISTINCT chat_id) >= $4
                ORDER BY COUNT(*) DESC
            """
            params = (since, chain, min_mentions, min_unique_chats)
        else:
            sql = """
                SELECT contract, chain,
                       COUNT(*)::int                       AS mention_count,
                       COUNT(DISTINCT chat_id)::int        AS unique_chats
                FROM contract_mentions
                WHERE mentioned_at >= $1
                GROUP BY contract, chain
                HAVING COUNT(*) >= $2
                   AND COUNT(DISTINCT chat_id) >= $3
                ORDER BY COUNT(*) DESC
            """
            params = (since, min_mentions, min_unique_chats)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [
            TrendingToken(
                contract=r["contract"],
                chain=r["chain"],
                mention_count=r["mention_count"],
                unique_chats=r["unique_chats"],
            )
            for r in rows
        ]

    async def get_mention_count(
        self,
        contract: str,
        since: datetime,
        until: datetime,
    ) -> int:
        assert self._pool is not None
        sql = """
            SELECT COUNT(*)::int
            FROM contract_mentions
            WHERE contract = $1
              AND mentioned_at >= $2
              AND mentioned_at < $3
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, contract, since, until) or 0

    async def cleanup_old_mentions(self, before: datetime) -> int:
        assert self._pool is not None
        sql = "DELETE FROM contract_mentions WHERE mentioned_at < $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(sql, before)
        count = int(result.split()[-1])
        if count:
            logger.info("Cleaned up %d old mentions", count)
        return count
