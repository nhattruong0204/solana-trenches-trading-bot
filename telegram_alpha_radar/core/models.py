"""Domain models used across the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class TokenMatch:
    """A single contract detection result from a message."""

    contract: str
    chain: str
    chat_id: int
    message_id: int
    timestamp: datetime

    def __post_init__(self) -> None:
        # Ensure timezone-aware timestamp
        if self.timestamp.tzinfo is None:
            object.__setattr__(
                self, "timestamp", self.timestamp.replace(tzinfo=timezone.utc)
            )


@dataclass(slots=True)
class TrendingToken:
    """Aggregated trending data for a single contract."""

    contract: str
    chain: str
    mention_count: int
    unique_chats: int
    velocity: float = 0.0
    score: float = 0.0

    def compute_score(self) -> None:
        """score = mentions * 2 + unique_chats * 3 + velocity * 5"""
        self.score = (
            self.mention_count * 2
            + self.unique_chats * 3
            + self.velocity * 5
        )


@dataclass(frozen=True, slots=True)
class MentionRecord:
    """A persisted mention row — maps 1:1 to the DB table."""

    id: int
    contract: str
    chain: str
    chat_id: int
    message_id: int
    mentioned_at: datetime


@dataclass(slots=True)
class HealthStatus:
    """Application health snapshot."""

    uptime_seconds: float = 0.0
    messages_processed: int = 0
    mentions_recorded: int = 0
    alerts_sent: int = 0
    db_connected: bool = False
    telegram_connected: bool = False
    detectors_loaded: list[str] = field(default_factory=list)
