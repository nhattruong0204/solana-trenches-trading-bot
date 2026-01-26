"""
Tests for commercial/premium features.

Tests cover:
- Signal Publisher
- Subscription Manager
- Hit Rate Tracker
- KOL Tracker
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.signal_publisher import (
    SignalPublisher,
    BroadcastConfig,
    SignalMapping,
)
from src.subscription_manager import (
    SubscriptionManager,
    PaymentWallets,
    SubscriptionPlan,
    SubscriptionStatus,
    Subscriber,
    PaymentMethod,
)
from src.hit_rate_tracker import (
    HitRateTracker,
    SignalRecord,
    TimeFrame,
)
from src.kol_tracker import (
    KOLTracker,
    KOLTrackerConfig,
    TrackedWallet,
    WalletType,
    WalletTransaction,
    TransactionType,
)


# ==============================================================================
# Signal Publisher Tests
# ==============================================================================

class TestSignalMapping:
    """Tests for SignalMapping dataclass."""

    def test_signal_mapping_creation(self):
        """Test SignalMapping can be created with required fields."""
        mapping = SignalMapping(
            source_msg_id=123,
            premium_msg_id=456,
            token_symbol="TEST",
            token_address="abc123",
        )
        assert mapping.source_msg_id == 123
        assert mapping.premium_msg_id == 456
        assert mapping.token_symbol == "TEST"
        assert mapping.forwarded_to_public is False

    def test_signal_mapping_to_dict(self):
        """Test SignalMapping serialization."""
        mapping = SignalMapping(
            source_msg_id=123,
            premium_msg_id=456,
            token_symbol="TEST",
            token_address="abc123",
            current_multiplier=2.5,
        )
        data = mapping.to_dict()
        assert data["source_msg_id"] == 123
        assert data["token_symbol"] == "TEST"
        assert data["current_multiplier"] == 2.5

    def test_signal_mapping_from_dict(self):
        """Test SignalMapping deserialization."""
        data = {
            "source_msg_id": 123,
            "premium_msg_id": 456,
            "token_symbol": "TEST",
            "token_address": "abc123",
            "entry_time": "2024-01-01T00:00:00+00:00",
        }
        mapping = SignalMapping.from_dict(data)
        assert mapping.source_msg_id == 123
        assert mapping.token_symbol == "TEST"


# ==============================================================================
# Subscription Manager Tests
# ==============================================================================

class TestSubscriber:
    """Tests for Subscriber dataclass."""

    def test_is_active_pending(self):
        """Test pending subscription is not active."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.PENDING,
        )
        assert not sub.is_active

    def test_is_active_active(self):
        """Test active subscription."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert sub.is_active

    def test_is_active_expired(self):
        """Test expired subscription."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert not sub.is_active

    def test_is_active_lifetime(self):
        """Test lifetime subscription."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=None,  # Lifetime
        )
        assert sub.is_active

    def test_days_remaining(self):
        """Test days remaining calculation."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        # Allow 9 or 10 due to timing edge cases
        assert sub.days_remaining in (9, 10)

    def test_days_remaining_lifetime(self):
        """Test days remaining for lifetime."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=None,
        )
        assert sub.days_remaining is None

    def test_is_expiring_soon(self):
        """Test expiring soon detection."""
        sub = Subscriber(
            user_id=123,
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        )
        assert sub.is_expiring_soon

        sub2 = Subscriber(
            user_id=124,
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(days=15),
        )
        assert not sub2.is_expiring_soon

    def test_serialization(self):
        """Test to_dict and from_dict."""
        sub = Subscriber(
            user_id=123,
            username="testuser",
            plan=SubscriptionPlan.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
        )
        data = sub.to_dict()
        restored = Subscriber.from_dict(data)

        assert restored.user_id == sub.user_id
        assert restored.username == sub.username
        assert restored.plan == sub.plan
        assert restored.status == sub.status


class TestSubscriptionManager:
    """Tests for SubscriptionManager."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a subscription manager with temp file."""
        state_file = tmp_path / "subscriptions.json"
        return SubscriptionManager(state_file=str(state_file))

    @pytest.mark.asyncio
    async def test_create_subscription(self, manager):
        """Test creating a new subscription."""
        sub = await manager.create_subscription(
            user_id=123,
            plan=SubscriptionPlan.MONTHLY,
            username="testuser",
        )

        assert sub.user_id == 123
        assert sub.plan == SubscriptionPlan.MONTHLY
        assert sub.status == SubscriptionStatus.PENDING

    @pytest.mark.asyncio
    async def test_activate_subscription(self, manager):
        """Test activating a subscription."""
        # First create
        await manager.create_subscription(user_id=123, plan=SubscriptionPlan.MONTHLY)

        # Then activate
        sub = await manager.activate_subscription(
            user_id=123,
            payment_method=PaymentMethod.SOL,
        )

        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.payment_method == PaymentMethod.SOL
        assert sub.expires_at is not None

    @pytest.mark.asyncio
    async def test_has_access(self, manager):
        """Test access checking."""
        await manager.create_subscription(user_id=123, plan=SubscriptionPlan.MONTHLY)
        assert not manager.has_access(123)

        await manager.activate_subscription(user_id=123)
        assert manager.has_access(123)

    @pytest.mark.asyncio
    async def test_get_active_subscribers(self, manager):
        """Test getting active subscribers."""
        await manager.create_subscription(user_id=1, plan=SubscriptionPlan.MONTHLY)
        await manager.activate_subscription(user_id=1)

        await manager.create_subscription(user_id=2, plan=SubscriptionPlan.MONTHLY)
        # User 2 not activated

        active = manager.get_active_subscribers()
        assert len(active) == 1
        assert active[0].user_id == 1


