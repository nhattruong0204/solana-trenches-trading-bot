"""
Take Profit Strategy Definitions.

This module defines all available take profit strategies and their parameters.
Strategies can be:
- Fixed Exit: Sell at a fixed multiplier (e.g., 2X)
- Trailing Stop: Sell when price drops X% from peak
- Tiered Exit: Sell portions at different multipliers

Each strategy includes:
- Unique ID for persistence
- Display name for UI
- Strategy type and parameters
- Ranking based on backtesting results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, List, Tuple


class StrategyType(str, Enum):
    """Type of take profit strategy."""
    
    TRAILING_STOP = "trailing_stop"
    FIXED_EXIT = "fixed_exit"
    TIERED_EXIT = "tiered_exit"
    
    def __str__(self) -> str:
        return self.value


@dataclass
class TakeProfitStrategy:
    """
    Definition of a take profit strategy.
    
    Attributes:
        id: Unique strategy identifier
        name: Human-readable name
        strategy_type: Type of strategy
        rank: Performance ranking (1 = best)
        enabled: Whether strategy is currently active
        params: Strategy-specific parameters
    """
    
    id: str
    name: str
    strategy_type: StrategyType
    rank: int
    enabled: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    
    # Performance metrics from backtesting
    win_rate: float = 0.0
    net_pnl_sol: float = 0.0
    roi_pct: float = 0.0
    fees_paid: float = 0.0
    avg_mult: float = 0.0
    avg_hold_hours: float = 0.0
    
    def __post_init__(self) -> None:
        """Validate strategy data."""
        if not self.id:
            raise ValueError("Strategy ID cannot be empty")
        if not self.name:
            raise ValueError("Strategy name cannot be empty")
        if self.rank < 1:
            raise ValueError("Rank must be >= 1")
    
    @property
    def short_name(self) -> str:
        """Get abbreviated name for buttons."""
        if self.strategy_type == StrategyType.TRAILING_STOP:
            pct = self.params.get("stop_pct", 0.25)
            return f"Trail {int(pct*100)}%"
        elif self.strategy_type == StrategyType.FIXED_EXIT:
            mult = self.params.get("target_mult", 2.0)
            return f"Fixed {mult}X"
        elif self.strategy_type == StrategyType.TIERED_EXIT:
            tiers = self.params.get("tiers", [])
            if len(tiers) == 2:
                return f"Tiered {tiers[0][0]}X+{tiers[1][0]}X"
            elif len(tiers) == 3:
                return f"Tiered 3-way"
            return "Tiered"
        return self.name[:12]
    
    @property
    def display_status(self) -> str:
        """Get status emoji for display."""
        return "✅" if self.enabled else "⬜"
    
    @property
    def rank_emoji(self) -> str:
        """Get rank display emoji."""
        if self.rank == 1:
            return "🥇"
        elif self.rank == 2:
            return "🥈"
        elif self.rank == 3:
            return "🥉"
        return f"#{self.rank}"
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize strategy to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "rank": self.rank,
            "enabled": self.enabled,
            "params": self.params,
            "win_rate": self.win_rate,
            "net_pnl_sol": self.net_pnl_sol,
            "roi_pct": self.roi_pct,
            "fees_paid": self.fees_paid,
            "avg_mult": self.avg_mult,
            "avg_hold_hours": self.avg_hold_hours,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TakeProfitStrategy:
        """Deserialize strategy from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            strategy_type=StrategyType(data["strategy_type"]),
            rank=data.get("rank", 99),
            enabled=data.get("enabled", False),
            params=data.get("params", {}),
            win_rate=data.get("win_rate", 0.0),
            net_pnl_sol=data.get("net_pnl_sol", 0.0),
            roi_pct=data.get("roi_pct", 0.0),
            fees_paid=data.get("fees_paid", 0.0),
            avg_mult=data.get("avg_mult", 0.0),
            avg_hold_hours=data.get("avg_hold_hours", 0.0),
        )


# =============================================================================
# PREDEFINED STRATEGIES (based on backtesting results)
# =============================================================================

