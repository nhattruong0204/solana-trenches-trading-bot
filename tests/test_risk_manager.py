"""
Tests for the risk_manager module - Risk Management System.

Covers:
- Stop loss evaluation (fixed, trailing, time-based)
- Dynamic position sizing
- Circuit breakers
- Portfolio risk tracking
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from src.risk_manager import (
    StopLossType,
    StopLossConfig,
    PositionSizingConfig,
    CircuitBreakerConfig,
    RiskConfig,
    StopLossManager,
    PositionSizer,
    CircuitBreaker,
    RiskManager,
    StopLossResult,
    PositionSizeResult,
    PortfolioRiskMetrics,
)
from src.models import Position, PositionStatus


# ==================== FIXTURES ====================

@pytest.fixture
def default_stop_loss_config():
    """Default stop loss configuration."""
    return StopLossConfig(
        enabled=True,
        stop_loss_type=StopLossType.FIXED_PERCENTAGE,
        fixed_percentage=0.25,
        trailing_percentage=0.20,
        trailing_activation=1.5,
        time_limit_hours=24,
    )


@pytest.fixture
def default_sizing_config():
    """Default position sizing configuration."""
    return PositionSizingConfig(
        enabled=True,
        base_amount_sol=0.1,
        risk_per_trade=0.02,
        min_size_multiplier=0.5,
        max_size_multiplier=1.5,
        min_position_size_sol=0.01,
        max_position_size_sol=1.0,
    )


@pytest.fixture
def default_circuit_config():
    """Default circuit breaker configuration."""
    return CircuitBreakerConfig(
        enabled=True,
        daily_loss_limit_pct=0.05,
        consecutive_loss_limit=5,
        cooldown_minutes=60,
    )


@pytest.fixture
def sample_position():
    """Sample position for testing."""
    return Position(
        token_address="TokenAddress123456789012345678901234567890",
        token_symbol="TEST",
        buy_time=datetime.now(timezone.utc) - timedelta(hours=2),
        buy_amount_sol=0.1,
        signal_msg_id=12345,
        status=PositionStatus.OPEN,
        last_multiplier=1.0,
        peak_multiplier=1.0,
    )


# ==================== STOP LOSS TESTS ====================

class TestStopLossManager:
    """Tests for StopLossManager class."""

    def test_create_stop_loss_manager(self, default_stop_loss_config):
        """Test creating a StopLossManager."""
        manager = StopLossManager(default_stop_loss_config)
        assert manager.config.enabled is True
        assert manager.config.fixed_percentage == 0.25

    def test_stop_loss_disabled(self, default_stop_loss_config, sample_position):
        """Test that disabled stop loss doesn't trigger."""
        default_stop_loss_config.enabled = False
        manager = StopLossManager(default_stop_loss_config)

        result = manager.evaluate(sample_position, current_multiplier=0.5)

        assert result.should_exit is False
        assert "disabled" in result.reason.lower()

    def test_fixed_stop_loss_triggers(self, default_stop_loss_config, sample_position):
        """Test fixed stop loss triggers at correct level."""
        manager = StopLossManager(default_stop_loss_config)

        # 25% stop loss should trigger at 0.75X
        result = manager.evaluate(sample_position, current_multiplier=0.74)

        assert result.should_exit is True
        assert result.stop_type == StopLossType.FIXED_PERCENTAGE
        assert "fixed stop loss" in result.reason.lower()

    def test_fixed_stop_loss_no_trigger(self, default_stop_loss_config, sample_position):
        """Test fixed stop loss doesn't trigger above threshold."""
        manager = StopLossManager(default_stop_loss_config)

        # 0.80X should not trigger 25% stop
        result = manager.evaluate(sample_position, current_multiplier=0.80)

        assert result.should_exit is False

    def test_trailing_stop_not_active_below_activation(self, default_stop_loss_config, sample_position):
        """Test trailing stop doesn't activate below activation level."""
        manager = StopLossManager(default_stop_loss_config)

        # Peak at 1.4X, below 1.5X activation
        result = manager.evaluate(
            sample_position,
            current_multiplier=1.1,
            peak_multiplier=1.4,
        )

        assert result.should_exit is False

    def test_trailing_stop_triggers_after_activation(self, default_stop_loss_config, sample_position):
        """Test trailing stop triggers when price drops from peak."""
        manager = StopLossManager(default_stop_loss_config)

        # Peak at 2.0X, 20% trailing = stop at 1.6X
        # Current at 1.5X should trigger
        result = manager.evaluate(
            sample_position,
            current_multiplier=1.5,
            peak_multiplier=2.0,
        )

        assert result.should_exit is True
        assert result.stop_type == StopLossType.TRAILING
        assert "trailing stop" in result.reason.lower()

    def test_trailing_stop_no_trigger_above_trail(self, default_stop_loss_config, sample_position):
        """Test trailing stop doesn't trigger above trail level."""
        manager = StopLossManager(default_stop_loss_config)

        # Peak at 2.0X, 20% trailing = stop at 1.6X
        # Current at 1.7X should NOT trigger
        result = manager.evaluate(
            sample_position,
            current_multiplier=1.7,
            peak_multiplier=2.0,
        )

        assert result.should_exit is False

    def test_time_stop_triggers_underwater(self, default_stop_loss_config):
        """Test time-based stop triggers when underwater past time limit."""
        manager = StopLossManager(default_stop_loss_config)

        # Position held for 25 hours, underwater
        old_position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc) - timedelta(hours=25),
            buy_amount_sol=0.1,
            signal_msg_id=12345,
        )

        result = manager.evaluate(old_position, current_multiplier=0.9)

        assert result.should_exit is True
        assert result.stop_type == StopLossType.TIME_BASED
        assert "time stop" in result.reason.lower()

    def test_time_stop_no_trigger_if_profitable(self, default_stop_loss_config):
        """Test time-based stop doesn't trigger if position is profitable."""
        manager = StopLossManager(default_stop_loss_config)

        old_position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc) - timedelta(hours=25),
            buy_amount_sol=0.1,
            signal_msg_id=12345,
        )

        # Profitable at 1.2X
        result = manager.evaluate(old_position, current_multiplier=1.2)

        assert result.should_exit is False

    def test_update_config(self, default_stop_loss_config):
        """Test updating stop loss configuration."""
        manager = StopLossManager(default_stop_loss_config)

        manager.update_config(fixed_percentage=0.30, enabled=False)

        assert manager.config.fixed_percentage == 0.30
        assert manager.config.enabled is False