# ==============================================================================
# Hit Rate Tracker Tests
# ==============================================================================

class TestSignalRecord:
    """Tests for SignalRecord dataclass."""

    def test_update_multiplier_hits(self):
        """Test multiplier milestone tracking."""
        record = SignalRecord(
            signal_id="test1",
            token_symbol="TEST",
            token_address="abc123",
            entry_time=datetime.now(timezone.utc),
        )

        assert not record.hit_2x
        assert not record.hit_5x
        assert not record.hit_10x

        record.update_multiplier(2.5)
        assert record.hit_2x
        assert not record.hit_5x
        assert record.max_multiplier == 2.5

        record.update_multiplier(6.0)
        assert record.hit_5x
        assert not record.hit_10x
        assert record.max_multiplier == 6.0

        record.update_multiplier(12.0)
        assert record.hit_10x
        assert record.max_multiplier == 12.0

    def test_update_multiplier_lower_doesnt_reduce_max(self):
        """Test that lower multiplier doesn't reduce max."""
        record = SignalRecord(
            signal_id="test1",
            token_symbol="TEST",
            token_address="abc123",
            entry_time=datetime.now(timezone.utc),
        )

        record.update_multiplier(5.0)
        assert record.max_multiplier == 5.0

        record.update_multiplier(3.0)
        assert record.max_multiplier == 5.0
        assert record.last_multiplier == 3.0

    def test_serialization(self):
        """Test to_dict and from_dict."""
        record = SignalRecord(
            signal_id="test1",
            token_symbol="TEST",
            token_address="abc123",
            entry_time=datetime.now(timezone.utc),
        )
        record.update_multiplier(5.0)

        data = record.to_dict()
        restored = SignalRecord.from_dict(data)

        assert restored.signal_id == record.signal_id
        assert restored.hit_5x == record.hit_5x
        assert restored.max_multiplier == record.max_multiplier


class TestHitRateTracker:
    """Tests for HitRateTracker."""

    @pytest.fixture
    def tracker(self, tmp_path):
        """Create a tracker with temp file."""
        state_file = tmp_path / "hit_rate.json"
        return HitRateTracker(state_file=str(state_file))

    @pytest.mark.asyncio
    async def test_record_signal(self, tracker):
        """Test recording a new signal."""
        record = tracker.record_signal(
            signal_id="test1",
            token_symbol="TEST",
            token_address="abc123",
        )

        assert record.signal_id == "test1"
        assert record.token_symbol == "TEST"
        assert tracker.get_signal("test1") is not None

    @pytest.mark.asyncio
    async def test_update_signal(self, tracker):
        """Test updating a signal."""
        tracker.record_signal(
            signal_id="test1",
            token_symbol="TEST",
            token_address="abc123",
        )

        record = tracker.update_signal("test1", 3.0)
        assert record.max_multiplier == 3.0
        assert record.hit_2x
        assert record.hit_3x
        assert not record.hit_5x

    @pytest.mark.asyncio
    async def test_calculate_metrics(self, tracker):
        """Test metrics calculation."""
        # Add some signals
        tracker.record_signal("s1", "A", "addr1")
        tracker.update_signal("s1", 2.5)

        tracker.record_signal("s2", "B", "addr2")
        tracker.update_signal("s2", 6.0)

        tracker.record_signal("s3", "C", "addr3")
        tracker.update_signal("s3", 12.0)

        metrics = tracker.calculate_metrics(TimeFrame.ALL_TIME)

        assert metrics.total_signals == 3
        assert metrics.hit_2x_count == 3
        assert metrics.hit_5x_count == 2
        assert metrics.hit_10x_count == 1
        assert metrics.best_multiplier == 12.0


