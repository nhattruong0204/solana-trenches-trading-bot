"""Abstract storage interface — allows swapping PostgreSQL for Redis, SQLite, etc."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from telegram_alpha_radar.core.models import TokenMatch, TrendingToken


class BaseRepository(ABC):
    """Contract for all storage backends."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / pool and ensure schema exists."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release all connections."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Health probe."""
        ...

    @abstractmethod
    async def record_mention(self, match: TokenMatch) -> bool:
        """Persist a mention. Return True if it was new (not a duplicate)."""
        ...

    @abstractmethod
    async def get_trending(
        self,
        *,
        since: datetime,
        min_mentions: int,
        min_unique_chats: int,
        chain: str | None = None,
    ) -> list[TrendingToken]:
        """Return tokens meeting trending thresholds since *since*."""
        ...

    @abstractmethod
    async def get_mention_count(
        self,
        contract: str,
        since: datetime,
        until: datetime,
    ) -> int:
        """Count mentions in the time range [since, until)."""
        ...

    @abstractmethod
    async def cleanup_old_mentions(self, before: datetime) -> int:
        """Delete mentions older than *before*. Return count deleted."""
        ...
