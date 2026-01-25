"""
Public Channel Signal Publisher for Marketing.

This module broadcasts significant winning trades to a public Telegram channel
for marketing purposes, similar to how AstroX Hub showcases winning calls.

Features:
- Broadcasts signals that hit configurable multiplier thresholds (2X, 5X, 10X, etc.)
- Tracks hit rate statistics for credibility
- Formats messages professionally for marketing
- Delays broadcasts to avoid front-running by free users
- Includes call-to-action for premium subscription
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

logger = logging.getLogger(__name__)


class SignalTier(str, Enum):
    """Signal performance tiers for broadcasting."""
    TIER_2X = "2X"
    TIER_3X = "3X"
    TIER_5X = "5X"
    TIER_10X = "10X"
    TIER_20X = "20X"
    TIER_50X = "50X"
    TIER_100X = "100X"


@dataclass
class BroadcastConfig:
    """Configuration for public channel broadcasting."""

    # Public channel settings
    public_channel_id: Optional[str] = None
    public_channel_username: Optional[str] = None

    # Broadcast thresholds
    min_multiplier_to_broadcast: float = 2.0  # Minimum X to broadcast
    broadcast_delay_seconds: int = 300  # 5 minute delay for free channel

    # Message settings
    show_token_address: bool = False  # Hide address in public (premium only)
    show_entry_price: bool = False
    include_cta: bool = True  # Call-to-action for premium

    # Premium settings
    premium_channel_id: Optional[str] = None
    premium_instant_broadcast: bool = True  # Premium gets instant alerts

    # Branding
    bot_name: str = "Trenches Trading Bot"
    bot_username: str = "TrenchesBot"


@dataclass
class BroadcastSignal:
    """A signal prepared for broadcasting."""

    token_symbol: str
    token_address: str
    entry_time: datetime
    alert_time: datetime
    multiplier: float
    entry_fdv: Optional[float] = None
    current_fdv: Optional[float] = None
    signal_msg_id: Optional[int] = None

    @property
    def tier(self) -> SignalTier:
        """Get the performance tier for this signal."""
        if self.multiplier >= 100:
            return SignalTier.TIER_100X
        elif self.multiplier >= 50:
            return SignalTier.TIER_50X
        elif self.multiplier >= 20:
            return SignalTier.TIER_20X
        elif self.multiplier >= 10:
            return SignalTier.TIER_10X
        elif self.multiplier >= 5:
            return SignalTier.TIER_5X
        elif self.multiplier >= 3:
            return SignalTier.TIER_3X
        else:
            return SignalTier.TIER_2X

    @property
    def hold_duration_hours(self) -> float:
        """Calculate holding duration in hours."""
        delta = self.alert_time - self.entry_time
        return delta.total_seconds() / 3600

    @property
    def tier_emoji(self) -> str:
        """Get emoji for the tier."""
        emojis = {
            SignalTier.TIER_2X: "🟢",
            SignalTier.TIER_3X: "🟢",
            SignalTier.TIER_5X: "🔥",
            SignalTier.TIER_10X: "🚀",
            SignalTier.TIER_20X: "💎",
            SignalTier.TIER_50X: "👑",
            SignalTier.TIER_100X: "🏆",
        }
        return emojis.get(self.tier, "📈")


@dataclass
class HitRateStats:
    """Statistics for hit rate tracking."""

    total_signals: int = 0
    signals_2x: int = 0
    signals_3x: int = 0
    signals_5x: int = 0
    signals_10x: int = 0
    signals_20x: int = 0

    # Time-based stats
    last_24h_signals: int = 0
    last_24h_winners: int = 0
    last_7d_signals: int = 0
    last_7d_winners: int = 0

    # Performance metrics
    avg_multiplier: float = 0.0
    best_multiplier: float = 0.0

    @property
    def hit_rate_2x(self) -> float:
        """Percentage of signals that hit 2X."""
        if self.total_signals == 0:
            return 0.0
        return (self.signals_2x / self.total_signals) * 100

    @property
    def hit_rate_5x(self) -> float:
        """Percentage of signals that hit 5X."""
        if self.total_signals == 0:
            return 0.0
        return (self.signals_5x / self.total_signals) * 100

    @property
    def hit_rate_10x(self) -> float:
        """Percentage of signals that hit 10X."""
        if self.total_signals == 0:
            return 0.0
        return (self.signals_10x / self.total_signals) * 100

    @property
    def daily_hit_rate(self) -> float:
        """24h win rate."""
        if self.last_24h_signals == 0:
            return 0.0
        return (self.last_24h_winners / self.last_24h_signals) * 100

    @property
    def weekly_hit_rate(self) -> float:
        """7d win rate."""
        if self.last_7d_signals == 0:
            return 0.0
        return (self.last_7d_winners / self.last_7d_signals) * 100


class SignalPublisher:
    """
    Broadcasts winning signals to public marketing channel.

    This creates the "Top Trades" showcase similar to AstroX,
    demonstrating the bot's performance to attract premium subscribers.

    Usage:
        publisher = SignalPublisher(client, config)
        await publisher.broadcast_winner(signal)
    """

    def __init__(
        self,
        client: "TelegramClient",
        config: BroadcastConfig,
    ) -> None:
        """
        Initialize the signal publisher.

        Args:
            client: Telegram client for sending messages
            config: Broadcast configuration
        """
        self._client = client
        self._config = config
        self._public_channel = None
        self._premium_channel = None
        self._broadcast_queue: list[BroadcastSignal] = []
        self._broadcast_history: list[BroadcastSignal] = []
        self._stats = HitRateStats()
        self._initialized = False

    @property
    def config(self) -> BroadcastConfig:
        """Get broadcast configuration."""
        return self._config

    @property
    def stats(self) -> HitRateStats:
        """Get current hit rate statistics."""
        return self._stats

    async def initialize(self) -> bool:
        """
        Initialize channel connections.

        Returns:
            True if at least one channel was resolved
        """
        success = False

        # Resolve public channel
        if self._config.public_channel_id or self._config.public_channel_username:
            try:
                channel_ref = self._config.public_channel_id or self._config.public_channel_username
                # Convert to int if it's a numeric channel ID
                if channel_ref and channel_ref.lstrip('-').isdigit():
                    channel_ref = int(channel_ref)
                self._public_channel = await self._client.get_entity(channel_ref)
                logger.info(f"✅ Public channel connected: {self._get_channel_name(self._public_channel)}")
                success = True
            except Exception as e:
                logger.warning(f"Could not connect to public channel: {e}")

        # Resolve premium channel
        if self._config.premium_channel_id:
            try:
                premium_ref = self._config.premium_channel_id
                # Convert to int if it's a numeric channel ID
                if premium_ref and premium_ref.lstrip('-').isdigit():
                    premium_ref = int(premium_ref)
                self._premium_channel = await self._client.get_entity(premium_ref)
                logger.info(f"✅ Premium channel connected: {self._get_channel_name(self._premium_channel)}")
                success = True
            except Exception as e:
                logger.warning(f"Could not connect to premium channel: {e}")

        self._initialized = success
        return success

    def _get_channel_name(self, channel) -> str:
        """Get display name of a channel."""
        if hasattr(channel, 'title'):
            return channel.title
        return str(channel)

    async def queue_broadcast(self, signal: BroadcastSignal) -> None:
        """
        Queue a signal for delayed broadcast to public channel.

        Args:
            signal: Signal to broadcast
        """
        if signal.multiplier < self._config.min_multiplier_to_broadcast:
            logger.debug(f"Signal {signal.token_symbol} below broadcast threshold")
            return

        # Update stats
        self._update_stats(signal)

        # Add to history
        self._broadcast_history.append(signal)

        # Broadcast to premium immediately
        if self._premium_channel and self._config.premium_instant_broadcast:
            await self._broadcast_to_premium(signal)

        # Queue for delayed public broadcast
        self._broadcast_queue.append(signal)

        # Schedule delayed broadcast
        asyncio.create_task(self._delayed_broadcast(signal))

        logger.info(
            f"Queued broadcast: ${signal.token_symbol} {signal.multiplier:.1f}X "
            f"(delay: {self._config.broadcast_delay_seconds}s)"
        )

    async def broadcast_immediately(self, signal: BroadcastSignal) -> None:
        """
        Broadcast a signal immediately to all channels.
        Used for major wins (10X+) that deserve immediate attention.

        Args:
            signal: Signal to broadcast
        """
        # Update stats
        self._update_stats(signal)
        self._broadcast_history.append(signal)

        # Broadcast to both channels
        if self._premium_channel:
            await self._broadcast_to_premium(signal)

        if self._public_channel:
            await self._broadcast_to_public(signal)

    def _update_stats(self, signal: BroadcastSignal) -> None:
        """Update hit rate statistics with a new signal."""
        self._stats.total_signals += 1

        if signal.multiplier >= 2:
            self._stats.signals_2x += 1
        if signal.multiplier >= 3:
            self._stats.signals_3x += 1
        if signal.multiplier >= 5:
            self._stats.signals_5x += 1
        if signal.multiplier >= 10:
            self._stats.signals_10x += 1
        if signal.multiplier >= 20:
            self._stats.signals_20x += 1

        # Update best multiplier
        if signal.multiplier > self._stats.best_multiplier:
            self._stats.best_multiplier = signal.multiplier

        # Update average (rolling)
        total = self._stats.total_signals
        old_avg = self._stats.avg_multiplier
        self._stats.avg_multiplier = old_avg + (signal.multiplier - old_avg) / total

    async def _delayed_broadcast(self, signal: BroadcastSignal) -> None:
        """Wait and then broadcast to public channel."""
        await asyncio.sleep(self._config.broadcast_delay_seconds)

        if self._public_channel:
            await self._broadcast_to_public(signal)

        # Remove from queue
        if signal in self._broadcast_queue:
            self._broadcast_queue.remove(signal)

    async def _broadcast_to_public(self, signal: BroadcastSignal) -> None:
        """Broadcast to public marketing channel."""
        if not self._public_channel:
            return

        message = self._format_public_message(signal)

        try:
            await self._client.send_message(
                self._public_channel,
                message,
                parse_mode="markdown",
            )
            logger.info(f"Broadcast to public: ${signal.token_symbol} {signal.multiplier:.1f}X")
        except Exception as e:
            logger.error(f"Failed to broadcast to public channel: {e}")

    async def _broadcast_to_premium(self, signal: BroadcastSignal) -> None:
        """Broadcast to premium channel with full details."""
        if not self._premium_channel:
            return

        message = self._format_premium_message(signal)

        try:
            await self._client.send_message(
                self._premium_channel,
                message,
                parse_mode="markdown",
            )
            logger.info(f"Broadcast to premium: ${signal.token_symbol} {signal.multiplier:.1f}X")
        except Exception as e:
            logger.error(f"Failed to broadcast to premium channel: {e}")

    def _format_public_message(self, signal: BroadcastSignal) -> str:
        """
        Format message for public marketing channel.

        Designed to showcase wins and attract subscribers,
        similar to AstroX Top Trades format.
        """
        emoji = signal.tier_emoji
        tier = signal.tier.value

        # Header with dramatic effect
        if signal.multiplier >= 10:
            header = f"{emoji} **{tier} MONSTER CALL** {emoji}"
        elif signal.multiplier >= 5:
            header = f"{emoji} **{tier} WINNING CALL** {emoji}"
        else:
            header = f"{emoji} **{tier} PROFIT ALERT** {emoji}"

        # Build message
        lines = [
            header,
            "",
            f"Token: **${signal.token_symbol}**",
            f"Multiplier: **{signal.multiplier:.1f}X** ({(signal.multiplier - 1) * 100:.0f}% profit)",
        ]

        # Add FDV if available
        if signal.entry_fdv and signal.current_fdv:
            entry_fdv_str = self._format_fdv(signal.entry_fdv)
            current_fdv_str = self._format_fdv(signal.current_fdv)
            lines.append(f"FDV: {entry_fdv_str} -> {current_fdv_str}")

        # Hold duration
        hold_hrs = signal.hold_duration_hours
        if hold_hrs < 1:
            hold_str = f"{int(hold_hrs * 60)} minutes"
        elif hold_hrs < 24:
            hold_str = f"{hold_hrs:.1f} hours"
        else:
            hold_str = f"{hold_hrs / 24:.1f} days"
        lines.append(f"Hold Time: {hold_str}")

        # Timestamp
        lines.append(f"Called: {signal.entry_time.strftime('%Y-%m-%d %H:%M UTC')}")

        # Hit rate stats
        lines.extend([
            "",
            "═══════════════════════════",
            f"📊 Our Performance:",
            f"• Win Rate (2X+): **{self._stats.hit_rate_2x:.0f}%**",
            f"• Win Rate (5X+): **{self._stats.hit_rate_5x:.0f}%**",
            f"• Best Call: **{self._stats.best_multiplier:.0f}X**",
            f"• Total Signals: {self._stats.total_signals}",
            "═══════════════════════════",
        ])

        # Call to action
        if self._config.include_cta:
            lines.extend([
                "",
                "🔑 **Want INSTANT alerts + Full Details?**",
                "",
                "Premium members receive:",
                "• Instant real-time signals (no delay)",
                "• Full token addresses for sniping",
                "• Entry/exit price levels",
                "• Anti-rug security checks",
                "• KOL/Whale tracking alerts",
                "",
                f"👉 **Join Premium**: @{self._config.bot_username}",
                "",
                f"_Powered by {self._config.bot_name}_",
            ])

        return "\n".join(lines)

    def _format_premium_message(self, signal: BroadcastSignal) -> str:
        """
        Format message for premium channel with full details.

        Premium members get complete information for immediate action.
        """
        emoji = signal.tier_emoji
        tier = signal.tier.value

        header = f"{emoji} **{tier} PROFIT ALERT** {emoji}"

        lines = [
            header,
            "",
            f"Token: **${signal.token_symbol}**",
            f"Address: `{signal.token_address}`",
            f"Multiplier: **{signal.multiplier:.1f}X**",
        ]

        # Add FDV details
        if signal.entry_fdv:
            lines.append(f"Entry FDV: {self._format_fdv(signal.entry_fdv)}")
        if signal.current_fdv:
            lines.append(f"Current FDV: {self._format_fdv(signal.current_fdv)}")

        # Timing
        lines.extend([
            "",
            f"Entry: {signal.entry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Alert: {signal.alert_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Hold: {signal.hold_duration_hours:.1f}h",
        ])

        # Quick links
        lines.extend([
            "",
            "📈 **Quick Links:**",
            f"• [DexScreener](https://dexscreener.com/solana/{signal.token_address})",
            f"• [Birdeye](https://birdeye.so/token/{signal.token_address})",
            f"• [GMGN](https://gmgn.ai/sol/token/{signal.token_address})",
        ])

        return "\n".join(lines)

    def _format_fdv(self, fdv: float) -> str:
        """Format FDV for display."""
        if fdv >= 1_000_000_000:
            return f"${fdv / 1_000_000_000:.1f}B"
        elif fdv >= 1_000_000:
            return f"${fdv / 1_000_000:.1f}M"
        elif fdv >= 1_000:
            return f"${fdv / 1_000:.0f}K"
        else:
            return f"${fdv:.0f}"

    async def broadcast_daily_stats(self) -> None:
        """Broadcast daily performance summary to public channel."""
        if not self._public_channel:
            return

        message = self._format_daily_stats()

        try:
            await self._client.send_message(
                self._public_channel,
                message,
                parse_mode="markdown",
            )
            logger.info("Broadcast daily stats")
        except Exception as e:
            logger.error(f"Failed to broadcast daily stats: {e}")

    def _format_daily_stats(self) -> str:
        """Format daily statistics message."""
        now = datetime.now(timezone.utc)

        lines = [
            "📊 **DAILY PERFORMANCE REPORT**",
            f"_{now.strftime('%Y-%m-%d')}_",
            "",
            "═══════════════════════════",
            "",
            f"📈 **Hit Rates:**",
            f"• 2X+ Win Rate: **{self._stats.hit_rate_2x:.0f}%**",
            f"• 5X+ Win Rate: **{self._stats.hit_rate_5x:.0f}%**",
            f"• 10X+ Win Rate: **{self._stats.hit_rate_10x:.0f}%**",
            "",
            f"🏆 **Achievements:**",
            f"• Total Signals: {self._stats.total_signals}",
            f"• 2X Hits: {self._stats.signals_2x}",
            f"• 5X Hits: {self._stats.signals_5x}",
            f"• 10X Hits: {self._stats.signals_10x}",
            f"• 20X+ Hits: {self._stats.signals_20x}",
            "",
            f"• Best Call: **{self._stats.best_multiplier:.0f}X**",
            f"• Average: {self._stats.avg_multiplier:.1f}X",
            "",
            "═══════════════════════════",
            "",
            "🔑 **Ready to trade like an insider?**",
            "",
            f"👉 Join Premium: @{self._config.bot_username}",
            "",
            f"_Powered by {self._config.bot_name}_",
        ]

        return "\n".join(lines)

    def get_pending_broadcasts(self) -> list[BroadcastSignal]:
        """Get signals pending broadcast."""
        return self._broadcast_queue.copy()

    def get_broadcast_history(self, limit: int = 50) -> list[BroadcastSignal]:
        """Get recent broadcast history."""
        return self._broadcast_history[-limit:]

    def format_stats_message(self) -> str:
        """Format statistics for display."""
        return (
            "📊 **BROADCAST STATISTICS**\n\n"
            f"• Total Signals: {self._stats.total_signals}\n"
            f"• 2X+ Hits: {self._stats.signals_2x} ({self._stats.hit_rate_2x:.0f}%)\n"
            f"• 5X+ Hits: {self._stats.signals_5x} ({self._stats.hit_rate_5x:.0f}%)\n"
            f"• 10X+ Hits: {self._stats.signals_10x} ({self._stats.hit_rate_10x:.0f}%)\n"
            f"• Best Call: {self._stats.best_multiplier:.0f}X\n"
            f"• Avg Multiplier: {self._stats.avg_multiplier:.1f}X\n"
            f"• Pending Broadcasts: {len(self._broadcast_queue)}"
        )