# ==================== POSITION SIZING TESTS ====================

class TestPositionSizer:
    """Tests for PositionSizer class."""

    def test_create_position_sizer(self, default_sizing_config):
        """Test creating a PositionSizer."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)
        assert sizer.capital == 10.0
        assert sizer.config.base_amount_sol == 0.1

    def test_disabled_sizing_returns_base(self, default_sizing_config):
        """Test that disabled sizing returns base amount."""
        default_sizing_config.enabled = False
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        result = sizer.calculate_size(signal_score=90)

        assert result.size_sol == 0.1
        assert "disabled" in result.reasoning.lower()

    def test_high_quality_signal_increases_size(self, default_sizing_config):
        """Test high quality signals get larger position sizes."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        result = sizer.calculate_size(signal_score=100)

        # Score of 100 should give max multiplier (1.5x)
        assert result.size_sol > default_sizing_config.base_amount_sol
        assert result.size_multiplier >= 1.4

    def test_low_quality_signal_decreases_size(self, default_sizing_config):
        """Test low quality signals get smaller position sizes."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        result = sizer.calculate_size(signal_score=0)

        # Score of 0 should give min multiplier (0.5x)
        assert result.size_sol < default_sizing_config.base_amount_sol
        assert result.size_multiplier <= 0.6

    def test_high_volatility_reduces_size(self, default_sizing_config):
        """Test high volatility reduces position size."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        # 25% volatility should reduce size
        result = sizer.calculate_size(volatility=0.25)

        assert result.volatility_factor == 0.5
        assert result.size_sol < default_sizing_config.base_amount_sol

    def test_low_volatility_increases_size(self, default_sizing_config):
        """Test low volatility can increase position size."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        # 3% volatility should increase size
        result = sizer.calculate_size(volatility=0.03)

        assert result.volatility_factor == 1.25

    def test_size_capped_by_max(self, default_sizing_config):
        """Test position size is capped at maximum."""
        sizer = PositionSizer(default_sizing_config, capital=100.0)

        # Very high score should still be capped at max
        result = sizer.calculate_size(signal_score=100)

        assert result.size_sol <= default_sizing_config.max_position_size_sol

    def test_size_floored_by_min(self, default_sizing_config):
        """Test position size is floored at minimum."""
        sizer = PositionSizer(default_sizing_config, capital=0.5)

        result = sizer.calculate_size(signal_score=0, volatility=0.30)

        assert result.size_sol >= default_sizing_config.min_position_size_sol

    def test_risk_based_cap(self, default_sizing_config):
        """Test position is capped by risk per trade."""
        default_sizing_config.base_amount_sol = 1.0  # Large base
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        result = sizer.calculate_size()

        # 2% of 10 SOL = 0.2 SOL max
        assert result.size_sol <= 0.2

    def test_set_capital(self, default_sizing_config):
        """Test updating capital."""
        sizer = PositionSizer(default_sizing_config, capital=10.0)

        sizer.set_capital(20.0)

        assert sizer.capital == 20.0


# ==================== CIRCUIT BREAKER TESTS ====================

class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_create_circuit_breaker(self, default_circuit_config):
        """Test creating a CircuitBreaker."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)
        assert cb.is_triggered is False

    def test_disabled_circuit_breaker(self, default_circuit_config):
        """Test disabled circuit breaker never triggers."""
        default_circuit_config.enabled = False
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        # Record large loss
        triggered = cb.record_trade(-5.0)

        assert triggered is False
        assert cb.is_triggered is False

    def test_daily_loss_triggers_breaker(self, default_circuit_config):
        """Test daily loss limit triggers circuit breaker."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        # 5% of 10 SOL = 0.5 SOL daily limit
        triggered = cb.record_trade(-0.6)

        assert triggered is True
        assert cb.is_triggered is True
        assert "daily loss" in cb.trigger_reason.lower()

    def test_consecutive_losses_trigger_breaker(self, default_circuit_config):
        """Test consecutive losses trigger circuit breaker."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        # 5 consecutive small losses
        for i in range(5):
            triggered = cb.record_trade(-0.05)

        assert triggered is True
        assert cb.is_triggered is True
        assert "consecutive" in cb.trigger_reason.lower()

    def test_winning_trade_resets_consecutive(self, default_circuit_config):
        """Test winning trade resets consecutive loss counter."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        # 3 losses
        for _ in range(3):
            cb.record_trade(-0.05)

        # 1 win
        cb.record_trade(0.10)

        # 3 more losses - should not trigger (only 3 consecutive)
        for _ in range(3):
            triggered = cb.record_trade(-0.05)

        assert triggered is False

    def test_can_trade_when_ok(self, default_circuit_config):
        """Test can_trade returns True when circuit breaker not triggered."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        can_trade, reason = cb.can_trade()

        assert can_trade is True
        assert reason is None

    def test_can_trade_when_triggered(self, default_circuit_config):
        """Test can_trade returns False when circuit breaker triggered."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        cb.record_trade(-0.6)  # Trigger

        can_trade, reason = cb.can_trade()

        assert can_trade is False
        assert reason is not None

    def test_cooldown_expires(self, default_circuit_config):
        """Test circuit breaker allows trading after cooldown."""
        default_circuit_config.cooldown_minutes = 1  # Short cooldown
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        cb.record_trade(-0.6)  # Trigger

        # Manually expire cooldown
        cb._cooldown_until = datetime.now(timezone.utc) - timedelta(minutes=1)

        can_trade, reason = cb.can_trade()

        assert can_trade is True

    def test_manual_reset(self, default_circuit_config):
        """Test manual reset of circuit breaker."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        cb.record_trade(-0.6)  # Trigger
        assert cb.is_triggered is True

        cb.reset()

        assert cb.is_triggered is False
        can_trade, _ = cb.can_trade()
        assert can_trade is True

    def test_get_metrics(self, default_circuit_config):
        """Test getting circuit breaker metrics."""
        cb = CircuitBreaker(default_circuit_config, capital=10.0)

        cb.record_trade(-0.1)
        cb.record_trade(-0.1)

        metrics = cb.get_metrics()

        assert metrics["daily_pnl"] == -0.2
        assert metrics["consecutive_losses"] == 2
        assert metrics["is_triggered"] is False


