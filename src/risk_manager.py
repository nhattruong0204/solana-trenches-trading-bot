"""
Risk Management Module.

Provides comprehensive risk management for the trading bot including:
- Stop loss strategies (fixed, trailing, time-based, ATR-based)
- Dynamic position sizing
- Portfolio heat tracking
- Circuit breakers for loss limits
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple, List

if TYPE_CHECKING:
    from src.models import Position

logger = logging.getLogger(__name__)


class StopLossType(str, Enum):
    """Types of stop loss strategies."""
    FIXED_PERCENTAGE = "fixed_percentage"
    TRAILING = "trailing"
    TIME_BASED = "time_based"
    ATR_BASED = "atr_based"

    def __str__(self) -> str:
        return self.value


@dataclass
class StopLossConfig:
    """Configuration for stop loss behavior."""
    enabled: bool = True
    stop_loss_type: StopLossType = StopLossType.FIXED_PERCENTAGE

    # Fixed percentage stop loss (e.g., 0.25 = 25% loss from entry)
    fixed_percentage: float = 0.25

    # Trailing stop loss
    trailing_percentage: float = 0.20  # Trail 20% from peak
    trailing_activation: float = 1.5   # Activate after 1.5X gain

    # Time-based stop loss
    time_limit_hours: int = 24  # Exit if below entry after X hours

    # ATR-based (volatility-adjusted)
    atr_multiplier: float = 2.0  # Stop at entry - (ATR * multiplier)


@dataclass
class PositionSizingConfig:
    """Configuration for dynamic position sizing."""
    enabled: bool = True
    base_amount_sol: float = 0.1

    # Risk per trade as percentage of capital
    risk_per_trade: float = 0.02  # 2% of capital

    # Size multiplier range based on signal quality
    min_size_multiplier: float = 0.5   # 50% of base for low quality
    max_size_multiplier: float = 1.5   # 150% of base for high quality

    # Absolute limits
    min_position_size_sol: float = 0.01
    max_position_size_sol: float = 1.0

    # Volatility adjustment
    volatility_adjustment_enabled: bool = True
    high_volatility_reduction: float = 0.5  # Reduce by 50% in high vol


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    enabled: bool = True

    # Daily loss limit as percentage of capital
    daily_loss_limit_pct: float = 0.05  # 5% daily loss limit

    # Consecutive loss limit
    consecutive_loss_limit: int = 5

    # Cooldown period after circuit breaker triggers
    cooldown_minutes: int = 60


@dataclass
class RiskConfig:
    """Complete risk management configuration."""
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # Portfolio-level risk
    max_portfolio_heat: float = 0.10  # 10% max total portfolio risk
    max_correlated_positions: int = 3  # Max positions in similar tokens
    max_hold_time_hours: int = 72  # Force exit after 72 hours


@dataclass
class StopLossResult:
    """Result of a stop loss evaluation."""
    should_exit: bool
    reason: str
    exit_percentage: float = 100.0  # Percentage of position to exit
    current_multiplier: float = 1.0
    stop_type: Optional[StopLossType] = None


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    size_sol: float
    size_multiplier: float
    reasoning: str
    signal_score: Optional[float] = None
    volatility_factor: Optional[float] = None


@dataclass
class PortfolioRiskMetrics:
    """Current portfolio risk metrics."""
    total_positions: int = 0
    total_exposure_sol: float = 0.0
    portfolio_heat: float = 0.0
    daily_realized_pnl: float = 0.0
    daily_unrealized_pnl: float = 0.0
    consecutive_losses: int = 0
    circuit_breaker_active: bool = False
    circuit_breaker_reason: Optional[str] = None
    cooldown_until: Optional[datetime] = None


class StopLossManager:
    """Manages stop loss logic for positions."""

    def __init__(self, config: StopLossConfig):
        self._config = config

    @property
    def config(self) -> StopLossConfig:
        return self._config

    def update_config(self, **kwargs) -> None:
        """Update stop loss configuration."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def evaluate(
        self,
        position: "Position",
        current_multiplier: float,
        peak_multiplier: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> StopLossResult:
        """
        Evaluate if stop loss should trigger for a position.

        Args:
            position: The position to evaluate
            current_multiplier: Current price as multiplier of entry price
            peak_multiplier: Highest multiplier seen since entry
            atr: Average True Range for ATR-based stops

        Returns:
            StopLossResult with decision and reasoning
        """
        if not self._config.enabled:
            return StopLossResult(
                should_exit=False,
                reason="Stop loss disabled",
                current_multiplier=current_multiplier,
            )

        # Use position's peak if not provided
        if peak_multiplier is None:
            peak_multiplier = getattr(position, 'peak_multiplier', current_multiplier)

        # Check each stop loss type
        result = self._check_fixed_stop(current_multiplier)
        if result.should_exit:
            return result

        result = self._check_trailing_stop(current_multiplier, peak_multiplier)
        if result.should_exit:
            return result

        result = self._check_time_stop(position, current_multiplier)
        if result.should_exit:
            return result

        if atr is not None:
            result = self._check_atr_stop(current_multiplier, atr)
            if result.should_exit:
                return result

        return StopLossResult(
            should_exit=False,
            reason="No stop loss triggered",
            current_multiplier=current_multiplier,
        )

    def _check_fixed_stop(self, current_multiplier: float) -> StopLossResult:
        """Check fixed percentage stop loss."""
        if self._config.stop_loss_type != StopLossType.FIXED_PERCENTAGE:
            return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)

        stop_level = 1.0 - self._config.fixed_percentage

        if current_multiplier <= stop_level:
            loss_pct = (1.0 - current_multiplier) * 100
            return StopLossResult(
                should_exit=True,
                reason=f"Fixed stop loss triggered at {current_multiplier:.2f}X ({loss_pct:.1f}% loss)",
                current_multiplier=current_multiplier,
                stop_type=StopLossType.FIXED_PERCENTAGE,
            )

        return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)

    def _check_trailing_stop(
        self,
        current_multiplier: float,
        peak_multiplier: float,
    ) -> StopLossResult:
        """Check trailing stop loss."""
        # Only activate trailing stop if we've reached activation level
        if peak_multiplier < self._config.trailing_activation:
            return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)

        # Calculate trailing stop level
        trail_level = peak_multiplier * (1.0 - self._config.trailing_percentage)

        if current_multiplier <= trail_level:
            drop_pct = ((peak_multiplier - current_multiplier) / peak_multiplier) * 100
            return StopLossResult(
                should_exit=True,
                reason=f"Trailing stop triggered: {current_multiplier:.2f}X (dropped {drop_pct:.1f}% from peak {peak_multiplier:.2f}X)",
                current_multiplier=current_multiplier,
                stop_type=StopLossType.TRAILING,
            )

        return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)

    def _check_time_stop(
        self,
        position: "Position",
        current_multiplier: float,
    ) -> StopLossResult:
        """Check time-based stop loss."""
        hold_hours = position.holding_duration

        if hold_hours >= self._config.time_limit_hours and current_multiplier < 1.0:
            return StopLossResult(
                should_exit=True,
                reason=f"Time stop triggered: held {hold_hours:.1f}h while underwater ({current_multiplier:.2f}X)",
                current_multiplier=current_multiplier,
                stop_type=StopLossType.TIME_BASED,
            )

        return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)

    def _check_atr_stop(
        self,
        current_multiplier: float,
        atr: float,
    ) -> StopLossResult:
        """Check ATR-based stop loss."""
        # ATR stop: entry - (ATR * multiplier) as a multiplier
        # This requires entry price context, simplified here
        atr_stop_distance = atr * self._config.atr_multiplier
        atr_stop_level = 1.0 - atr_stop_distance

        if current_multiplier <= atr_stop_level:
            return StopLossResult(
                should_exit=True,
                reason=f"ATR stop triggered at {current_multiplier:.2f}X (ATR-based stop at {atr_stop_level:.2f}X)",
                current_multiplier=current_multiplier,
                stop_type=StopLossType.ATR_BASED,
            )

        return StopLossResult(should_exit=False, reason="", current_multiplier=current_multiplier)


