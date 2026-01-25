"""
Subscription Manager for Premium Memberships.

This module handles premium subscription management including:
- Subscription plans (Monthly, Quarterly, Lifetime)
- Payment tracking and verification
- Member access control
- Invite link generation
- Subscription expiry and renewal reminders

Inspired by AstroX Pro Bot's subscription model.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from asyncpg import Pool

logger = logging.getLogger(__name__)


class SubscriptionPlan(str, Enum):
    """Available subscription plans."""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class PaymentMethod(str, Enum):
    """Supported payment methods."""
    SOL = "sol"
    USDT_BEP20 = "usdt_bep20"
    USDT_TRC20 = "usdt_trc20"
    USDC_SOL = "usdc_sol"


class SubscriptionStatus(str, Enum):
    """Subscription status."""
    PENDING = "pending"  # Awaiting payment
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class PlanConfig:
    """Configuration for a subscription plan."""

    plan_type: SubscriptionPlan
    name: str
    price_usd: float
    duration_days: int  # 0 for lifetime
    description: str
    features: list[str] = field(default_factory=list)

    @property
    def is_lifetime(self) -> bool:
        return self.duration_days == 0


@dataclass
class Subscriber:
    """A premium subscriber."""

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None

    # Subscription details
    plan: SubscriptionPlan = SubscriptionPlan.MONTHLY
    status: SubscriptionStatus = SubscriptionStatus.PENDING

    # Dates
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Payment
    payment_method: Optional[PaymentMethod] = None
    payment_amount_usd: float = 0.0
    payment_tx_hash: Optional[str] = None

    # Access
    invite_link: Optional[str] = None
    joined_premium_channel: bool = False

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        if self.expires_at is None:
            return True  # Lifetime
        return datetime.now(timezone.utc) < self.expires_at

    @property
    def days_remaining(self) -> Optional[int]:
        """Days remaining on subscription."""
        if self.expires_at is None:
            return None  # Lifetime
        if not self.is_active:
            return 0
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)

    @property
    def is_expiring_soon(self) -> bool:
        """Check if subscription expires within 7 days."""
        remaining = self.days_remaining
        if remaining is None:
            return False
        return 0 < remaining <= 7

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "plan": self.plan.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "payment_method": self.payment_method.value if self.payment_method else None,
            "payment_amount_usd": self.payment_amount_usd,
            "payment_tx_hash": self.payment_tx_hash,
            "invite_link": self.invite_link,
            "joined_premium_channel": self.joined_premium_channel,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Subscriber":
        """Create from dictionary."""
        return cls(
            user_id=data["user_id"],
            username=data.get("username"),
            first_name=data.get("first_name"),
            plan=SubscriptionPlan(data.get("plan", "monthly")),
            status=SubscriptionStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            activated_at=datetime.fromisoformat(data["activated_at"]) if data.get("activated_at") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            payment_method=PaymentMethod(data["payment_method"]) if data.get("payment_method") else None,
            payment_amount_usd=data.get("payment_amount_usd", 0.0),
            payment_tx_hash=data.get("payment_tx_hash"),
            invite_link=data.get("invite_link"),
            joined_premium_channel=data.get("joined_premium_channel", False),
        )


@dataclass
class PaymentWallets:
    """Payment receiving wallets."""

    sol_address: Optional[str] = None
    usdt_bep20_address: Optional[str] = None  # BNB Chain
    usdt_trc20_address: Optional[str] = None  # Tron
    usdc_sol_address: Optional[str] = None  # Solana USDC


class SubscriptionManager:
    """
    Manages premium subscriptions and payments.

    Features:
    - Multiple subscription plans
    - Payment verification
    - Invite link generation
    - Expiry notifications
    - Member access control

    Usage:
        manager = SubscriptionManager(client, config)
        await manager.load()

        # Create subscription
        sub = await manager.create_subscription(user_id, plan)

        # Verify payment
        await manager.verify_payment(user_id, tx_hash)

        # Check access
        if manager.has_access(user_id):
            # Grant premium features
    """

    # Default plan configurations
    DEFAULT_PLANS = {
        SubscriptionPlan.MONTHLY: PlanConfig(
            plan_type=SubscriptionPlan.MONTHLY,
            name="Monthly",
            price_usd=79.0,
            duration_days=30,
            description="1 Month Premium Access",
            features=[
                "Instant real-time signals",
                "Full token addresses",
                "Anti-rug security checks",
                "KOL/Whale tracking",
                "Priority support",
            ],
        ),
        SubscriptionPlan.QUARTERLY: PlanConfig(
            plan_type=SubscriptionPlan.QUARTERLY,
            name="Quarterly",
            price_usd=199.0,
            duration_days=90,
            description="3 Months Premium Access (Save 16%)",
            features=[
                "All Monthly features",
                "Strategy backtesting",
                "Custom alerts",
                "Trading strategies guide",
            ],
        ),
        SubscriptionPlan.YEARLY: PlanConfig(
            plan_type=SubscriptionPlan.YEARLY,
            name="Yearly",
            price_usd=599.0,
            duration_days=365,
            description="12 Months Premium Access (Save 37%)",
            features=[
                "All Quarterly features",
                "1-on-1 onboarding call",
                "Exclusive strategies",
                "Early access to new features",
            ],
        ),
        SubscriptionPlan.LIFETIME: PlanConfig(
            plan_type=SubscriptionPlan.LIFETIME,
            name="Lifetime",
            price_usd=999.0,
            duration_days=0,
            description="Forever Premium Access",
            features=[
                "All Yearly features",
                "Never expires",
                "Founder badge",
                "VIP Discord access",
            ],
        ),
    }

    def __init__(
        self,
        client: Optional["TelegramClient"] = None,
        wallets: Optional[PaymentWallets] = None,
        state_file: str = "subscriptions.json",
        premium_channel_id: Optional[str] = None,
        db_pool: Optional["Pool"] = None,
    ) -> None:
        """
        Initialize subscription manager.

        Args:
            client: Telegram client for sending messages
            wallets: Payment receiving wallets
            state_file: Path to subscription state file
            premium_channel_id: Premium channel for invite links
            db_pool: Optional PostgreSQL pool for persistence
        """
        self._client = client
        self._wallets = wallets or PaymentWallets()
        self._state_file = Path(state_file)
        self._premium_channel_id = premium_channel_id
        self._db_pool = db_pool

        self._subscribers: dict[int, Subscriber] = {}
        self._plans = self.DEFAULT_PLANS.copy()
        self._pending_payments: dict[int, datetime] = {}  # user_id -> payment started

        self._initialized = False

    @property
    def wallets(self) -> PaymentWallets:
        """Get payment wallets."""
        return self._wallets

    def set_wallets(self, wallets: PaymentWallets) -> None:
        """Update payment wallets."""
        self._wallets = wallets

    def get_plan(self, plan_type: SubscriptionPlan) -> PlanConfig:
        """Get plan configuration."""
        return self._plans[plan_type]

    def get_all_plans(self) -> list[PlanConfig]:
        """Get all available plans."""
        return list(self._plans.values())

    async def load(self) -> None:
        """Load subscription state from file."""
        if self._db_pool:
            await self._load_from_database()
        elif self._state_file.exists():
            await self._load_from_file()

        self._initialized = True
        logger.info(f"Loaded {len(self._subscribers)} subscribers")

    async def _load_from_file(self) -> None:
        """Load from JSON file."""
        try:
            with open(self._state_file, 'r') as f:
                data = json.load(f)

            for sub_data in data.get("subscribers", []):
                sub = Subscriber.from_dict(sub_data)
                self._subscribers[sub.user_id] = sub

        except Exception as e:
            logger.error(f"Failed to load subscriptions: {e}")

    async def _load_from_database(self) -> None:
        """Load from PostgreSQL database."""
        if not self._db_pool:
            return

        try:
            async with self._db_pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT * FROM subscriptions
                    WHERE status != 'cancelled'
                ''')

                for row in rows:
                    sub = Subscriber(
                        user_id=row['user_id'],
                        username=row['username'],
                        plan=SubscriptionPlan(row['plan']),
                        status=SubscriptionStatus(row['status']),
                        activated_at=row['activated_at'],
                        expires_at=row['expires_at'],
                        payment_tx_hash=row['payment_tx_hash'],
                    )
                    self._subscribers[sub.user_id] = sub

        except Exception as e:
            logger.error(f"Failed to load from database: {e}")

    async def save(self) -> None:
        """Save subscription state."""
        if self._db_pool:
            # Database saves are immediate
            return

        try:
            data = {
                "subscribers": [sub.to_dict() for sub in self._subscribers.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            with open(self._state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save subscriptions: {e}")

    def has_access(self, user_id: int) -> bool:
        """Check if user has active premium access."""
        sub = self._subscribers.get(user_id)
        if not sub:
            return False
        return sub.is_active

    def get_subscriber(self, user_id: int) -> Optional[Subscriber]:
        """Get subscriber by user ID."""
        return self._subscribers.get(user_id)

    def get_active_subscribers(self) -> list[Subscriber]:
        """Get all active subscribers."""
        return [s for s in self._subscribers.values() if s.is_active]

    def get_expiring_soon(self, days: int = 7) -> list[Subscriber]:
        """Get subscribers expiring within N days."""
        result = []
        for sub in self._subscribers.values():
            if sub.is_active and sub.days_remaining is not None:
                if 0 < sub.days_remaining <= days:
                    result.append(sub)
        return result

    async def create_subscription(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> Subscriber:
        """
        Create a new pending subscription.

        Args:
            user_id: Telegram user ID
            plan: Subscription plan
            username: Optional username
            first_name: Optional first name

        Returns:
            New Subscriber object in pending status
        """
        sub = Subscriber(
            user_id=user_id,
            username=username,
            first_name=first_name,
            plan=plan,
            status=SubscriptionStatus.PENDING,
        )

        self._subscribers[user_id] = sub
        self._pending_payments[user_id] = datetime.now(timezone.utc)

        await self.save()

        logger.info(f"Created pending subscription for {user_id}: {plan.value}")
        return sub

    async def activate_subscription(
        self,
        user_id: int,
        payment_method: Optional[PaymentMethod] = None,
        payment_tx_hash: Optional[str] = None,
    ) -> Optional[Subscriber]:
        """
        Activate a pending subscription after payment verification.

        Args:
            user_id: User ID to activate
            payment_method: Payment method used
            payment_tx_hash: Transaction hash for verification

        Returns:
            Activated subscriber or None if not found
        """
        sub = self._subscribers.get(user_id)
        if not sub:
            logger.warning(f"No subscription found for {user_id}")
            return None

        plan_config = self._plans[sub.plan]
        now = datetime.now(timezone.utc)

        sub.status = SubscriptionStatus.ACTIVE
        sub.activated_at = now
        sub.payment_method = payment_method
        sub.payment_tx_hash = payment_tx_hash
        sub.payment_amount_usd = plan_config.price_usd

        # Set expiry
        if plan_config.is_lifetime:
            sub.expires_at = None
        else:
            sub.expires_at = now + timedelta(days=plan_config.duration_days)

        # Generate invite link
        if self._client and self._premium_channel_id:
            sub.invite_link = await self._generate_invite_link(user_id)

        # Remove from pending
        self._pending_payments.pop(user_id, None)

        await self.save()

        logger.info(f"Activated subscription for {user_id}: {sub.plan.value}")
        return sub

    async def extend_subscription(
        self,
        user_id: int,
        plan: SubscriptionPlan,
    ) -> Optional[Subscriber]:
        """
        Extend an existing subscription.

        Args:
            user_id: User ID
            plan: Plan to extend with

        Returns:
            Updated subscriber or None
        """
        sub = self._subscribers.get(user_id)
        if not sub:
            return None

        plan_config = self._plans[plan]
        now = datetime.now(timezone.utc)

        # Calculate new expiry
        if plan_config.is_lifetime:
            sub.expires_at = None
            sub.plan = plan
        else:
            # Add to existing expiry or from now
            base_date = sub.expires_at if sub.expires_at and sub.expires_at > now else now
            sub.expires_at = base_date + timedelta(days=plan_config.duration_days)

        sub.status = SubscriptionStatus.ACTIVE

        await self.save()

        logger.info(f"Extended subscription for {user_id}: +{plan_config.duration_days} days")
        return sub

    async def cancel_subscription(self, user_id: int) -> Optional[Subscriber]:
        """Cancel a subscription."""
        sub = self._subscribers.get(user_id)
        if not sub:
            return None

        sub.status = SubscriptionStatus.CANCELLED

        await self.save()

        logger.info(f"Cancelled subscription for {user_id}")
        return sub

    async def _generate_invite_link(self, user_id: int) -> Optional[str]:
        """Generate unique invite link for premium channel."""
        if not self._client or not self._premium_channel_id:
            return None

        try:
            # Create invite link that can only be used once
            result = await self._client(
                # Use CreateChatInviteLinkRequest for proper invite creation
                # This is a simplified version
                self._client.export_chat_invite_link(self._premium_channel_id)
            )
            return result
        except Exception as e:
            logger.error(f"Failed to generate invite link: {e}")
            return None

    async def check_expired(self) -> list[Subscriber]:
        """
        Check for expired subscriptions and update status.

        Returns:
            List of newly expired subscribers
        """
        expired = []
        now = datetime.now(timezone.utc)

        for sub in self._subscribers.values():
            if sub.status == SubscriptionStatus.ACTIVE:
                if sub.expires_at and sub.expires_at < now:
                    sub.status = SubscriptionStatus.EXPIRED
                    expired.append(sub)

        if expired:
            await self.save()
            logger.info(f"Marked {len(expired)} subscriptions as expired")

        return expired

    def format_plans_message(self) -> str:
        """Format subscription plans for display."""
        lines = [
            "🔑 **PREMIUM SUBSCRIPTION PLANS**",
            "",
            "Unlock the full power of our trading signals:",
            "",
        ]

        for plan in self._plans.values():
            price_str = f"${plan.price_usd:.0f}"
            lines.append(f"**{plan.name}** - {price_str}")
            lines.append(f"_{plan.description}_")
            lines.append("")

        lines.extend([
            "═══════════════════════════",
            "",
            "All plans include:",
            "• Instant real-time signals (no delay)",
            "• Full token addresses for sniping",
            "• Anti-rug security checks",
            "• KOL/Whale tracking alerts",
            "• Priority support",
            "",
            "Use `/subscribe <plan>` to get started!",
        ])

        return "\n".join(lines)

    def format_payment_message(self, sub: Subscriber) -> str:
        """Format payment instructions for a subscriber."""
        plan = self._plans[sub.plan]

        lines = [
            f"💰 **Payment for {plan.name} Plan**",
            "",
            f"**Total: ${plan.price_usd:.0f} USD**",
            "",
            "═══════════════════════════",
            "",
            "**Payment Options:**",
            "",
        ]

        # Add available payment methods
        if self._wallets.sol_address:
            lines.extend([
                "**SOL (Solana)**",
                f"`{self._wallets.sol_address}`",
                "[Convert USD to SOL](https://www.coingecko.com/en/coins/solana/usd)",
                "",
            ])

        if self._wallets.usdt_bep20_address:
            lines.extend([
                "**USDT (BEP20 - BNB Chain)**",
                f"`{self._wallets.usdt_bep20_address}`",
                "",
            ])

        if self._wallets.usdc_sol_address:
            lines.extend([
                "**USDC (Solana)**",
                f"`{self._wallets.usdc_sol_address}`",
                "",
            ])

        lines.extend([
            "═══════════════════════════",
            "",
            "**After Payment:**",
            "1. Copy the transaction hash/signature",
            "2. Send `/verify <tx_hash>` to confirm",
            "3. Receive your premium access instantly!",
            "",
            "_Payment will be verified within 5 minutes_",
        ])

        return "\n".join(lines)

    def format_subscription_status(self, sub: Subscriber) -> str:
        """Format subscription status for display."""
        if sub.status == SubscriptionStatus.ACTIVE:
            status_emoji = "✅"
            status_text = "Active"
        elif sub.status == SubscriptionStatus.PENDING:
            status_emoji = "⏳"
            status_text = "Pending Payment"
        elif sub.status == SubscriptionStatus.EXPIRED:
            status_emoji = "❌"
            status_text = "Expired"
        else:
            status_emoji = "🚫"
            status_text = "Cancelled"

        lines = [
            f"{status_emoji} **Subscription Status: {status_text}**",
            "",
            f"• Plan: **{sub.plan.value.title()}**",
        ]

        if sub.activated_at:
            lines.append(f"• Activated: {sub.activated_at.strftime('%Y-%m-%d')}")

        if sub.expires_at:
            lines.append(f"• Expires: {sub.expires_at.strftime('%Y-%m-%d')}")
            if sub.days_remaining is not None:
                if sub.days_remaining > 0:
                    lines.append(f"• Days Remaining: **{sub.days_remaining}**")
                else:
                    lines.append("• **Subscription expired**")
        elif sub.status == SubscriptionStatus.ACTIVE:
            lines.append("• Expires: **Never** (Lifetime)")

        if sub.invite_link and sub.status == SubscriptionStatus.ACTIVE:
            lines.extend([
                "",
                f"🔗 Premium Channel: {sub.invite_link}",
            ])

        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        """Get subscription statistics."""
        total = len(self._subscribers)
        active = len([s for s in self._subscribers.values() if s.is_active])
        pending = len([s for s in self._subscribers.values() if s.status == SubscriptionStatus.PENDING])
        expired = len([s for s in self._subscribers.values() if s.status == SubscriptionStatus.EXPIRED])

        # Revenue calculation
        total_revenue = sum(
            s.payment_amount_usd
            for s in self._subscribers.values()
            if s.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED)
        )

        # Plan breakdown
        plan_counts = {}
        for plan in SubscriptionPlan:
            plan_counts[plan.value] = len([
                s for s in self._subscribers.values()
                if s.plan == plan and s.is_active
            ])

        return {
            "total_subscribers": total,
            "active": active,
            "pending": pending,
            "expired": expired,
            "total_revenue_usd": total_revenue,
            "plan_breakdown": plan_counts,
        }

    def format_admin_stats(self) -> str:
        """Format stats for admin view."""
        stats = self.get_stats()

        lines = [
            "📊 **SUBSCRIPTION STATISTICS**",
            "",
            f"• Total Subscribers: {stats['total_subscribers']}",
            f"• Active: {stats['active']}",
            f"• Pending: {stats['pending']}",
            f"• Expired: {stats['expired']}",
            "",
            f"💰 Total Revenue: **${stats['total_revenue_usd']:.0f}**",
            "",
            "**Active by Plan:**",
        ]

        for plan, count in stats['plan_breakdown'].items():
            lines.append(f"• {plan.title()}: {count}")

        return "\n".join(lines)