# ==================== RISK MANAGER TESTS ====================

class TestRiskManager:
    """Tests for RiskManager class."""

    def test_create_risk_manager(self):
        """Test creating a RiskManager."""
        manager = RiskManager(capital=10.0)

        assert manager.config is not None
        assert manager.stop_loss is not None
        assert manager.position_sizer is not None
        assert manager.circuit_breaker is not None

    def test_create_with_custom_config(self, default_stop_loss_config, default_sizing_config, default_circuit_config):
        """Test creating RiskManager with custom configuration."""
        config = RiskConfig(
            stop_loss=default_stop_loss_config,
            position_sizing=default_sizing_config,
            circuit_breaker=default_circuit_config,
            max_portfolio_heat=0.15,
        )

        manager = RiskManager(config=config, capital=20.0)

        assert manager.config.max_portfolio_heat == 0.15
        assert manager._capital == 20.0

    def test_set_capital_updates_all_components(self):
        """Test that set_capital updates all components."""
        manager = RiskManager(capital=10.0)

        manager.set_capital(25.0)

        assert manager._capital == 25.0
        assert manager.position_sizer.capital == 25.0

    def test_can_open_position_circuit_breaker(self):
        """Test can_open_position respects circuit breaker."""
        manager = RiskManager(capital=10.0)

        # Trigger circuit breaker
        manager.circuit_breaker.record_trade(-0.6)

        can_open, reason = manager.can_open_position(0.1)

        assert can_open is False
        assert "circuit" in reason.lower() or "daily" in reason.lower()

    def test_can_open_position_portfolio_heat(self):
        """Test can_open_position respects portfolio heat limit."""
        config = RiskConfig(max_portfolio_heat=0.10)
        manager = RiskManager(config=config, capital=10.0)

        # Update with existing positions totaling 0.9 SOL
        positions = [
            Position(
                token_address=f"Token{i}123456789012345678901234567890",
                token_symbol=f"T{i}",
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=0.3,
                signal_msg_id=i,
            )
            for i in range(3)
        ]
        manager.update_positions(positions)

        # Try to open position that would exceed 10% heat
        can_open, reason = manager.can_open_position(0.2)

        assert can_open is False
        assert "heat" in reason.lower() or "portfolio" in reason.lower()

    def test_should_force_exit_time_limit(self):
        """Test force exit for positions exceeding max hold time."""
        config = RiskConfig(max_hold_time_hours=24)
        manager = RiskManager(config=config, capital=10.0)

        old_position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc) - timedelta(hours=25),
            buy_amount_sol=0.1,
            signal_msg_id=12345,
        )

        should_exit, reason = manager.should_force_exit(old_position)

        assert should_exit is True
        assert "hold time" in reason.lower()

    def test_evaluate_stop_loss_delegates(self, sample_position):
        """Test evaluate_stop_loss delegates to StopLossManager."""
        manager = RiskManager(capital=10.0)

        result = manager.evaluate_stop_loss(
            position=sample_position,
            current_multiplier=0.5,
        )

        assert isinstance(result, StopLossResult)

    def test_calculate_position_size_delegates(self):
        """Test calculate_position_size delegates to PositionSizer."""
        manager = RiskManager(capital=10.0)

        result = manager.calculate_position_size(signal_score=80)

        assert isinstance(result, PositionSizeResult)

    def test_record_trade_result_tracks_pnl(self):
        """Test recording trade results for circuit breaker."""
        manager = RiskManager(capital=10.0)

        # Record loss
        triggered = manager.record_trade_result(-0.1)

        metrics = manager.get_portfolio_metrics()
        assert metrics.daily_realized_pnl == -0.1

    def test_get_portfolio_metrics(self):
        """Test getting comprehensive portfolio metrics."""
        manager = RiskManager(capital=10.0)

        positions = [
            Position(
                token_address="TokenAddress123456789012345678901234567890",
                token_symbol="TEST",
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=0.2,
                signal_msg_id=12345,
            )
        ]
        manager.update_positions(positions)

        metrics = manager.get_portfolio_metrics()

        assert isinstance(metrics, PortfolioRiskMetrics)
        assert metrics.total_positions == 1
        assert metrics.total_exposure_sol == 0.2
        assert metrics.portfolio_heat == 0.02  # 0.2 / 10.0

    def test_format_status(self):
        """Test formatting risk status as string."""
        manager = RiskManager(capital=10.0)

        status = manager.format_status()

        assert "Risk Management Status" in status
        assert "Capital" in status
        assert "Stop Loss" in status
        assert "Circuit Breaker" in status