class PositionSizer:
    """Calculates optimal position sizes based on risk parameters."""

    def __init__(self, config: PositionSizingConfig, capital: float = 10.0):
        self._config = config
        self._capital = capital

    @property
    def config(self) -> PositionSizingConfig:
        return self._config

    @property
    def capital(self) -> float:
        return self._capital

    def set_capital(self, capital: float) -> None:
        """Update the capital amount."""
        if capital > 0:
            self._capital = capital

    def update_config(self, **kwargs) -> None:
        """Update position sizing configuration."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def calculate_size(
        self,
        signal_score: Optional[float] = None,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
    ) -> PositionSizeResult:
        """
        Calculate position size based on signal quality and market conditions.

        Args:
            signal_score: Signal quality score (0-100)
            volatility: Market volatility measure (e.g., ATR as percentage)
            win_rate: Historical win rate for Kelly Criterion (0-1)

        Returns:
            PositionSizeResult with calculated size and reasoning
        """
        if not self._config.enabled:
            return PositionSizeResult(
                size_sol=self._config.base_amount_sol,
                size_multiplier=1.0,
                reasoning="Dynamic sizing disabled, using base amount",
            )

        base_size = self._config.base_amount_sol
        multiplier = 1.0
        reasoning_parts = []

        # Signal quality adjustment
        if signal_score is not None:
            quality_mult = self._calculate_quality_multiplier(signal_score)
            multiplier *= quality_mult
            reasoning_parts.append(f"Quality score {signal_score:.0f} -> {quality_mult:.2f}x")

        # Volatility adjustment
        vol_factor = None
        if volatility is not None and self._config.volatility_adjustment_enabled:
            vol_factor = self._calculate_volatility_factor(volatility)
            multiplier *= vol_factor
            reasoning_parts.append(f"Volatility {volatility:.2%} -> {vol_factor:.2f}x")

        # Kelly Criterion adjustment (simplified)
        if win_rate is not None and win_rate > 0:
            kelly_mult = self._calculate_kelly_factor(win_rate)
            multiplier *= kelly_mult
            reasoning_parts.append(f"Win rate {win_rate:.0%} -> Kelly {kelly_mult:.2f}x")

        # Calculate final size
        final_size = base_size * multiplier

        # Apply absolute limits
        final_size = max(self._config.min_position_size_sol, final_size)
        final_size = min(self._config.max_position_size_sol, final_size)

        # Risk-based cap (don't risk more than risk_per_trade of capital)
        max_risk_size = self._capital * self._config.risk_per_trade
        if final_size > max_risk_size:
            final_size = max_risk_size
            reasoning_parts.append(f"Capped by {self._config.risk_per_trade:.0%} risk limit")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Base amount used"

        return PositionSizeResult(
            size_sol=round(final_size, 4),
            size_multiplier=multiplier,
            reasoning=reasoning,
            signal_score=signal_score,
            volatility_factor=vol_factor,
        )

    def _calculate_quality_multiplier(self, score: float) -> float:
        """Calculate size multiplier based on signal quality score (0-100)."""
        # Linear interpolation between min and max multipliers
        normalized = max(0, min(100, score)) / 100
        mult_range = self._config.max_size_multiplier - self._config.min_size_multiplier
        return self._config.min_size_multiplier + (normalized * mult_range)

    def _calculate_volatility_factor(self, volatility: float) -> float:
        """Calculate size factor based on volatility."""
        # High volatility (>20%) reduces size, low volatility (<5%) increases
        if volatility > 0.20:
            return self._config.high_volatility_reduction
        elif volatility > 0.10:
            return 0.75
        elif volatility < 0.05:
            return 1.25
        else:
            return 1.0

    def _calculate_kelly_factor(self, win_rate: float) -> float:
        """Calculate Kelly Criterion-inspired sizing factor."""
        # Simplified Kelly: f = (bp - q) / b
        # Where b = win/loss ratio (assume 2:1), p = win rate, q = 1-p
        b = 2.0  # Expected win/loss ratio
        p = win_rate
        q = 1 - p

        kelly = (b * p - q) / b

        # Use fractional Kelly (25%) for safety
        fractional_kelly = kelly * 0.25

        # Clamp to reasonable range
        return max(0.5, min(1.5, 1.0 + fractional_kelly))


class CircuitBreaker:
    """Manages circuit breakers to halt trading during adverse conditions."""

    def __init__(self, config: CircuitBreakerConfig, capital: float = 10.0):
        self._config = config
        self._capital = capital

        # Daily tracking
        self._daily_pnl: float = 0.0
        self._day_start: datetime = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Consecutive loss tracking
        self._consecutive_losses: int = 0
        self._last_trade_profitable: Optional[bool] = None

        # Circuit breaker state
        self._is_triggered: bool = False
        self._trigger_reason: Optional[str] = None
        self._cooldown_until: Optional[datetime] = None

    @property
    def config(self) -> CircuitBreakerConfig:
        return self._config

    @property
    def is_triggered(self) -> bool:
        """Check if circuit breaker is currently active."""
        if not self._config.enabled:
            return False

        # Check if cooldown has expired
        if self._cooldown_until and datetime.now(timezone.utc) >= self._cooldown_until:
            self._reset()

        return self._is_triggered

    @property
    def trigger_reason(self) -> Optional[str]:
        return self._trigger_reason

    @property
    def cooldown_until(self) -> Optional[datetime]:
        return self._cooldown_until

    def set_capital(self, capital: float) -> None:
        """Update capital for limit calculations."""
        if capital > 0:
            self._capital = capital

    def update_config(self, **kwargs) -> None:
        """Update circuit breaker configuration."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def record_trade(self, pnl: float) -> bool:
        """
        Record a trade result and check circuit breakers.

        Args:
            pnl: Profit/loss in SOL (positive = profit, negative = loss)

        Returns:
            True if circuit breaker triggered, False otherwise
        """
        if not self._config.enabled:
            return False

        # Reset daily tracking if new day
        self._check_day_reset()

        # Update daily PnL
        self._daily_pnl += pnl

        # Track consecutive losses
        is_profitable = pnl >= 0
        if is_profitable:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
        self._last_trade_profitable = is_profitable

        # Check circuit breaker conditions
        return self._check_triggers()

    def can_trade(self) -> Tuple[bool, Optional[str]]:
        """
        Check if trading is allowed.

        Returns:
            Tuple of (can_trade, reason if not)
        """
        if not self._config.enabled:
            return True, None

        # Check cooldown
        if self._cooldown_until:
            if datetime.now(timezone.utc) < self._cooldown_until:
                remaining = (self._cooldown_until - datetime.now(timezone.utc)).total_seconds() / 60
                return False, f"Circuit breaker cooldown: {remaining:.0f}m remaining"
            else:
                self._reset()

        if self._is_triggered:
            return False, self._trigger_reason

        return True, None

    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self._reset()

    def get_metrics(self) -> dict:
        """Get current circuit breaker metrics."""
        return {
            "daily_pnl": self._daily_pnl,
            "daily_limit": self._capital * self._config.daily_loss_limit_pct,
            "consecutive_losses": self._consecutive_losses,
            "consecutive_limit": self._config.consecutive_loss_limit,
            "is_triggered": self._is_triggered,
            "trigger_reason": self._trigger_reason,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
        }

    def _check_triggers(self) -> bool:
        """Check all circuit breaker conditions."""
        # Daily loss limit
        daily_limit = self._capital * self._config.daily_loss_limit_pct
        if self._daily_pnl <= -daily_limit:
            self._trigger(f"Daily loss limit reached: {self._daily_pnl:.4f} SOL (limit: -{daily_limit:.4f})")
            return True

        # Consecutive losses
        if self._consecutive_losses >= self._config.consecutive_loss_limit:
            self._trigger(f"Consecutive loss limit reached: {self._consecutive_losses} losses")
            return True

        return False

    def _trigger(self, reason: str) -> None:
        """Trigger the circuit breaker."""
        self._is_triggered = True
        self._trigger_reason = reason
        self._cooldown_until = datetime.now(timezone.utc) + timedelta(
            minutes=self._config.cooldown_minutes
        )
        logger.warning(f"Circuit breaker triggered: {reason}")

    def _reset(self) -> None:
        """Reset circuit breaker state."""
        self._is_triggered = False
        self._trigger_reason = None
        self._cooldown_until = None
        logger.info("Circuit breaker reset")

    def _check_day_reset(self) -> None:
        """Reset daily tracking if it's a new day."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if today_start > self._day_start:
            self._daily_pnl = 0.0
            self._day_start = today_start
            logger.info("Daily PnL tracking reset for new day")


class RiskManager:
    """
    Central risk management coordinator.

    Combines stop loss, position sizing, and circuit breaker functionality.
    """

    def __init__(self, config: Optional[RiskConfig] = None, capital: float = 10.0):
        self._config = config or RiskConfig()
        self._capital = capital

        # Initialize components
        self._stop_loss = StopLossManager(self._config.stop_loss)
        self._position_sizer = PositionSizer(self._config.position_sizing, capital)
        self._circuit_breaker = CircuitBreaker(self._config.circuit_breaker, capital)

        # Portfolio tracking
        self._open_positions: List["Position"] = []
        self._total_exposure: float = 0.0

    @property
    def config(self) -> RiskConfig:
        return self._config

    @property
    def stop_loss(self) -> StopLossManager:
        return self._stop_loss

    @property
    def position_sizer(self) -> PositionSizer:
        return self._position_sizer

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    def set_capital(self, capital: float) -> None:
        """Update capital across all components."""
        if capital > 0:
            self._capital = capital
            self._position_sizer.set_capital(capital)
            self._circuit_breaker.set_capital(capital)

    def update_positions(self, positions: List["Position"]) -> None:
        """Update tracked open positions."""
        self._open_positions = positions
        self._total_exposure = sum(p.buy_amount_sol for p in positions if p.is_open or p.is_partially_sold)

    def can_open_position(self, proposed_size: float) -> Tuple[bool, Optional[str]]:
        """
        Check if a new position can be opened.

        Args:
            proposed_size: Size of proposed position in SOL

        Returns:
            Tuple of (can_open, reason if not)
        """
        # Check circuit breaker
        can_trade, reason = self._circuit_breaker.can_trade()
        if not can_trade:
            return False, reason

        # Check portfolio heat
        current_heat = self._total_exposure / self._capital if self._capital > 0 else 0
        new_heat = (self._total_exposure + proposed_size) / self._capital if self._capital > 0 else 0

        if new_heat > self._config.max_portfolio_heat:
            return False, f"Portfolio heat limit: current {current_heat:.1%}, would be {new_heat:.1%} (max {self._config.max_portfolio_heat:.0%})"

        return True, None

    def should_force_exit(self, position: "Position") -> Tuple[bool, Optional[str]]:
        """
        Check if a position should be force-exited due to time limit.

        Args:
            position: Position to check

        Returns:
            Tuple of (should_exit, reason)
        """
        hold_hours = position.holding_duration
        if hold_hours >= self._config.max_hold_time_hours:
            return True, f"Max hold time reached: {hold_hours:.1f}h (limit: {self._config.max_hold_time_hours}h)"
        return False, None

    def evaluate_stop_loss(
        self,
        position: "Position",
        current_multiplier: float,
        peak_multiplier: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> StopLossResult:
        """
        Evaluate stop loss for a position.

        Delegates to StopLossManager.
        """
        return self._stop_loss.evaluate(position, current_multiplier, peak_multiplier, atr)

    def calculate_position_size(
        self,
        signal_score: Optional[float] = None,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
    ) -> PositionSizeResult:
        """
        Calculate optimal position size.

        Delegates to PositionSizer.
        """
        return self._position_sizer.calculate_size(signal_score, volatility, win_rate)

    def record_trade_result(self, pnl: float) -> bool:
        """
        Record a trade result for circuit breaker tracking.

        Args:
            pnl: Profit/loss in SOL

        Returns:
            True if circuit breaker triggered
        """
        return self._circuit_breaker.record_trade(pnl)

    def get_portfolio_metrics(self) -> PortfolioRiskMetrics:
        """Get comprehensive portfolio risk metrics."""
        can_trade, reason = self._circuit_breaker.can_trade()
        cb_metrics = self._circuit_breaker.get_metrics()

        return PortfolioRiskMetrics(
            total_positions=len(self._open_positions),
            total_exposure_sol=self._total_exposure,
            portfolio_heat=self._total_exposure / self._capital if self._capital > 0 else 0,
            daily_realized_pnl=cb_metrics["daily_pnl"],
            consecutive_losses=cb_metrics["consecutive_losses"],
            circuit_breaker_active=not can_trade,
            circuit_breaker_reason=reason,
            cooldown_until=self._circuit_breaker.cooldown_until,
        )

    def format_status(self) -> str:
        """Format risk metrics as a human-readable status string."""
        metrics = self.get_portfolio_metrics()

        lines = [
            "📊 **Risk Management Status**",
            "",
            f"💰 Capital: {self._capital:.2f} SOL",
            f"📈 Total Exposure: {metrics.total_exposure_sol:.4f} SOL",
            f"🔥 Portfolio Heat: {metrics.portfolio_heat:.1%} (max {self._config.max_portfolio_heat:.0%})",
            f"📉 Daily PnL: {metrics.daily_realized_pnl:+.4f} SOL",
            "",
            "🛑 **Stop Loss Settings**",
            f"  • Enabled: {'✅' if self._config.stop_loss.enabled else '❌'}",
            f"  • Type: {self._config.stop_loss.stop_loss_type.value}",
            f"  • Fixed %: {self._config.stop_loss.fixed_percentage:.0%}",
            f"  • Trailing: {self._config.stop_loss.trailing_percentage:.0%} (after {self._config.stop_loss.trailing_activation}X)",
            "",
            "⚡ **Circuit Breaker**",
            f"  • Status: {'🔴 ACTIVE' if metrics.circuit_breaker_active else '🟢 OK'}",
        ]

        if metrics.circuit_breaker_active:
            lines.append(f"  • Reason: {metrics.circuit_breaker_reason}")
            if metrics.cooldown_until:
                lines.append(f"  • Cooldown until: {metrics.cooldown_until.strftime('%H:%M:%S UTC')}")
        else:
            lines.append(f"  • Consecutive Losses: {metrics.consecutive_losses}/{self._config.circuit_breaker.consecutive_loss_limit}")

        return "\n".join(lines)