# Trailing Stop Strategies (ranked by performance)
TRAILING_STOP_15 = TakeProfitStrategy(
    id="trailing_15",
    name="Trailing Stop (15%)",
    strategy_type=StrategyType.TRAILING_STOP,
    rank=1,
    params={"stop_pct": 0.15},
    win_rate=77.3,
    net_pnl_sol=4.0318,
    roi_pct=40.3,
    fees_paid=0.2259,
    avg_mult=2.833,
    avg_hold_hours=0.1,
)

TRAILING_STOP_20 = TakeProfitStrategy(
    id="trailing_20",
    name="Trailing Stop (20%)",
    strategy_type=StrategyType.TRAILING_STOP,
    rank=2,
    params={"stop_pct": 0.20},
    win_rate=77.3,
    net_pnl_sol=3.6733,
    roi_pct=36.7,
    fees_paid=0.2167,
    avg_mult=2.670,
    avg_hold_hours=0.1,
)

TRAILING_STOP_25 = TakeProfitStrategy(
    id="trailing_25",
    name="Trailing Stop (25%)",
    strategy_type=StrategyType.TRAILING_STOP,
    rank=3,
    params={"stop_pct": 0.25},
    win_rate=77.3,
    net_pnl_sol=3.3147,
    roi_pct=33.1,
    fees_paid=0.2075,
    avg_mult=2.507,
    avg_hold_hours=0.1,
)

TRAILING_STOP_30 = TakeProfitStrategy(
    id="trailing_30",
    name="Trailing Stop (30%)",
    strategy_type=StrategyType.TRAILING_STOP,
    rank=4,
    params={"stop_pct": 0.30},
    win_rate=68.2,
    net_pnl_sol=2.9562,
    roi_pct=29.6,
    fees_paid=0.1984,
    avg_mult=2.344,
    avg_hold_hours=0.1,
)

# Fixed Exit Strategies (ranked by performance)
FIXED_EXIT_5X = TakeProfitStrategy(
    id="fixed_5x",
    name="Fixed Exit 5.0X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=5,
    params={"target_mult": 5.0, "stop_loss_mult": 0.5},
    win_rate=45.5,
    net_pnl_sol=2.6241,
    roi_pct=26.2,
    fees_paid=0.1898,
    avg_mult=2.193,
    avg_hold_hours=4.5,
)

FIXED_EXIT_4X = TakeProfitStrategy(
    id="fixed_4x",
    name="Fixed Exit 4.0X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=6,
    params={"target_mult": 4.0, "stop_loss_mult": 0.5},
    win_rate=50.0,
    net_pnl_sol=2.3165,
    roi_pct=23.2,
    fees_paid=0.1819,
    avg_mult=2.053,
    avg_hold_hours=3.3,
)

FIXED_EXIT_3X = TakeProfitStrategy(
    id="fixed_3x",
    name="Fixed Exit 3.0X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=8,
    params={"target_mult": 3.0, "stop_loss_mult": 0.5},
    win_rate=54.5,
    net_pnl_sol=1.6053,
    roi_pct=16.1,
    fees_paid=0.1637,
    avg_mult=1.730,
    avg_hold_hours=2.7,
)

FIXED_EXIT_2_5X = TakeProfitStrategy(
    id="fixed_2_5x",
    name="Fixed Exit 2.5X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=10,
    params={"target_mult": 2.5, "stop_loss_mult": 0.5},
    win_rate=59.1,
    net_pnl_sol=1.3028,
    roi_pct=13.0,
    fees_paid=0.1560,
    avg_mult=1.592,
    avg_hold_hours=1.8,
)

FIXED_EXIT_2X = TakeProfitStrategy(
    id="fixed_2x",
    name="Fixed Exit 2.0X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=11,
    params={"target_mult": 2.0, "stop_loss_mult": 0.5},
    win_rate=72.7,
    net_pnl_sol=1.1132,
    roi_pct=11.1,
    fees_paid=0.1511,
    avg_mult=1.506,
    avg_hold_hours=0.3,
)

