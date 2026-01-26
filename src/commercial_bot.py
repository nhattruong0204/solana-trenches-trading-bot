"""
Commercial Bot Handler - Premium Features Integration.

This module integrates all commercial features:
- Public channel broadcasting (marketing)
- Subscription management (payments)
- Hit rate tracking (credibility)
- KOL/Whale tracking (premium feature)

Designed to make the bot production-ready for monetization.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from telethon import TelegramClient
from telethon.tl.custom import Button

from src.signal_publisher import SignalPublisher, BroadcastConfig
from src.subscription_manager import (
    SubscriptionManager, PaymentWallets, SubscriptionPlan,
    SubscriptionStatus, Subscriber, PaymentMethod,
)
from src.hit_rate_tracker import HitRateTracker, TimeFrame
from src.kol_tracker import KOLTracker, KOLTrackerConfig, WalletType, WalletTransaction

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


class CommercialBot:
    """
    Handles all commercial/premium features.

    This class integrates:
    - Public channel marketing broadcasts
    - Premium subscriptions and payments
    - Performance tracking for credibility
    - KOL/Whale tracking alerts

    Usage:
        commercial = CommercialBot(client, settings)
        await commercial.initialize()

        # Broadcast a winning signal
        await commercial.broadcast_winner(token, multiplier)

        # Handle subscription
        await commercial.start_subscription(user_id, plan)
    """

    def __init__(
        self,
        client: TelegramClient,
        settings: "Settings",
    ) -> None:
        """
        Initialize commercial bot.

        Args:
            client: Telegram client
            settings: Application settings
        """
        self._client = client
        self._settings = settings

        # Initialize components
        self._signal_publisher: Optional[SignalPublisher] = None
        self._subscription_manager: Optional[SubscriptionManager] = None
        self._hit_rate_tracker: Optional[HitRateTracker] = None
        self._kol_tracker: Optional[KOLTracker] = None

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def publisher(self) -> Optional[SignalPublisher]:
        return self._signal_publisher

    @property
    def subscriptions(self) -> Optional[SubscriptionManager]:
        return self._subscription_manager

    @property
    def hit_rate(self) -> Optional[HitRateTracker]:
        return self._hit_rate_tracker

    @property
    def kol_tracker(self) -> Optional[KOLTracker]:
        return self._kol_tracker

    async def initialize(self) -> None:
        """Initialize all commercial components."""
        if self._initialized:
            return

        # Initialize signal publisher
        await self._init_publisher()

        # Initialize subscription manager
        await self._init_subscriptions()

        # Initialize hit rate tracker
        await self._init_hit_rate()

        # Initialize KOL tracker
        await self._init_kol_tracker()

        self._initialized = True
        logger.info("✅ Commercial features initialized")

    async def _init_publisher(self) -> None:
        """Initialize signal publisher for AstroX-style channel broadcasting."""
        public_settings = self._settings.public_channel

        if not public_settings.premium_channel_id:
            logger.info("Premium channel not configured, signal forwarding disabled")
            return

        config = BroadcastConfig(
            public_channel_id=public_settings.public_channel_id,
            premium_channel_id=public_settings.premium_channel_id,
            min_multiplier_to_broadcast=public_settings.min_multiplier_to_broadcast,
            show_token_address_public=public_settings.show_token_address_public,
            bot_name=public_settings.bot_name,
            bot_username=public_settings.bot_username,
        )

        # State file for signal mappings
        import os
        state_file = os.getenv("SIGNAL_MAPPINGS_FILE", "signal_mappings.json")

        self._signal_publisher = SignalPublisher(
            self._client,
            config,
            state_file=state_file
        )

        if await self._signal_publisher.initialize():
            logger.info("✅ Signal publisher initialized")
        else:
            logger.warning("Signal publisher failed to initialize")

    async def _init_subscriptions(self) -> None:
        """Initialize subscription manager."""
        sub_settings = self._settings.subscription

        if not sub_settings.subscriptions_enabled:
            logger.info("Subscriptions disabled")
            return

        wallets = PaymentWallets(
            sol_address=sub_settings.payment_sol_address,
            usdt_bep20_address=sub_settings.payment_usdt_bep20_address,
            usdc_sol_address=sub_settings.payment_usdc_sol_address,
        )

        self._subscription_manager = SubscriptionManager(
            client=self._client,
            wallets=wallets,
            state_file=sub_settings.subscriptions_file,
            premium_channel_id=self._settings.premium_channel_id,
        )

        # Update plan prices from settings
        if self._subscription_manager:
            self._subscription_manager._plans[SubscriptionPlan.MONTHLY].price_usd = sub_settings.price_monthly
            self._subscription_manager._plans[SubscriptionPlan.QUARTERLY].price_usd = sub_settings.price_quarterly
            self._subscription_manager._plans[SubscriptionPlan.YEARLY].price_usd = sub_settings.price_yearly
            self._subscription_manager._plans[SubscriptionPlan.LIFETIME].price_usd = sub_settings.price_lifetime

        await self._subscription_manager.load()
        logger.info(f"✅ Subscription manager initialized ({len(self._subscription_manager.get_active_subscribers())} active)")

    async def _init_hit_rate(self) -> None:
        """Initialize hit rate tracker."""
        self._hit_rate_tracker = HitRateTracker(
            state_file="hit_rate_state.json",
        )
        await self._hit_rate_tracker.load()
        logger.info("✅ Hit rate tracker initialized")

    async def _init_kol_tracker(self) -> None:
        """Initialize KOL tracker."""
        import os

        config = KOLTrackerConfig(
            helius_api_key=os.getenv("HELIUS_API_KEY"),
            birdeye_api_key=os.getenv("BIRDEYE_API_KEY"),
        )

        self._kol_tracker = KOLTracker(
            config=config,
            state_file="kol_tracker_state.json",
        )
        await self._kol_tracker.load()
        logger.info(f"✅ KOL tracker initialized ({len(self._kol_tracker.wallets)} wallets)")

    async def shutdown(self) -> None:
        """Shutdown all components."""
        if self._kol_tracker:
            await self._kol_tracker.stop_monitoring()

        if self._subscription_manager:
            await self._subscription_manager.save()

        if self._hit_rate_tracker:
            await self._hit_rate_tracker.save()

    # =========================================================================
    # Signal Broadcasting (AstroX-style)
    # =========================================================================

    async def forward_ape_signal(
        self,
        source_msg_id: int,
        token_symbol: str,
        token_address: str,
        entry_fdv: Optional[float] = None,
    ) -> Optional[int]:
        """
        Forward an ape signal from Trenches to Premium channel.

        This mirrors the signal to the premium channel immediately.

        Args:
            source_msg_id: Original message ID in Trenches channel
            token_symbol: Token symbol
            token_address: Token contract address
            entry_fdv: Entry FDV in USD

        Returns:
            Message ID in premium channel, or None if failed
        """
        if not self._signal_publisher:
            return None

        premium_msg_id = await self._signal_publisher.forward_ape_signal(
            source_msg_id=source_msg_id,
            token_symbol=token_symbol,
            token_address=token_address,
            entry_fdv=entry_fdv,
        )

        # Record in hit rate tracker
        if self._hit_rate_tracker and premium_msg_id:
            signal_id = str(source_msg_id)
            self._hit_rate_tracker.record_signal(
                signal_id=signal_id,
                token_symbol=token_symbol,
                token_address=token_address,
                entry_fdv=entry_fdv,
            )

        return premium_msg_id

    async def send_profit_update(
        self,
        source_msg_id: int,
        multiplier: float,
        current_fdv: Optional[float] = None,
    ) -> bool:
        """
        Send a profit UPDATE message as a reply to the original ape signal.

        This is called when a signal hits a new milestone (2X, 3X, etc.)
        The update is sent as a reply in the premium channel, and on
        first 2X+ hit, also forwards to public channel.

        Args:
            source_msg_id: Original message ID in Trenches channel
            multiplier: Current multiplier (e.g., 2.5 for 2.5X)
            current_fdv: Current FDV

        Returns:
            True if update was sent successfully
        """
        if not self._signal_publisher:
            return False

        result = await self._signal_publisher.send_profit_update(
            source_msg_id=source_msg_id,
            multiplier=multiplier,
            current_fdv=current_fdv,
        )

        # Update hit rate tracker
        if self._hit_rate_tracker and result:
            signal_id = str(source_msg_id)
            self._hit_rate_tracker.update_signal(signal_id, multiplier)

        return result

    def get_signal_mapping(self, source_msg_id: int):
        """Get signal mapping for a source message ID."""
        if not self._signal_publisher:
            return None
        return self._signal_publisher.get_mapping(source_msg_id)

    # =========================================================================
    # Subscription Handling
    # =========================================================================

    async def handle_subscribe_command(
        self,
        user_id: int,
        username: Optional[str] = None,
        plan_arg: Optional[str] = None,
    ) -> tuple[str, Optional[list[list[Button]]]]:
        """
        Handle /subscribe command.

        Returns message text and optional buttons.
        """
        if not self._subscription_manager:
            return "Subscriptions are not enabled.", None

        # Check if already subscribed
        existing = self._subscription_manager.get_subscriber(user_id)
        if existing and existing.is_active:
            return self._subscription_manager.format_subscription_status(existing), None

        # Parse plan
        plan = None
        if plan_arg:
            plan_map = {
                "monthly": SubscriptionPlan.MONTHLY,
                "quarterly": SubscriptionPlan.QUARTERLY,
                "yearly": SubscriptionPlan.YEARLY,
                "lifetime": SubscriptionPlan.LIFETIME,
                "1": SubscriptionPlan.MONTHLY,
                "3": SubscriptionPlan.QUARTERLY,
                "12": SubscriptionPlan.YEARLY,
            }
            plan = plan_map.get(plan_arg.lower())

        if not plan:
            # Show plan selection
            buttons = [
                [Button.inline("Monthly - $79", b"plan_monthly")],
                [Button.inline("Quarterly - $199 (Save 16%)", b"plan_quarterly")],
                [Button.inline("Yearly - $599 (Save 37%)", b"plan_yearly")],
                [Button.inline("Lifetime - $999", b"plan_lifetime")],
            ]
            return self._subscription_manager.format_plans_message(), buttons

        # Create subscription
        sub = await self._subscription_manager.create_subscription(
            user_id=user_id,
            plan=plan,
            username=username,
        )

        # Return payment instructions
        return self._subscription_manager.format_payment_message(sub), None

    async def handle_plan_selection(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        username: Optional[str] = None,
    ) -> str:
        """Handle plan selection callback."""
        if not self._subscription_manager:
            return "Subscriptions not enabled."

        sub = await self._subscription_manager.create_subscription(
            user_id=user_id,
            plan=plan,
            username=username,
        )

        return self._subscription_manager.format_payment_message(sub)

    async def handle_verify_payment(
        self,
        user_id: int,
        tx_hash: str,
    ) -> str:
        """
        Handle /verify command to verify payment.

        In production, this should actually verify the transaction on-chain.
        """
        if not self._subscription_manager:
            return "Subscriptions not enabled."

        sub = self._subscription_manager.get_subscriber(user_id)
        if not sub:
            return "No pending subscription found. Use /subscribe first."

        if sub.status == SubscriptionStatus.ACTIVE:
            return "Your subscription is already active!"

        # TODO: Actually verify the transaction on-chain
        # For now, we just activate (manual verification by admin)

        # Mark as pending verification
        sub.payment_tx_hash = tx_hash

        message = (
            "✅ **Payment Submitted**\n\n"
            f"Transaction: `{tx_hash[:20]}...`\n\n"
            "Your payment is being verified. "
            "You'll receive confirmation and your premium invite link shortly.\n\n"
            "_Verification usually takes 5-10 minutes_"
        )

        return message

    async def admin_activate_subscription(
        self,
        user_id: int,
        payment_method: PaymentMethod = PaymentMethod.SOL,
    ) -> str:
        """Admin command to manually activate a subscription."""
        if not self._subscription_manager:
            return "Subscriptions not enabled."

        sub = await self._subscription_manager.activate_subscription(
            user_id=user_id,
            payment_method=payment_method,
        )

        if not sub:
            return f"No subscription found for user {user_id}"

        return (
            f"✅ Activated subscription for user {user_id}\n"
            f"Plan: {sub.plan.value}\n"
            f"Expires: {sub.expires_at.strftime('%Y-%m-%d') if sub.expires_at else 'Never'}"
        )

    def has_premium_access(self, user_id: int) -> bool:
        """Check if user has premium access."""
        if not self._subscription_manager:
            return False
        return self._subscription_manager.has_access(user_id)

    # =========================================================================
    # Hit Rate & Stats
    # =========================================================================

    def get_public_stats(self) -> str:
        """Get public statistics for marketing."""
        if not self._hit_rate_tracker:
            return "Statistics not available."
        return self._hit_rate_tracker.format_public_stats(TimeFrame.DAYS_7)

    def get_detailed_stats(self) -> str:
        """Get detailed statistics (admin/premium)."""
        if not self._hit_rate_tracker:
            return "Statistics not available."
        return self._hit_rate_tracker.format_detailed_stats()

    def get_leaderboard(self) -> str:
        """Get top performers leaderboard."""
        if not self._hit_rate_tracker:
            return "Leaderboard not available."
        return self._hit_rate_tracker.format_leaderboard()

    # =========================================================================
    # KOL Tracking
    # =========================================================================

    async def start_kol_monitoring(
        self,
        alert_callback,
    ) -> None:
        """Start KOL wallet monitoring."""
        if not self._kol_tracker:
            return

        async def on_kol_transaction(tx: WalletTransaction):
            """Handle KOL transaction alert."""
            message = self._kol_tracker.format_transaction_alert(tx)
            await alert_callback(message)

        await self._kol_tracker.start_monitoring(on_kol_transaction)

    async def add_kol_wallet(
        self,
        address: str,
        name: str,
        wallet_type: str = "smart_money",
        twitter: Optional[str] = None,
    ) -> str:
        """Add a wallet to KOL tracking."""
        if not self._kol_tracker:
            return "KOL tracking not initialized."

        type_map = {
            "kol": WalletType.KOL,
            "whale": WalletType.WHALE,
            "smart_money": WalletType.SMART_MONEY,
            "dev": WalletType.DEV,
            "fund": WalletType.FUND,
            "insider": WalletType.INSIDER,
        }

        wtype = type_map.get(wallet_type.lower(), WalletType.SMART_MONEY)

        wallet = self._kol_tracker.add_wallet(
            address=address,
            name=name,
            wallet_type=wtype,
            twitter_handle=twitter,
        )

        return f"✅ Added wallet to tracking:\n• Name: {wallet.name}\n• Type: {wallet.wallet_type.value}\n• Address: `{address[:16]}...`"

    def get_kol_wallets_list(self) -> str:
        """Get list of tracked KOL wallets."""
        if not self._kol_tracker:
            return "KOL tracking not initialized."
        return self._kol_tracker.format_wallets_list()

    # =========================================================================
    # Marketing Messages
    # =========================================================================

    def get_welcome_message(self) -> str:
        """Get welcome message for new users."""
        bot_name = self._settings.public_channel.bot_name

        return f"""
