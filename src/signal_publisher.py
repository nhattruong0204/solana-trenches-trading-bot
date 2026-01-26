"""
Signal Publisher - AstroX-style Channel Broadcasting.

This module implements the same broadcasting pattern as AstroX Hub:
1. Premium Channel: Mirror of Trenches signals + profit update replies
2. Public Channel: Only winning signals (2X+) with CTA for marketing

Flow:
1. New signal from Trenches -> Forward to Premium channel immediately
2. Profit alert (2X, 3X, etc.) -> Send UPDATE as REPLY to the original in Premium
3. First 2X+ hit -> Forward ape signal + update to Public channel with CTA
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import Message

logger = logging.getLogger(__name__)


# Rotating CTA messages like AstroX uses
CTA_MESSAGES = [
    "✨ **Your Silent Edge in Memes Trading**",
    "☄️ **This play went LIVE in Pro hub before volume exploded**",
    "📊 **Premium members received this entry in Real-time**",
    "🚫 **Rug pulls are filtered out by our rug-counter system**",
    "👁‍🗨 **Seeing KOL,Whale's real time transactions on Memes → Instant Automated Copy Trading**",
    "⚡ **Real-time signals. No delays. Maximum alpha.**",
    "🎯 **Precision entries that the public never sees**",
    "🔮 **The future of memecoin trading is automated**",
]


@dataclass
class BroadcastConfig:
    """Configuration for channel broadcasting."""

    # Channel IDs
    public_channel_id: Optional[str] = None
    premium_channel_id: Optional[str] = None
    source_channel_id: Optional[str] = None  # Trenches channel to mirror

    # Broadcast settings
    min_multiplier_to_broadcast: float = 2.0
    show_token_address_public: bool = False

    # Branding
    bot_name: str = "SolSleuth"
    bot_username: str = "SolSleuthBot"
    premium_channel_link: str = ""


@dataclass
class SignalMapping:
    """Maps source signal to premium channel message for replies."""

    source_msg_id: int  # Message ID in Trenches channel
    premium_msg_id: int  # Message ID in Premium channel
    public_msg_id: Optional[int] = None  # Message ID in Public channel (if forwarded)
    token_symbol: str = ""
    token_address: str = ""
    entry_fdv: Optional[float] = None
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_multiplier: float = 1.0
    last_update_multiplier: float = 0.0  # Last multiplier we sent an update for
    forwarded_to_public: bool = False
    raw_message: str = ""  # Original raw message text for forwarding to public

    def to_dict(self) -> dict:
        return {
            "source_msg_id": self.source_msg_id,
            "premium_msg_id": self.premium_msg_id,
            "public_msg_id": self.public_msg_id,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "entry_fdv": self.entry_fdv,
            "entry_time": self.entry_time.isoformat(),
            "current_multiplier": self.current_multiplier,
            "last_update_multiplier": self.last_update_multiplier,
            "forwarded_to_public": self.forwarded_to_public,
            "raw_message": self.raw_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignalMapping":
        entry_time = data.get("entry_time")
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        elif entry_time is None:
            entry_time = datetime.now(timezone.utc)

        return cls(
            source_msg_id=data["source_msg_id"],
            premium_msg_id=data["premium_msg_id"],
            public_msg_id=data.get("public_msg_id"),
            token_symbol=data.get("token_symbol", ""),
            token_address=data.get("token_address", ""),
            entry_fdv=data.get("entry_fdv"),
            entry_time=entry_time,
            current_multiplier=data.get("current_multiplier", 1.0),
            last_update_multiplier=data.get("last_update_multiplier", 0.0),
            forwarded_to_public=data.get("forwarded_to_public", False),
            raw_message=data.get("raw_message", ""),
        )


class SignalPublisher:
    """
    AstroX-style signal broadcasting system.

    Premium Channel:
    - Mirrors all ape signals from Trenches
    - Sends profit UPDATE messages as replies to original signals

    Public Channel:
    - Only shows winning signals (2X+)
    - Forwards ape signal + update on first significant win
    - Includes CTA to join premium
    """

    def __init__(
        self,
        client: "TelegramClient",
        config: BroadcastConfig,
        state_file: str = "signal_mappings.json",
    ) -> None:
        self._client = client
        self._config = config
        self._state_file = Path(state_file)

        self._public_channel = None
        self._premium_channel = None
        self._initialized = False

        # Signal mappings: source_msg_id -> SignalMapping
        self._mappings: dict[int, SignalMapping] = {}

    @property
    def config(self) -> BroadcastConfig:
        return self._config

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self) -> bool:
        """Initialize channel connections and load state."""
        success = False

        # Load existing mappings
        await self._load_state()

        # Connect to public channel
        if self._config.public_channel_id:
            try:
                channel_ref = self._config.public_channel_id
                if channel_ref.lstrip('-').isdigit():
                    channel_ref = int(channel_ref)
                self._public_channel = await self._client.get_entity(channel_ref)
                logger.info(f"✅ Public channel connected: {self._get_channel_name(self._public_channel)}")
                success = True
            except Exception as e:
                logger.warning(f"Could not connect to public channel: {e}")

        # Connect to premium channel
        if self._config.premium_channel_id:
            try:
                premium_ref = self._config.premium_channel_id
                if premium_ref.lstrip('-').isdigit():
                    premium_ref = int(premium_ref)
                self._premium_channel = await self._client.get_entity(premium_ref)
                logger.info(f"✅ Premium channel connected: {self._get_channel_name(self._premium_channel)}")
                success = True
            except Exception as e:
                logger.warning(f"Could not connect to premium channel: {e}")

        self._initialized = success
        return success

    def _get_channel_name(self, channel) -> str:
        if hasattr(channel, 'title'):
            return channel.title
        return str(channel)

    async def _load_state(self) -> None:
        """Load signal mappings from file."""
        if not self._state_file.exists():
            return

        try:
            with open(self._state_file, 'r') as f:
                data = json.load(f)
                for key, value in data.items():
                    self._mappings[int(key)] = SignalMapping.from_dict(value)
            logger.info(f"Loaded {len(self._mappings)} signal mappings")
        except Exception as e:
            logger.error(f"Failed to load signal mappings: {e}")

    async def _save_state(self) -> None:
        """Save signal mappings to file."""
        try:
            data = {str(k): v.to_dict() for k, v in self._mappings.items()}
            with open(self._state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save signal mappings: {e}")

    # =========================================================================
    # MESSAGE MIRRORING (Trenches -> Premium - ALL Messages)
    # =========================================================================

    async def mirror_message(
        self,
        source_msg_id: int,
        raw_message: str,
        reply_to_source_id: Optional[int] = None,
        is_signal: bool = False,
        token_symbol: str = "",
        token_address: str = "",
        entry_fdv: Optional[float] = None,
    ) -> Optional[int]:
        """
        Mirror ANY message from Trenches to Premium channel exactly.

        This forwards ALL messages (not just signals) to create a full mirror.
        If it's a reply message in source, it will be a reply in Premium too.

        Args:
            source_msg_id: Original message ID in Trenches channel
            raw_message: Original message text (forwarded as-is)
            reply_to_source_id: If this is a reply, the source msg ID it replies to
            is_signal: Whether this is an ape signal (for tracking)
            token_symbol: Token symbol if it's a signal
            token_address: Token address if it's a signal
            entry_fdv: Entry FDV if it's a signal

        Returns:
            Message ID in premium channel, or None if failed
        """
        if not self._premium_channel:
            logger.debug("Premium channel not configured, skipping mirror")
            return None

        # Check if already mirrored
        if source_msg_id in self._mappings:
            logger.debug(f"Message {source_msg_id} already mirrored")
            return self._mappings[source_msg_id].premium_msg_id

        try:
            # Determine reply_to for premium channel
            reply_to_premium_id = None
            if reply_to_source_id and reply_to_source_id in self._mappings:
                reply_to_premium_id = self._mappings[reply_to_source_id].premium_msg_id

            # Forward the message as-is (raw text)
            sent = await self._client.send_message(
                self._premium_channel,
                raw_message,
                reply_to=reply_to_premium_id,
                parse_mode=None,  # Preserve original formatting
            )

            # Create mapping (for both signals and general messages)
            mapping = SignalMapping(
                source_msg_id=source_msg_id,
                premium_msg_id=sent.id,
                token_symbol=token_symbol,
                token_address=token_address,
                entry_fdv=entry_fdv,
                entry_time=datetime.now(timezone.utc),
                raw_message=raw_message,  # Store for public channel forwarding
            )
            self._mappings[source_msg_id] = mapping

            # Save state
            asyncio.create_task(self._save_state())

            if is_signal:
                logger.info(f"📨 Mirrored signal ${token_symbol} to Premium (msg:{sent.id})")
            else:
                logger.debug(f"📨 Mirrored message to Premium (msg:{sent.id})")

            return sent.id

        except Exception as e:
            logger.error(f"Failed to mirror message: {e}")
            return None

    # =========================================================================
    # APE SIGNAL FORWARDING (Legacy - kept for backward compatibility)
    # =========================================================================

    async def forward_ape_signal(
        self,
        source_msg_id: int,
        token_symbol: str,
        token_address: str,
        entry_fdv: Optional[float] = None,
        raw_message: str = "",
    ) -> Optional[int]:
        """
        Forward an ape signal from Trenches to Premium channel.

        NOTE: This is the legacy method that reformats the signal.
        For full mirroring, use mirror_message() instead.

        Args:
            source_msg_id: Original message ID in Trenches channel
            token_symbol: Token symbol (e.g., $PEPE)
            token_address: Token contract address
            entry_fdv: Entry FDV in USD
            raw_message: Original message text

        Returns:
            Message ID in premium channel, or None if failed
        """
        if not self._premium_channel:
            logger.debug("Premium channel not configured, skipping forward")
            return None

        # Check if already forwarded
        if source_msg_id in self._mappings:
            logger.debug(f"Signal {source_msg_id} already forwarded")
            return self._mappings[source_msg_id].premium_msg_id

        # Format the ape signal message for premium channel
        message = self._format_ape_signal(
            token_symbol=token_symbol,
            token_address=token_address,
            entry_fdv=entry_fdv,
        )

        try:
            sent = await self._client.send_message(
                self._premium_channel,
                message,
                parse_mode="markdown",
            )

            # Create mapping
            mapping = SignalMapping(
                source_msg_id=source_msg_id,
                premium_msg_id=sent.id,
                token_symbol=token_symbol,
                token_address=token_address,
                entry_fdv=entry_fdv,
                entry_time=datetime.now(timezone.utc),
            )
            self._mappings[source_msg_id] = mapping

            # Save state
            asyncio.create_task(self._save_state())

            logger.info(f"📨 Forwarded ${token_symbol} to Premium (msg:{sent.id})")
            return sent.id

        except Exception as e:
            logger.error(f"Failed to forward ape signal: {e}")
            return None

    def _format_ape_signal(
        self,
        token_symbol: str,
        token_address: str,
        entry_fdv: Optional[float] = None,
    ) -> str:
        """Format ape signal message like AstroX."""
        # Format FDV
        fdv_str = self._format_fdv(entry_fdv) if entry_fdv else "N/A"

        lines = [
            f"🔹`${token_symbol}` - SOL",
            "",
            f"**Entry:** **{fdv_str}**",
            "",
            f"**Chart:** [MevX](https://mevx.io/solana/{token_address}) - [gmgn](https://gmgn.ai/sol/token/{token_address})",
            "",
            f"`{token_address}`",
            "",
            f"🔸**{self._config.bot_name} LIVE Trading**🔸",
        ]

        return "\n".join(lines)

    # =========================================================================
    # PROFIT UPDATE HANDLING (Track multipliers and forward winners to Public)
    # =========================================================================

    async def send_profit_update(
        self,
        source_msg_id: int,
        multiplier: float,
        current_fdv: Optional[float] = None,
        profit_alert_raw: str = "",
    ) -> bool:
        """
        Handle a profit alert and forward winners to Public channel.

        NOTE: With mirroring enabled, profit alerts are already sent to Premium
        channel as raw messages. This method only:
        1. Tracks the multiplier milestone
        2. Forwards to Public channel when 2X+ is hit

        Args:
            source_msg_id: Original SIGNAL message ID in Trenches channel
            multiplier: Current multiplier (e.g., 2.5 for 2.5X)
            current_fdv: Current FDV
            profit_alert_raw: Raw profit alert message text

        Returns:
            True if forwarded to public successfully or milestone tracked
        """
        # Get the mapping for the original signal
        mapping = self._mappings.get(source_msg_id)
        if not mapping:
            logger.warning(f"No mapping found for source message {source_msg_id}")
            return False

        # Only process if this is a signal (has token info)
        if not mapping.token_symbol:
            logger.debug(f"Message {source_msg_id} is not a signal, skipping profit update")
            return False

        # Update current multiplier
        old_multiplier = mapping.current_multiplier
        mapping.current_multiplier = multiplier

        # Check if we hit a new milestone
        milestone = self._get_milestone(multiplier)
        last_milestone = self._get_milestone(mapping.last_update_multiplier)

        if milestone > last_milestone:
            mapping.last_update_multiplier = multiplier
            logger.info(f"📈 ${mapping.token_symbol} hit {milestone}X milestone")

        # Check if we should forward to public channel (first 2X+ hit)
        if multiplier >= self._config.min_multiplier_to_broadcast and not mapping.forwarded_to_public:
            # Calculate hold time
            hold_time = datetime.now(timezone.utc) - mapping.entry_time
            hold_str = self._format_hold_time(hold_time)

            success = await self._forward_win_to_public(
                mapping=mapping,
                multiplier=multiplier,
                current_fdv=current_fdv,
                hold_time=hold_str,
                profit_alert_raw=profit_alert_raw,
            )
            if success:
                mapping.forwarded_to_public = True

        # Save state
        asyncio.create_task(self._save_state())
        return True

    def _format_profit_update(
        self,
        token_symbol: str,
        multiplier: float,
        entry_fdv: Optional[float],
        current_fdv: Optional[float],
        hold_time: str,
    ) -> str:
        """Format profit UPDATE message like AstroX."""
        milestone = int(multiplier)
        entry_str = self._format_fdv(entry_fdv) if entry_fdv else "N/A"
        ath_str = self._format_fdv(current_fdv) if current_fdv else "N/A"

        # Calculate PnL based on $100 investment
        pnl_start = 100
        pnl_end = int(pnl_start * multiplier)
        pnl_profit = pnl_end - pnl_start

        # Get random CTA message
        cta = random.choice(CTA_MESSAGES)

        lines = [
            f"🔹 **UPDATE:** `${token_symbol}` - **SOL**",
            "",
            f"🚩 **{milestone}X Hit From Entry**",
            "",
            f"💶 **PnL:** ${pnl_start} → ${pnl_end:,}  (PnL +${pnl_profit:,})",
            "",
            f"🔖 **Entry:** {entry_str}",
            f"📈 **ATH:** {ath_str}",
            "",
            f"📋 **ROI:** {milestone}x",
            f"⌛️ **Time:** {hold_time}",
            f"⛓️ **Chain:** SOL",
            "",
            cta,
            "",
            f"🔸 **{self._config.bot_name} Pro Trading** 🔸",
        ]

        return "\n".join(lines)

    def _get_milestone(self, multiplier: float) -> int:
        """Get the milestone tier for a multiplier."""
        if multiplier >= 100:
            return 100
        elif multiplier >= 50:
            return 50
        elif multiplier >= 20:
            return 20
        elif multiplier >= 10:
            return 10
        elif multiplier >= 5:
            return 5
        elif multiplier >= 4:
            return 4
        elif multiplier >= 3:
            return 3
        elif multiplier >= 2:
            return 2
        else:
            return 0

    # =========================================================================
    # PUBLIC CHANNEL (Marketing - Winners Only)
    # =========================================================================

    async def _forward_win_to_public(
        self,
        mapping: SignalMapping,
        multiplier: float,
        current_fdv: Optional[float],
        hold_time: str,
        profit_alert_raw: str = "",
    ) -> bool:
        """
        Forward a winning signal to the public channel.

        This is called on the first 2X+ hit.
        Forwards: Raw ape signal + Raw profit alert + CTA

        Args:
            mapping: The signal mapping with original message info
            multiplier: Current multiplier
            current_fdv: Current FDV
            hold_time: Formatted hold time string
            profit_alert_raw: Raw profit alert message text
        """
        if not self._public_channel:
            logger.debug("Public channel not configured, skipping forward to public")
            return False

        if mapping.forwarded_to_public:
            return False

        try:
            # 1. Send the raw ape signal first (or formatted if raw not available)
            if mapping.raw_message:
                # Use raw message from source
                sent_ape = await self._client.send_message(
                    self._public_channel,
                    mapping.raw_message,
                    parse_mode=None,  # Raw text
                )
            else:
                # Fallback to formatted message
                ape_msg = self._format_ape_signal_public(
                    token_symbol=mapping.token_symbol,
                    token_address=mapping.token_address if self._config.show_token_address_public else None,
                    entry_fdv=mapping.entry_fdv,
                )
                sent_ape = await self._client.send_message(
                    self._public_channel,
                    ape_msg,
                    parse_mode="markdown",
                )

            mapping.public_msg_id = sent_ape.id

            # 2. Send the profit alert as reply (raw if available, else formatted)
            if profit_alert_raw:
                # Use raw profit alert message
                await self._client.send_message(
                    self._public_channel,
                    profit_alert_raw,
                    reply_to=sent_ape.id,
                    parse_mode=None,  # Raw text
                )
            else:
                # Fallback to formatted update
                update_msg = self._format_profit_update_public(
                    token_symbol=mapping.token_symbol,
                    multiplier=multiplier,
                    entry_fdv=mapping.entry_fdv,
                    current_fdv=current_fdv,
                    hold_time=hold_time,
                )
                await self._client.send_message(
                    self._public_channel,
                    update_msg,
                    reply_to=sent_ape.id,
                    parse_mode="markdown",
                )

            # 3. Send CTA message
            cta_msg = self._format_cta_message(
                token_symbol=mapping.token_symbol,
                multiplier=multiplier,
            )
            await self._client.send_message(
                self._public_channel,
                cta_msg,
                reply_to=sent_ape.id,
                parse_mode="markdown",
            )

            logger.info(f"🎯 Forwarded ${mapping.token_symbol} {int(multiplier)}X win to Public channel")
            return True

        except Exception as e:
            logger.error(f"Failed to forward win to public channel: {e}")
            return False

    def _format_cta_message(
        self,
        token_symbol: str,
        multiplier: float,
    ) -> str:
        """Format CTA message for public channel."""
        cta = random.choice(CTA_MESSAGES)
        milestone = int(multiplier)

        lines = [
            "═══════════════════════════",
            "",
            f"🚀 **${token_symbol} just hit {milestone}X!**",
            "",
            cta,
            "",
            "🔑 **Want REAL-TIME signals?**",
            "",
            "Premium members receive:",
            "• ⚡ Instant signals (no delay)",
            "• 📋 Full token addresses",
            "• 🐋 KOL/Whale tracking",
            "• 🛡️ Anti-rug protection",
            "",
        ]

        # Add premium channel link if configured
        if self._config.premium_channel_link:
            lines.append(f"👉 **Join Premium:** {self._config.premium_channel_link}")
        else:
            lines.append(f"👉 **Contact:** @{self._config.bot_username}")

        lines.extend([
            "",
            f"🔸 **{self._config.bot_name} Pro** 🔸",
        ])

        return "\n".join(lines)

    def _format_ape_signal_public(
        self,
        token_symbol: str,
        token_address: Optional[str],
        entry_fdv: Optional[float],
    ) -> str:
        """Format ape signal for public channel (may hide address)."""
        fdv_str = self._format_fdv(entry_fdv) if entry_fdv else "N/A"

        lines = [
            f"🔹`${token_symbol}` - SOL",
            "",
            f"**Entry:** **{fdv_str}**",
            "",
        ]

        if token_address:
            lines.extend([
                f"**Chart:** [gmgn](https://gmgn.ai/sol/token/{token_address})",
                "",
                f"`{token_address}`",
            ])
        else:
            lines.append("_Token address available for Premium members_")

        lines.extend([
            "",
            f"🔸**{self._config.bot_name} Trading**🔸",
        ])

        return "\n".join(lines)

    def _format_profit_update_public(
        self,
        token_symbol: str,
        multiplier: float,
        entry_fdv: Optional[float],
        current_fdv: Optional[float],
        hold_time: str,
    ) -> str:
        """Format profit update for public channel with CTA."""
        milestone = int(multiplier)
        entry_str = self._format_fdv(entry_fdv) if entry_fdv else "N/A"
        ath_str = self._format_fdv(current_fdv) if current_fdv else "N/A"

        pnl_start = 100
        pnl_end = int(pnl_start * multiplier)
        pnl_profit = pnl_end - pnl_start

        cta = random.choice(CTA_MESSAGES)

        lines = [
            f"🔹 **UPDATE:** `${token_symbol}` - **SOL**",
            "",
            f"🚩 **{milestone}X Hit From Entry**",
            "",
            f"💶 **PnL:** ${pnl_start} → ${pnl_end:,}  (PnL +${pnl_profit:,})",
            "",
            f"🔖 **Entry:** {entry_str}",
            f"📈 **ATH:** {ath_str}",
            "",
            f"📋 **ROI:** {milestone}x",
            f"⌛️ **Time:** {hold_time}",
            f"⛓️ **Chain:** SOL",
            "",
            cta,
            "",
            "═══════════════════════════",
            "",
            "🔑 **Want INSTANT signals + Full token addresses?**",
            "",
            "Premium members receive:",
            "• ⚡ Real-time signals (no delay)",
            "• 📋 Full token addresses for sniping",
            "• 🐋 KOL/Whale tracking alerts",
            "• 🛡️ Anti-rug protection",
            "",
        ]

        # Add premium channel link if configured
        if self._config.premium_channel_link:
            lines.append(f"👉 **Join Premium:** {self._config.premium_channel_link}")
        else:
            lines.append(f"👉 **Join Premium:** @{self._config.bot_username}")

        lines.extend([
            "",
            f"🔸 **{self._config.bot_name} Pro Trading** 🔸",
        ])

        return "\n".join(lines)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _format_fdv(self, fdv: Optional[float]) -> str:
        """Format FDV for display."""
        if fdv is None:
            return "N/A"
        if fdv >= 1_000_000_000:
            return f"${fdv / 1_000_000_000:.1f}B"
        elif fdv >= 1_000_000:
            return f"${fdv / 1_000_000:.1f}M"
        elif fdv >= 1_000:
            return f"${fdv / 1_000:.0f}K"
        else:
            return f"${fdv:.0f}"

    def _format_hold_time(self, delta: timedelta) -> str:
        """Format hold time for display."""
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)} Min"
        elif hours < 24:
            return f"{int(hours)} Hour" if int(hours) == 1 else f"{int(hours)} Hours"
        else:
            days = int(hours / 24)
            return f"{days} Day" if days == 1 else f"{days} Days"

    def get_mapping(self, source_msg_id: int) -> Optional[SignalMapping]:
        """Get mapping for a source message ID."""
        return self._mappings.get(source_msg_id)

    def get_stats(self) -> dict:
        """Get publisher statistics."""
        total = len(self._mappings)
        forwarded = sum(1 for m in self._mappings.values() if m.forwarded_to_public)
        winners = sum(1 for m in self._mappings.values() if m.current_multiplier >= 2)

        return {
            "total_signals": total,
            "forwarded_to_public": forwarded,
            "winners_2x": winners,
            "win_rate": (winners / total * 100) if total > 0 else 0,
        }