FIXED_EXIT_1_5X = TakeProfitStrategy(
    id="fixed_1_5x",
    name="Fixed Exit 1.5X",
    strategy_type=StrategyType.FIXED_EXIT,
    rank=13,
    params={"target_mult": 1.5, "stop_loss_mult": 0.5},
    win_rate=72.7,
    net_pnl_sol=0.3546,
    roi_pct=3.5,
    fees_paid=0.1316,
    avg_mult=1.161,
    avg_hold_hours=0.3,
)

# Tiered Exit Strategies (ranked by performance)
TIERED_2X_3X_5X = TakeProfitStrategy(
    id="tiered_2_3_5",
    name="Tiered 2.0X(33%)+3.0X(33%)+5.0X(34%)",
    strategy_type=StrategyType.TIERED_EXIT,
    rank=7,
    params={
        "tiers": [(2.0, 0.33), (3.0, 0.33), (5.0, 0.34)],
        "trailing_pct": 0.25,
    },
    win_rate=63.6,
    net_pnl_sol=1.8671,
    roi_pct=18.7,
    fees_paid=0.1704,
    avg_mult=1.849,
    avg_hold_hours=10.5,
)

TIERED_2X_3X = TakeProfitStrategy(
    id="tiered_2_3",
    name="Tiered 2.0X(50%)+3.0X(50%)",
    strategy_type=StrategyType.TIERED_EXIT,
    rank=9,
    params={
        "tiers": [(2.0, 0.50), (3.0, 0.50)],
        "trailing_pct": 0.25,
    },
    win_rate=72.7,
    net_pnl_sol=1.4540,
    roi_pct=14.5,
    fees_paid=0.1598,
    avg_mult=1.661,
    avg_hold_hours=7.6,
)

TIERED_1_5X_2_5X = TakeProfitStrategy(
    id="tiered_1_5_2_5",
    name="Tiered 1.5X(50%)+2.5X(50%)",
    strategy_type=StrategyType.TIERED_EXIT,
    rank=12,
    params={
        "tiers": [(1.5, 0.50), (2.5, 0.50)],
        "trailing_pct": 0.25,
    },
    win_rate=68.2,
    net_pnl_sol=0.9157,
    roi_pct=9.2,
    fees_paid=0.1460,
    avg_mult=1.416,
    avg_hold_hours=6.0,
)


# All available strategies sorted by rank
ALL_STRATEGIES: List[TakeProfitStrategy] = sorted([
    TRAILING_STOP_15,
    TRAILING_STOP_20,
    TRAILING_STOP_25,
    TRAILING_STOP_30,
    FIXED_EXIT_5X,
    FIXED_EXIT_4X,
    FIXED_EXIT_3X,
    FIXED_EXIT_2_5X,
    FIXED_EXIT_2X,
    FIXED_EXIT_1_5X,
    TIERED_2X_3X_5X,
    TIERED_2X_3X,
    TIERED_1_5X_2_5X,
], key=lambda s: s.rank)


def get_strategy_by_id(strategy_id: str) -> Optional[TakeProfitStrategy]:
    """Get a strategy by its ID."""
    for strategy in ALL_STRATEGIES:
        if strategy.id == strategy_id:
            return strategy
    return None


def get_default_strategies() -> List[TakeProfitStrategy]:
    """Get all strategies with default enabled state."""
    return [TakeProfitStrategy.from_dict(s.to_dict()) for s in ALL_STRATEGIES]