# ==============================================================================
# KOL Tracker Tests
# ==============================================================================

class TestTrackedWallet:
    """Tests for TrackedWallet dataclass."""

    def test_win_rate_calculation(self):
        """Test win rate calculation."""
        wallet = TrackedWallet(
            address="abc123",
            name="Test Whale",
            wallet_type=WalletType.WHALE,
            total_trades=10,
            profitable_trades=7,
        )
        assert wallet.win_rate == 70.0

    def test_win_rate_zero_trades(self):
        """Test win rate with zero trades."""
        wallet = TrackedWallet(
            address="abc123",
            name="Test Whale",
            wallet_type=WalletType.WHALE,
        )
        assert wallet.win_rate == 0.0

    def test_serialization(self):
        """Test to_dict and from_dict."""
        wallet = TrackedWallet(
            address="abc123",
            name="Test Whale",
            wallet_type=WalletType.WHALE,
            twitter_handle="testwhale",
        )
        data = wallet.to_dict()
        restored = TrackedWallet.from_dict(data)

        assert restored.address == wallet.address
        assert restored.name == wallet.name
        assert restored.wallet_type == wallet.wallet_type


class TestWalletTransaction:
    """Tests for WalletTransaction dataclass."""

    def test_is_significant(self):
        """Test significance check."""
        wallet = TrackedWallet(
            address="abc123",
            name="Test",
            wallet_type=WalletType.WHALE,
            min_trade_usd=1000.0,
        )

        tx_small = WalletTransaction(
            wallet=wallet,
            tx_type=TransactionType.BUY,
            token_address="xyz",
            token_symbol="TEST",
            amount_tokens=100,
            amount_usd=500,
            price_usd=5.0,
            tx_hash="hash123",
            timestamp=datetime.now(timezone.utc),
        )
        assert not tx_small.is_significant

        tx_large = WalletTransaction(
            wallet=wallet,
            tx_type=TransactionType.BUY,
            token_address="xyz",
            token_symbol="TEST",
            amount_tokens=1000,
            amount_usd=5000,
            price_usd=5.0,
            tx_hash="hash456",
            timestamp=datetime.now(timezone.utc),
        )
        assert tx_large.is_significant


class TestKOLTracker:
    """Tests for KOLTracker."""

    @pytest.fixture
    def tracker(self, tmp_path):
        """Create a tracker with temp file."""
        state_file = tmp_path / "kol_tracker.json"
        return KOLTracker(state_file=str(state_file))

    @pytest.mark.asyncio
    async def test_add_wallet(self, tracker):
        """Test adding a wallet."""
        wallet = tracker.add_wallet(
            address="abc123",
            name="Test Whale",
            wallet_type=WalletType.WHALE,
            twitter_handle="testwhale",
        )

        assert wallet.address == "abc123"
        assert wallet.name == "Test Whale"
        assert wallet.wallet_type == WalletType.WHALE
        assert len(tracker.wallets) == 1

    @pytest.mark.asyncio
    async def test_remove_wallet(self, tracker):
        """Test removing a wallet."""
        tracker.add_wallet("abc123", "Test", WalletType.WHALE)
        assert len(tracker.wallets) == 1

        result = tracker.remove_wallet("abc123")
        assert result is True
        assert len(tracker.wallets) == 0

    @pytest.mark.asyncio
    async def test_enable_disable_wallet(self, tracker):
        """Test enabling/disabling a wallet."""
        tracker.add_wallet("abc123", "Test", WalletType.WHALE)

        tracker.disable_wallet("abc123")
        assert not tracker.get_wallet("abc123").enabled
        assert len(tracker.enabled_wallets) == 0

        tracker.enable_wallet("abc123")
        assert tracker.get_wallet("abc123").enabled
        assert len(tracker.enabled_wallets) == 1

    def test_format_transaction_alert(self, tracker):
        """Test transaction alert formatting."""
        wallet = TrackedWallet(
            address="abc123",
            name="Big Whale",
            wallet_type=WalletType.WHALE,
            twitter_handle="bigwhale",
        )

        tx = WalletTransaction(
            wallet=wallet,
            tx_type=TransactionType.BUY,
            token_address="xyz789",
            token_symbol="MOON",
            amount_tokens=1000000,
            amount_usd=50000,
            price_usd=0.05,
            tx_hash="hash123abc",
            timestamp=datetime.now(timezone.utc),
        )

        message = tracker.format_transaction_alert(tx)

        assert "WHALE ALERT" in message
        assert "Big Whale" in message
        assert "$MOON" in message
        assert "$50,000" in message
        assert "@bigwhale" in message