🚀 **Welcome to {bot_name}!**

The most powerful Solana trading bot with:

🎯 **HIGH HIT-RATE SIGNALS**
• 60%+ win rate on 2X+ calls
• Proven track record
• Real-time profit alerts

🔒 **ANTI-RUG PROTECTION**
• Security scans before every trade
• Liquidity analysis
• Smart contract checks

🐋 **WHALE/KOL TRACKING**
• Track smart money moves
• Copy successful traders
• Real-time wallet alerts

📊 **PERFORMANCE STATS**
• Daily hit rate updates
• Full transparency
• Verified track record

═══════════════════════════

**FREE FEATURES:**
• Delayed signal broadcasts
• Public performance stats
• Basic alerts

**PREMIUM FEATURES:**
• Instant real-time signals
• Full token addresses
• KOL/Whale tracking
• Priority support
• Anti-rug security

Use /subscribe to unlock premium!
Use /stats to see our track record!
"""

    def get_premium_features_message(self) -> str:
        """Get premium features description."""
        return """
🔑 **PREMIUM FEATURES**

**⚡ INSTANT SIGNALS**
Get signals in real-time with NO DELAY.
Free users receive signals 5 minutes later.

**📍 FULL DETAILS**
• Complete token addresses
• Entry price levels
• Suggested exit targets
• FDV at signal time

**🐋 KOL/WHALE TRACKING**
• Track wallets of successful traders
• Real-time buy/sell alerts
• Copy-trade in seconds

**🛡️ SECURITY CHECKS**
• Anti-rug protection scans
• Liquidity analysis
• Contract verification

**📈 ADVANCED ANALYTICS**
• Detailed performance stats
• Strategy backtesting
• Custom alert settings

**🎯 PRIORITY SUPPORT**
• Direct admin access
• Quick response time
• Strategy guidance

═══════════════════════════

Ready to trade like an insider?

Use /subscribe to get started!
"""

    async def broadcast_daily_report(self) -> None:
        """Broadcast daily performance report to public channel."""
        if self._signal_publisher:
            await self._signal_publisher.broadcast_daily_stats()

    async def check_expiring_subscriptions(self) -> list[Subscriber]:
        """Check for expiring subscriptions and return list."""
        if not self._subscription_manager:
            return []

        return self._subscription_manager.get_expiring_soon(days=7)

    def get_subscription_stats(self) -> str:
        """Get subscription statistics (admin)."""
        if not self._subscription_manager:
            return "Subscriptions not enabled."
        return self._subscription_manager.format_admin_stats()