class StrategyManager:
    """
    Manages strategy selection and state.
    
    Handles enabling/disabling strategies and determining
    which strategy to use for selling.
    """
    
    def __init__(self, strategies: Optional[List[TakeProfitStrategy]] = None):
        """Initialize with optional custom strategy list."""
        self._strategies: dict[str, TakeProfitStrategy] = {}
        
        # Initialize with all strategies
        for strategy in (strategies or get_default_strategies()):
            self._strategies[strategy.id] = strategy
    
    @property
    def strategies(self) -> List[TakeProfitStrategy]:
        """Get all strategies sorted by rank."""
        return sorted(self._strategies.values(), key=lambda s: s.rank)
    
    @property
    def enabled_strategies(self) -> List[TakeProfitStrategy]:
        """Get only enabled strategies."""
        return [s for s in self.strategies if s.enabled]
    
    @property
    def active_strategy(self) -> Optional[TakeProfitStrategy]:
        """Get the highest-ranked enabled strategy."""
        enabled = self.enabled_strategies
        if enabled:
            return min(enabled, key=lambda s: s.rank)
        return None
    
    def get_strategy(self, strategy_id: str) -> Optional[TakeProfitStrategy]:
        """Get strategy by ID."""
        return self._strategies.get(strategy_id)
    
    def toggle_strategy(self, strategy_id: str) -> bool:
        """
        Toggle a strategy's enabled state.
        
        Returns:
            New enabled state, or None if strategy not found
        """
        strategy = self._strategies.get(strategy_id)
        if strategy:
            strategy.enabled = not strategy.enabled
            return strategy.enabled
        return False
    
    def enable_strategy(self, strategy_id: str) -> bool:
        """Enable a specific strategy."""
        strategy = self._strategies.get(strategy_id)
        if strategy:
            strategy.enabled = True
            return True
        return False
    
    def disable_strategy(self, strategy_id: str) -> bool:
        """Disable a specific strategy."""
        strategy = self._strategies.get(strategy_id)
        if strategy:
            strategy.enabled = False
            return True
        return False
    
    def disable_all(self) -> None:
        """Disable all strategies."""
        for strategy in self._strategies.values():
            strategy.enabled = False
    
    def enable_only(self, strategy_id: str) -> bool:
        """Enable only one strategy, disable all others."""
        self.disable_all()
        return self.enable_strategy(strategy_id)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for persistence."""
        return {
            "strategies": {
                sid: s.to_dict() for sid, s in self._strategies.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyManager:
        """Deserialize from dictionary."""
        manager = cls()
        
        strategies_data = data.get("strategies", {})
        for sid, sdata in strategies_data.items():
            if sid in manager._strategies:
                # Update enabled state from saved data
                manager._strategies[sid].enabled = sdata.get("enabled", False)
        
        return manager
    
    def should_sell(
        self,
        current_multiplier: float,
        peak_multiplier: float,
        entry_multiplier: float = 1.0,
    ) -> Tuple[bool, Optional[str], float]:
        """
        Determine if we should sell based on enabled strategies.
        
        Args:
            current_multiplier: Current price relative to entry
            peak_multiplier: Highest price reached relative to entry
            entry_multiplier: Entry multiplier (usually 1.0)
            
        Returns:
            Tuple of (should_sell, reason, sell_percentage)
        """
        strategy = self.active_strategy
        
        if not strategy:
            return False, None, 0.0
        
        if strategy.strategy_type == StrategyType.TRAILING_STOP:
            stop_pct = strategy.params.get("stop_pct", 0.25)
            stop_level = peak_multiplier * (1 - stop_pct)
            
            if current_multiplier <= stop_level:
                return True, f"Trailing stop at {stop_level:.2f}X (peak: {peak_multiplier:.2f}X)", 100.0
        
        elif strategy.strategy_type == StrategyType.FIXED_EXIT:
            target_mult = strategy.params.get("target_mult", 2.0)
            stop_loss = strategy.params.get("stop_loss_mult", 0.5)
            
            if current_multiplier >= target_mult:
                return True, f"Target {target_mult}X reached", 100.0
            elif current_multiplier <= stop_loss:
                return True, f"Stop loss at {stop_loss}X triggered", 100.0
        
        elif strategy.strategy_type == StrategyType.TIERED_EXIT:
            tiers = strategy.params.get("tiers", [(2.0, 0.50), (3.0, 0.50)])
            
            # Check each tier
            for tier_mult, tier_pct in tiers:
                if current_multiplier >= tier_mult:
                    return True, f"Tier {tier_mult}X reached", tier_pct * 100
        
        return False, None, 0.0