# ==================== INTEGRATION TESTS ====================

class TestRiskManagerIntegration:
    """Integration tests for the complete risk management flow."""

    def test_complete_trade_flow(self):
        """Test complete flow: check position, size, trade, record."""
        manager = RiskManager(capital=10.0)

        # 1. Check if we can trade
        can_trade, _ = manager.circuit_breaker.can_trade()
        assert can_trade is True

        # 2. Calculate position size
        size_result = manager.calculate_position_size(signal_score=70)
        assert size_result.size_sol > 0

        # 3. Check if we can open this position
        can_open, _ = manager.can_open_position(size_result.size_sol)
        assert can_open is True

        # 4. Create position (simulating successful buy)
        position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc),
            buy_amount_sol=size_result.size_sol,
            signal_msg_id=12345,
        )
        manager.update_positions([position])

        # 5. Check stop loss (position at entry)
        sl_result = manager.evaluate_stop_loss(
            position=position,
            current_multiplier=1.0,
        )
        assert sl_result.should_exit is False

        # 6. Simulate profitable exit
        pnl = size_result.size_sol * 0.5  # 50% profit
        triggered = manager.record_trade_result(pnl)
        assert triggered is False

    def test_stop_loss_exit_flow(self):
        """Test flow when stop loss triggers."""
        manager = RiskManager(capital=10.0)

        position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc) - timedelta(hours=1),
            buy_amount_sol=0.1,
            signal_msg_id=12345,
            peak_multiplier=1.8,  # Was up 80%
        )
        manager.update_positions([position])

        # Price dropped to 0.7X - below 25% fixed stop loss (0.75X)
        # Fixed stop loss evaluates first, so it triggers
        sl_result = manager.evaluate_stop_loss(
            position=position,
            current_multiplier=0.7,
            peak_multiplier=1.8,
        )

        assert sl_result.should_exit is True
        # Fixed stop loss triggers first at 0.75X threshold
        assert sl_result.stop_type == StopLossType.FIXED_PERCENTAGE

    def test_trailing_stop_exit_flow(self):
        """Test trailing stop triggers when price drops from peak."""
        manager = RiskManager(capital=10.0)

        position = Position(
            token_address="TokenAddress123456789012345678901234567890",
            token_symbol="TEST",
            buy_time=datetime.now(timezone.utc) - timedelta(hours=1),
            buy_amount_sol=0.1,
            signal_msg_id=12345,
            peak_multiplier=2.0,  # Was up 100%
        )
        manager.update_positions([position])

        # Price dropped to 1.5X from peak of 2.0X
        # Trailing stop (20%) triggers at 1.6X, so 1.5X should trigger
        # But fixed stop (0.75X) won't trigger since we're still above 1.0X
        sl_result = manager.evaluate_stop_loss(
            position=position,
            current_multiplier=1.5,
            peak_multiplier=2.0,
        )

        assert sl_result.should_exit is True
        assert sl_result.stop_type == StopLossType.TRAILING

    def test_circuit_breaker_blocks_trading(self):
        """Test that circuit breaker properly blocks new trades."""
        manager = RiskManager(capital=10.0)

        # Record 5 consecutive losses
        for _ in range(5):
            manager.record_trade_result(-0.05)

        # Now trading should be blocked
        can_trade, reason = manager.circuit_breaker.can_trade()
        assert can_trade is False

        can_open, reason = manager.can_open_position(0.1)
        assert can_open is False
