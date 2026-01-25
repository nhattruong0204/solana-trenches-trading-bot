"""
Hit Rate Tracker for Performance Analytics.

This module tracks and calculates trading performance metrics for:
- Marketing and credibility (public hit rate display)
- Internal performance monitoring
- Daily/weekly/monthly reports
- Leaderboard of best calls

Inspired by AstroX's "Consistency High Hit-rate" feature.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from asyncpg import Pool

logger = logging.getLogger(__name__)


class TimeFrame(str, Enum):
    """Time frames for statistics."""
    HOUR_24 = "24h"
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    ALL_TIME = "all"


@dataclass
class SignalRecord:
    """Record of a signal for hit rate tracking."""

    signal_id: str  # Unique identifier (can be msg_id or token_address)
    token_symbol: str
    token_address: str
    entry_time: datetime
    entry_fdv: Optional[float] = None

    # Performance tracking
    max_multiplier: float = 1.0
    last_multiplier: float = 1.0
    hit_2x: bool = False
    hit_3x: bool = False
    hit_5x: bool = False
    hit_10x: bool = False
    hit_20x: bool = False

    # Timestamps for various hits
    hit_2x_time: Optional[datetime] = None
    hit_5x_time: Optional[datetime] = None
    hit_10x_time: Optional[datetime] = None

    # Status
    is_rugged: bool = False
    is_closed: bool = False
    closed_at: Optional[datetime] = None
    closed_multiplier: Optional[float] = None

    def update_multiplier(self, multiplier: float, timestamp: Optional[datetime] = None) -> None:
        """Update with a new multiplier reading."""
        ts = timestamp or datetime.now(timezone.utc)

        self.last_multiplier = multiplier

        if multiplier > self.max_multiplier:
            self.max_multiplier = multiplier

        # Track milestone hits
        if multiplier >= 2.0 and not self.hit_2x:
            self.hit_2x = True
            self.hit_2x_time = ts

        if multiplier >= 3.0 and not self.hit_3x:
            self.hit_3x = True

        if multiplier >= 5.0 and not self.hit_5x:
            self.hit_5x = True
            self.hit_5x_time = ts

        if multiplier >= 10.0 and not self.hit_10x:
            self.hit_10x = True
            self.hit_10x_time = ts

        if multiplier >= 20.0 and not self.hit_20x:
            self.hit_20x = True

    @property
    def time_to_2x_hours(self) -> Optional[float]:
        """Hours from entry to 2X."""
        if not self.hit_2x_time:
            return None
        delta = self.hit_2x_time - self.entry_time
        return delta.total_seconds() / 3600

    @property
    def age_hours(self) -> float:
        """Hours since entry."""
        now = datetime.now(timezone.utc)
        delta = now - self.entry_time
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "entry_time": self.entry_time.isoformat(),
            "entry_fdv": self.entry_fdv,
            "max_multiplier": self.max_multiplier,
            "last_multiplier": self.last_multiplier,
            "hit_2x": self.hit_2x,
            "hit_3x": self.hit_3x,
            "hit_5x": self.hit_5x,
            "hit_10x": self.hit_10x,
            "hit_20x": self.hit_20x,
            "hit_2x_time": self.hit_2x_time.isoformat() if self.hit_2x_time else None,
            "hit_5x_time": self.hit_5x_time.isoformat() if self.hit_5x_time else None,
            "hit_10x_time": self.hit_10x_time.isoformat() if self.hit_10x_time else None,
            "is_rugged": self.is_rugged,
            "is_closed": self.is_closed,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "closed_multiplier": self.closed_multiplier,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalRecord":
        """Create from dictionary."""
        return cls(
            signal_id=data["signal_id"],
            token_symbol=data["token_symbol"],
            token_address=data["token_address"],
            entry_time=datetime.fromisoformat(data["entry_time"]),
            entry_fdv=data.get("entry_fdv"),
            max_multiplier=data.get("max_multiplier", 1.0),
            last_multiplier=data.get("last_multiplier", 1.0),
            hit_2x=data.get("hit_2x", False),
            hit_3x=data.get("hit_3x", False),
            hit_5x=data.get("hit_5x", False),
            hit_10x=data.get("hit_10x", False),
            hit_20x=data.get("hit_20x", False),
            hit_2x_time=datetime.fromisoformat(data["hit_2x_time"]) if data.get("hit_2x_time") else None,
            hit_5x_time=datetime.fromisoformat(data["hit_5x_time"]) if data.get("hit_5x_time") else None,
            hit_10x_time=datetime.fromisoformat(data["hit_10x_time"]) if data.get("hit_10x_time") else None,
            is_rugged=data.get("is_rugged", False),
            is_closed=data.get("is_closed", False),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
            closed_multiplier=data.get("closed_multiplier"),
        )


@dataclass
class HitRateMetrics:
    """Calculated hit rate metrics."""

    timeframe: TimeFrame
    timeframe_label: str

    # Signal counts
    total_signals: int = 0
    active_signals: int = 0
    closed_signals: int = 0
    rugged_signals: int = 0

    # Hit counts
    hit_2x_count: int = 0
    hit_3x_count: int = 0
    hit_5x_count: int = 0
    hit_10x_count: int = 0
    hit_20x_count: int = 0

    # Rates (percentages)
    hit_rate_2x: float = 0.0
    hit_rate_3x: float = 0.0
    hit_rate_5x: float = 0.0
    hit_rate_10x: float = 0.0

    # Performance
    avg_multiplier: float = 0.0
    avg_max_multiplier: float = 0.0
    best_multiplier: float = 0.0
    best_signal: Optional[SignalRecord] = None

    # Timing
    avg_time_to_2x_hours: Optional[float] = None
    avg_time_to_5x_hours: Optional[float] = None

    # Top performers
    top_signals: list[SignalRecord] = field(default_factory=list)


class HitRateTracker:
    """
    Tracks and calculates hit rate statistics.

    Provides real-time performance metrics for:
    - Public marketing (show credibility)
    - Internal monitoring
    - Report generation

    Usage:
        tracker = HitRateTracker()
        await tracker.load()

        # Record a new signal
        tracker.record_signal(token_symbol, token_address, entry_time)

        # Update when price changes
        tracker.update_signal(signal_id, multiplier)

        # Get metrics
        metrics = tracker.calculate_metrics(TimeFrame.DAYS_7)
    """

    def __init__(
        self,
        state_file: str = "hit_rate_state.json",
        db_pool: Optional["Pool"] = None,
    ) -> None:
        """
        Initialize hit rate tracker.

        Args:
            state_file: Path to state file
            db_pool: Optional PostgreSQL pool
        """
        self._state_file = Path(state_file)
        self._db_pool = db_pool
        self._signals: dict[str, SignalRecord] = {}
        self._initialized = False

    async def load(self) -> None:
        """Load state from file or database."""
        if self._db_pool:
            await self._load_from_database()
        elif self._state_file.exists():
            await self._load_from_file()

        self._initialized = True
        logger.info(f"Loaded {len(self._signals)} signal records for hit rate tracking")

    async def _load_from_file(self) -> None:
        """Load from JSON file."""
        try:
            with open(self._state_file, 'r') as f:
                data = json.load(f)

            for sig_data in data.get("signals", []):
                sig = SignalRecord.from_dict(sig_data)
                self._signals[sig.signal_id] = sig

        except Exception as e:
            logger.error(f"Failed to load hit rate state: {e}")

    async def _load_from_database(self) -> None:
        """Load from PostgreSQL."""
        # Implementation for database loading
        pass

    async def save(self) -> None:
        """Save state to file."""
        if self._db_pool:
            return  # Database saves are immediate

        try:
            data = {
                "signals": [sig.to_dict() for sig in self._signals.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(self._state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save hit rate state: {e}")

    def record_signal(
        self,
        signal_id: str,
        token_symbol: str,
        token_address: str,
        entry_time: Optional[datetime] = None,
        entry_fdv: Optional[float] = None,
    ) -> SignalRecord:
        """
        Record a new signal for tracking.

        Args:
            signal_id: Unique identifier (e.g., message ID)
            token_symbol: Token symbol
            token_address: Token address
            entry_time: Entry timestamp
            entry_fdv: FDV at entry

        Returns:
            New SignalRecord
        """
        record = SignalRecord(
            signal_id=signal_id,
            token_symbol=token_symbol,
            token_address=token_address,
            entry_time=entry_time or datetime.now(timezone.utc),
            entry_fdv=entry_fdv,
        )

        self._signals[signal_id] = record

        # Save asynchronously
        asyncio.create_task(self.save())

        logger.debug(f"Recorded signal: ${token_symbol} for hit rate tracking")
        return record

    def update_signal(
        self,
        signal_id: str,
        multiplier: float,
        timestamp: Optional[datetime] = None,
    ) -> Optional[SignalRecord]:
        """
        Update a signal with new multiplier data.

        Args:
            signal_id: Signal identifier
            multiplier: Current multiplier
            timestamp: Timestamp of the update

        Returns:
            Updated SignalRecord or None if not found
        """
        record = self._signals.get(signal_id)
        if not record:
            return None

        old_max = record.max_multiplier
        record.update_multiplier(multiplier, timestamp)

        # Log milestone hits
        if record.max_multiplier > old_max:
            if record.hit_10x and old_max < 10:
                logger.info(f"🚀 ${record.token_symbol} hit 10X!")
            elif record.hit_5x and old_max < 5:
                logger.info(f"🔥 ${record.token_symbol} hit 5X!")
            elif record.hit_2x and old_max < 2:
                logger.info(f"🟢 ${record.token_symbol} hit 2X!")

        # Save asynchronously
        asyncio.create_task(self.save())

        return record

    def mark_rugged(self, signal_id: str) -> Optional[SignalRecord]:
        """Mark a signal as rugged."""
        record = self._signals.get(signal_id)
        if not record:
            return None

        record.is_rugged = True
        record.is_closed = True
        record.closed_at = datetime.now(timezone.utc)
        record.closed_multiplier = 0.0

        asyncio.create_task(self.save())

        logger.info(f"Marked ${record.token_symbol} as rugged")
        return record

    def close_signal(
        self,
        signal_id: str,
        exit_multiplier: float,
    ) -> Optional[SignalRecord]:
        """Close a signal (sold)."""
        record = self._signals.get(signal_id)
        if not record:
            return None

        record.is_closed = True
        record.closed_at = datetime.now(timezone.utc)
        record.closed_multiplier = exit_multiplier

        asyncio.create_task(self.save())

        return record

    def get_signal(self, signal_id: str) -> Optional[SignalRecord]:
        """Get a signal by ID."""
        return self._signals.get(signal_id)

    def get_signal_by_address(self, token_address: str) -> Optional[SignalRecord]:
        """Get signal by token address."""
        for record in self._signals.values():
            if record.token_address == token_address:
                return record
        return None

    def _filter_by_timeframe(
        self,
        timeframe: TimeFrame,
    ) -> list[SignalRecord]:
        """Filter signals by timeframe."""
        now = datetime.now(timezone.utc)

        if timeframe == TimeFrame.ALL_TIME:
            return list(self._signals.values())

        cutoffs = {
            TimeFrame.HOUR_24: timedelta(hours=24),
            TimeFrame.DAYS_7: timedelta(days=7),
            TimeFrame.DAYS_30: timedelta(days=30),
        }

        cutoff = now - cutoffs[timeframe]

        return [
            s for s in self._signals.values()
            if s.entry_time >= cutoff
        ]

    def calculate_metrics(self, timeframe: TimeFrame = TimeFrame.ALL_TIME) -> HitRateMetrics:
        """
        Calculate hit rate metrics for a timeframe.

        Args:
            timeframe: Time period to analyze

        Returns:
            HitRateMetrics with calculated statistics
        """
        signals = self._filter_by_timeframe(timeframe)

        timeframe_labels = {
            TimeFrame.HOUR_24: "Last 24 Hours",
            TimeFrame.DAYS_7: "Last 7 Days",
            TimeFrame.DAYS_30: "Last 30 Days",
            TimeFrame.ALL_TIME: "All Time",
        }

        metrics = HitRateMetrics(
            timeframe=timeframe,
            timeframe_label=timeframe_labels[timeframe],
            total_signals=len(signals),
        )

        if not signals:
            return metrics

        # Count by status
        metrics.active_signals = len([s for s in signals if not s.is_closed])
        metrics.closed_signals = len([s for s in signals if s.is_closed])
        metrics.rugged_signals = len([s for s in signals if s.is_rugged])

        # Count hits
        metrics.hit_2x_count = len([s for s in signals if s.hit_2x])
        metrics.hit_3x_count = len([s for s in signals if s.hit_3x])
        metrics.hit_5x_count = len([s for s in signals if s.hit_5x])
        metrics.hit_10x_count = len([s for s in signals if s.hit_10x])
        metrics.hit_20x_count = len([s for s in signals if s.hit_20x])

        # Calculate rates
        total = len(signals)
        metrics.hit_rate_2x = (metrics.hit_2x_count / total) * 100
        metrics.hit_rate_3x = (metrics.hit_3x_count / total) * 100
        metrics.hit_rate_5x = (metrics.hit_5x_count / total) * 100
        metrics.hit_rate_10x = (metrics.hit_10x_count / total) * 100

        # Performance stats
        multipliers = [s.max_multiplier for s in signals]
        last_multipliers = [s.last_multiplier for s in signals]

        metrics.avg_max_multiplier = sum(multipliers) / len(multipliers)
        metrics.avg_multiplier = sum(last_multipliers) / len(last_multipliers)
        metrics.best_multiplier = max(multipliers)

        # Find best signal
        best_signal = max(signals, key=lambda s: s.max_multiplier)
        metrics.best_signal = best_signal

        # Time to hit stats
        times_to_2x = [s.time_to_2x_hours for s in signals if s.time_to_2x_hours is not None]
        if times_to_2x:
            metrics.avg_time_to_2x_hours = sum(times_to_2x) / len(times_to_2x)

        # Top performers
        metrics.top_signals = sorted(signals, key=lambda s: s.max_multiplier, reverse=True)[:10]

        return metrics

    def format_public_stats(self, timeframe: TimeFrame = TimeFrame.DAYS_7) -> str:
        """
        Format statistics for public marketing display.

        This is what gets shown to attract premium subscribers.
        """
        metrics = self.calculate_metrics(timeframe)

        lines = [
            "📊 **PERFORMANCE STATISTICS**",
            f"_{metrics.timeframe_label}_",
            "",
            "═══════════════════════════",
            "",
            f"📈 **Hit Rates:**",
            f"• 2X+ Win Rate: **{metrics.hit_rate_2x:.0f}%**",
            f"• 5X+ Win Rate: **{metrics.hit_rate_5x:.0f}%**",
            f"• 10X+ Win Rate: **{metrics.hit_rate_10x:.0f}%**",
            "",
            f"🎯 **Performance:**",
            f"• Total Signals: {metrics.total_signals}",
            f"• Average Max: **{metrics.avg_max_multiplier:.1f}X**",
            f"• Best Call: **{metrics.best_multiplier:.0f}X**",
        ]

        if metrics.best_signal:
            lines.append(f"  └ ${metrics.best_signal.token_symbol}")

        if metrics.avg_time_to_2x_hours:
            lines.extend([
                "",
                f"⏱️ Avg Time to 2X: **{metrics.avg_time_to_2x_hours:.1f}h**",
            ])

        lines.extend([
            "",
            "═══════════════════════════",
            "",
            "_Updated in real-time_",
        ])

        return "\n".join(lines)

    def format_detailed_stats(self) -> str:
        """Format detailed statistics for admin/premium view."""
        all_time = self.calculate_metrics(TimeFrame.ALL_TIME)
        weekly = self.calculate_metrics(TimeFrame.DAYS_7)
        daily = self.calculate_metrics(TimeFrame.HOUR_24)

        lines = [
            "📊 **DETAILED PERFORMANCE REPORT**",
            "",
            "**24 Hour Stats:**",
            f"• Signals: {daily.total_signals}",
            f"• 2X Hits: {daily.hit_2x_count} ({daily.hit_rate_2x:.0f}%)",
            f"• 5X Hits: {daily.hit_5x_count} ({daily.hit_rate_5x:.0f}%)",
            "",
            "**7 Day Stats:**",
            f"• Signals: {weekly.total_signals}",
            f"• 2X Hits: {weekly.hit_2x_count} ({weekly.hit_rate_2x:.0f}%)",
            f"• 5X Hits: {weekly.hit_5x_count} ({weekly.hit_rate_5x:.0f}%)",
            f"• 10X Hits: {weekly.hit_10x_count} ({weekly.hit_rate_10x:.0f}%)",
            "",
            "**All Time Stats:**",
            f"• Total Signals: {all_time.total_signals}",
            f"• Active: {all_time.active_signals}",
            f"• Closed: {all_time.closed_signals}",
            f"• Rugged: {all_time.rugged_signals}",
            "",
            f"• 2X Hits: {all_time.hit_2x_count} ({all_time.hit_rate_2x:.0f}%)",
            f"• 5X Hits: {all_time.hit_5x_count} ({all_time.hit_rate_5x:.0f}%)",
            f"• 10X Hits: {all_time.hit_10x_count} ({all_time.hit_rate_10x:.0f}%)",
            f"• 20X+ Hits: {all_time.hit_20x_count}",
            "",
            f"• Best Call: **{all_time.best_multiplier:.0f}X**",
            f"• Average: {all_time.avg_max_multiplier:.1f}X",
        ]

        if all_time.avg_time_to_2x_hours:
            lines.append(f"• Avg Time to 2X: {all_time.avg_time_to_2x_hours:.1f}h")

        return "\n".join(lines)

    def format_leaderboard(self, limit: int = 10) -> str:
        """Format top performers leaderboard."""
        metrics = self.calculate_metrics(TimeFrame.ALL_TIME)

        lines = [
            "🏆 **TOP PERFORMERS - LEADERBOARD**",
            "",
        ]

        medals = ["🥇", "🥈", "🥉"]

        for i, signal in enumerate(metrics.top_signals[:limit]):
            if i < 3:
                prefix = medals[i]
            else:
                prefix = f"{i + 1}."

            lines.append(
                f"{prefix} **${signal.token_symbol}** - "
                f"{signal.max_multiplier:.0f}X"
            )

        return "\n".join(lines)

    def get_signals_needing_update(self, max_age_hours: int = 24) -> list[SignalRecord]:
        """Get active signals that need price updates."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)

        return [
            s for s in self._signals.values()
            if not s.is_closed and s.entry_time >= cutoff
        ]
