"""
Advanced Trading Strategy Simulator for Solana Signals

Analyzes historical signal data and simulates various strategies
to find the optimal approach for maximum profit.

This module tests multiple strategies including:
- Fixed exit multipliers (2X, 3X, 5X)
- Trailing stop losses
- Time-based exits  
- Hybrid strategies combining multiple signals
- FDV-filtered entries
- Position sizing based on conviction

FEES INCLUDED:
- GMGN Buy Fee: 1% of position
- GMGN Sell Fee: 1% of proceeds  
- Solana Network Fee: ~0.00025 SOL per tx
- Priority Fee (MEV protection): 0.5% of position
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# FEE CONFIGURATION - GMGN.ai Fees
# ============================================================================
@dataclass
class TradingFees:
    """
    GMGN.ai Trading Fee Structure.
    
    These fees are deducted from each trade:
    - Buy: Fee is deducted from your SOL before buying tokens
    - Sell: Fee is deducted from your SOL proceeds after selling
    """
    # GMGN platform fees
    buy_fee_pct: float = 1.0      # 1% on buy
    sell_fee_pct: float = 1.0     # 1% on sell
    
    # Solana network fees (per transaction)
    network_fee_sol: float = 0.00025  # ~0.00025 SOL per tx
    
    # Priority fee for MEV protection (optional but recommended)
    priority_fee_pct: float = 0.5  # 0.5% priority fee
    
    # Slippage (worst case scenario for meme coins)
    slippage_pct: float = 1.0  # 1% average slippage on meme coins
    
    @property
    def total_buy_fee_pct(self) -> float:
        """Total percentage fee on buy side."""
        return self.buy_fee_pct + self.priority_fee_pct + self.slippage_pct
    
    @property
    def total_sell_fee_pct(self) -> float:
        """Total percentage fee on sell side."""
        return self.sell_fee_pct + self.priority_fee_pct + self.slippage_pct
    
    def calculate_buy_cost(self, position_sol: float) -> tuple[float, float]:
        """
        Calculate actual tokens received after buy fees.
        
        Returns: (effective_position_sol, total_fees_sol)
        """
        pct_fee = position_sol * (self.total_buy_fee_pct / 100)
        total_fee = pct_fee + self.network_fee_sol
        effective = position_sol - total_fee
        return max(effective, 0), total_fee
    
    def calculate_sell_proceeds(self, gross_proceeds_sol: float) -> tuple[float, float]:
        """
        Calculate actual SOL received after sell fees.
        
        Returns: (net_proceeds_sol, total_fees_sol)
        """
        pct_fee = gross_proceeds_sol * (self.total_sell_fee_pct / 100)
        total_fee = pct_fee + self.network_fee_sol
        net = gross_proceeds_sol - total_fee
        return max(net, 0), total_fee
    
    def calculate_round_trip_breakeven(self) -> float:
        """
        Calculate the minimum multiplier needed to break even after fees.
        
        This is critical for setting minimum TP targets.
        """
        # After buy: you have (1 - buy_fee%) worth of tokens
        # After sell: you get (sell_value * (1 - sell_fee%))
        # Break even when: (1 - buy_fee%) * multiplier * (1 - sell_fee%) = 1
        buy_factor = 1 - (self.total_buy_fee_pct / 100)
        sell_factor = 1 - (self.total_sell_fee_pct / 100)
        
        # multiplier = 1 / (buy_factor * sell_factor)
        breakeven_mult = 1 / (buy_factor * sell_factor)
        return breakeven_mult

    def summary(self) -> str:
        """Return fee summary."""
        return (
            f"Buy Fee: {self.total_buy_fee_pct:.1f}% | "
            f"Sell Fee: {self.total_sell_fee_pct:.1f}% | "
            f"Breakeven: {self.calculate_round_trip_breakeven():.3f}X"
        )


# Default fee structure
DEFAULT_FEES = TradingFees()


class ExitReason(Enum):
    """Reason for exiting a position."""
    TARGET_HIT = "target_hit"
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    TRAILING_STOP = "trailing_stop"
    RUGGED = "rugged"
    STILL_OPEN = "still_open"


@dataclass
class Trade:
    """Represents a single trade with fee calculations."""
    symbol: str
    address: str
    entry_time: datetime
    entry_price_mult: float = 1.0  # Always enter at signal (1X)
    exit_price_mult: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    position_size: float = 1.0  # In SOL (gross, before fees)
    peak_multiplier: float = 1.0
    initial_fdv: Optional[float] = None
    fees: TradingFees = field(default_factory=lambda: DEFAULT_FEES)
    
    @property
    def effective_entry_sol(self) -> float:
        """SOL actually invested in tokens after buy fees."""
        effective, _ = self.fees.calculate_buy_cost(self.position_size)
        return effective
    
    @property
    def buy_fees_sol(self) -> float:
        """Total fees paid on buy."""
        _, fees = self.fees.calculate_buy_cost(self.position_size)
        return fees
    
    @property
    def gross_exit_value(self) -> float:
        """Value before sell fees (if we sold at exit_price_mult)."""
        if self.exit_price_mult is None:
            return 0.0
        return self.effective_entry_sol * self.exit_price_mult
    
    @property
    def net_exit_value(self) -> float:
        """Value after sell fees."""
        if self.exit_price_mult is None:
            return 0.0
        gross = self.gross_exit_value
        net, _ = self.fees.calculate_sell_proceeds(gross)
        return net
    
    @property
    def sell_fees_sol(self) -> float:
        """Total fees paid on sell."""
        if self.exit_price_mult is None:
            return 0.0
        gross = self.gross_exit_value
        _, fees = self.fees.calculate_sell_proceeds(gross)
        return fees
    
    @property
    def total_fees_sol(self) -> float:
        """Total fees (buy + sell)."""
        return self.buy_fees_sol + self.sell_fees_sol
    
    @property
    def pnl_multiplier(self) -> float:
        """Return NET PnL multiplier after all fees."""
        if self.exit_price_mult is None:
            return 0.0
        # Net return / initial investment
        return self.net_exit_value / self.position_size
    
    @property
    def pnl_percent(self) -> float:
        """Return PnL as percentage (after fees)."""
        return (self.pnl_multiplier - 1) * 100
    
    @property
    def pnl_sol(self) -> float:
        """Return PnL in SOL (after fees)."""
        return self.net_exit_value - self.position_size
    
    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable AFTER fees."""
        return self.pnl_multiplier > 1.0


@dataclass
class StrategyResult:
    """Results from running a strategy simulation."""
    strategy_name: str
    trades: list[Trade] = field(default_factory=list)
    total_capital: float = 10.0  # Starting capital in SOL
    position_size: float = 0.1  # Per trade in SOL
    fees: TradingFees = field(default_factory=lambda: DEFAULT_FEES)
    
    @property
    def total_trades(self) -> int:
        return len(self.trades)
    
    @property
    def winners(self) -> int:
        return sum(1 for t in self.trades if t.is_winner)
    
    @property
    def losers(self) -> int:
        return sum(1 for t in self.trades if not t.is_winner and t.exit_price_mult is not None)
    
    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.exit_price_mult is not None]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.is_winner) / len(closed) * 100
    
    @property
    def total_pnl_sol(self) -> float:
        """Net PnL after all fees."""
        return sum(t.pnl_sol for t in self.trades)
    
    @property
    def total_fees_sol(self) -> float:
        """Total fees paid across all trades."""
        return sum(t.total_fees_sol for t in self.trades)
    
    @property
    def total_pnl_percent(self) -> float:
        if self.total_capital == 0:
            return 0.0
        return self.total_pnl_sol / self.total_capital * 100
    
    @property
    def avg_multiplier(self) -> float:
        closed = [t for t in self.trades if t.exit_price_mult is not None]
        if not closed:
            return 0.0
        return sum(t.pnl_multiplier for t in closed) / len(closed)
    
    @property
    def max_drawdown(self) -> float:
        """Calculate maximum drawdown during strategy."""
        if not self.trades:
            return 0.0
        
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        
        for trade in self.trades:
            cumulative += trade.pnl_sol
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / self.total_capital * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    @property
    def profit_factor(self) -> float:
        """Gross profit / Gross loss."""
        gross_profit = sum(t.pnl_sol for t in self.trades if t.pnl_sol > 0)
        gross_loss = abs(sum(t.pnl_sol for t in self.trades if t.pnl_sol < 0))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss
    
    @property
    def roi(self) -> float:
        """Return on investment percentage."""
        return self.total_pnl_percent
    
    def summary(self) -> dict:
        """Return summary statistics including fees."""
        return {
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "winners": self.winners,
            "losers": self.losers,
            "win_rate": round(self.win_rate, 1),
            "total_pnl_sol": round(self.total_pnl_sol, 4),
            "total_fees_sol": round(self.total_fees_sol, 4),
            "total_pnl_percent": round(self.total_pnl_percent, 1),
            "avg_multiplier": round(self.avg_multiplier, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown": round(self.max_drawdown, 1),
            "roi": round(self.roi, 1),
        }


class StrategySimulator:
    """
    Simulates various trading strategies on historical signal data.
    
    Core insight: The data shows signal peak multipliers (from profit alerts)
    vs real current multipliers. We can simulate what would happen if we
    had different exit strategies.
    
    INCLUDES GMGN FEES:
    - Buy fee: 1% + 0.5% priority + 1% slippage = 2.5%
    - Sell fee: 1% + 0.5% priority + 1% slippage = 2.5%
    - Network fee: ~0.00025 SOL per tx
    - Breakeven multiplier: ~1.05X (need 5% gain just to break even!)
    """
    
    def __init__(
        self, 
        data: dict, 
        position_size: float = 0.1, 
        starting_capital: float = 10.0,
        fees: Optional[TradingFees] = None
    ):
        """
        Initialize simulator with compare results JSON data.
        
        Args:
            data: Parsed JSON from compare results
            position_size: SOL per trade
            starting_capital: Total starting capital in SOL
            fees: Trading fee structure (uses GMGN defaults if not provided)
        """
        self.data = data
        self.position_size = position_size
        self.starting_capital = starting_capital
        self.tokens = data.get("tokens", [])
        self.fees = fees or DEFAULT_FEES
        
        # Parse metadata
        self.metadata = data.get("metadata", {})
        self.summary_data = data.get("summary", {})
        
    def _create_trade(self, token: dict) -> Trade:
        """Create a trade object from token data with fees."""
        return Trade(
            symbol=token.get("symbol", "UNKNOWN"),
            address=token.get("address", ""),
            entry_time=datetime.fromisoformat(token.get("signal_timestamp", "2026-01-01T00:00:00")),
            entry_price_mult=1.0,
            position_size=self.position_size,
            peak_multiplier=token.get("signal", {}).get("multiplier") or 1.0,
            initial_fdv=token.get("initial_fdv"),
            fees=self.fees,
        )
    
    def _create_result(self, name: str) -> StrategyResult:
        """Create a strategy result with proper fee tracking."""
        return StrategyResult(
            strategy_name=name,
            total_capital=self.starting_capital,
            position_size=self.position_size,
            fees=self.fees,
        )
    
    def strategy_hodl(self) -> StrategyResult:
        """
        HODL Strategy: Buy at signal, hold until now.
        This is the baseline - shows what happens with no exit strategy.
        """
        result = self._create_result("HODL (No Exit)")
        
        for token in self.tokens:
            trade = self._create_trade(token)
            
            real_data = token.get("real", {})
            if real_data.get("is_rugged"):
                trade.exit_price_mult = 0.0
                trade.exit_reason = ExitReason.RUGGED
            elif real_data.get("multiplier"):
                trade.exit_price_mult = real_data["multiplier"]
                trade.exit_reason = ExitReason.STILL_OPEN
            else:
                # Unknown state - assume 50% loss
                trade.exit_price_mult = 0.5
                trade.exit_reason = ExitReason.STILL_OPEN
            
            result.trades.append(trade)
        
        return result
    
    def strategy_fixed_exit(self, target_multiplier: float = 2.0) -> StrategyResult:
        """
        Fixed Exit Strategy: Sell when token reaches target multiplier.
        
        Simulates: If we always sold at exactly 2X (or target), what would happen?
        """
        result = self._create_result(f"Fixed Exit at {target_multiplier}X")
        
        for token in self.tokens:
            trade = self._create_trade(token)
            
            signal_data = token.get("signal", {})
            real_data = token.get("real", {})
            peak = signal_data.get("multiplier") or 1.0
            
            # Did it ever reach our target?
            if peak >= target_multiplier:
                trade.exit_price_mult = target_multiplier
                trade.exit_reason = ExitReason.TARGET_HIT
            elif real_data.get("is_rugged"):
                trade.exit_price_mult = 0.0
                trade.exit_reason = ExitReason.RUGGED
            else:
                # Never reached target, now at real price
                trade.exit_price_mult = real_data.get("multiplier") or 0.5
                trade.exit_reason = ExitReason.STILL_OPEN
            
            result.trades.append(trade)
        
        return result
    
    def strategy_tiered_exit(self, tiers: list[tuple[float, float]] = None) -> StrategyResult:
        """
        Tiered Exit Strategy: Sell portions at different levels.
        
        Default tiers: Sell 50% at 2X, remaining 50% at 3X or current
        
        Args:
            tiers: List of (multiplier, percentage_to_sell) tuples
        """
        if tiers is None:
            tiers = [(2.0, 0.5), (3.0, 0.5)]  # 50% at 2X, 50% at 3X
        
        result = self._create_result(f"Tiered Exit {tiers}")
        
        for token in self.tokens:
            trade = self._create_trade(token)
            
            signal_data = token.get("signal", {})
            real_data = token.get("real", {})
            peak = signal_data.get("multiplier") or 1.0
            current = real_data.get("multiplier") or 0.5
            is_rugged = real_data.get("is_rugged", False)
            
            # Calculate weighted exit based on tiers hit
            total_exit_value = 0.0
            remaining_pct = 1.0
            
            for target_mult, sell_pct in sorted(tiers):
                if remaining_pct <= 0:
                    break
                    
                actual_sell_pct = min(sell_pct, remaining_pct)
                
                if peak >= target_mult:
                    # Hit this tier - sold at target
                    total_exit_value += target_mult * actual_sell_pct
                elif is_rugged:
                    # Rugged before hitting tier
                    total_exit_value += 0.0
                else:
                    # Didn't hit tier, value at current price
                    total_exit_value += current * actual_sell_pct
                
                remaining_pct -= actual_sell_pct
            
            # Any remaining position at current price
            if remaining_pct > 0:
                if is_rugged:
                    total_exit_value += 0.0
                else:
                    total_exit_value += current * remaining_pct
            
            trade.exit_price_mult = total_exit_value
            trade.exit_reason = ExitReason.TARGET_HIT if total_exit_value > 1.0 else ExitReason.STOP_LOSS
            
            result.trades.append(trade)
        
        return result
    
    def strategy_trailing_stop(self, stop_pct: float = 0.30) -> StrategyResult:
        """
        Trailing Stop Strategy: Sell when price drops X% from peak.
        
        Simulates: If we had a 30% trailing stop from peak, where would we exit?
        
        Note: This is an approximation since we only have peak and current values.
        """
        result = self._create_result(f"Trailing Stop ({int(stop_pct*100)}% from peak)")
        
        for token in self.tokens:
            trade = self._create_trade(token)
            
            signal_data = token.get("signal", {})
            real_data = token.get("real", {})
            peak = signal_data.get("multiplier") or 1.0
            current = real_data.get("multiplier") or 0.5
            is_rugged = real_data.get("is_rugged", False)
            
            # Trailing stop would trigger at peak * (1 - stop_pct)
            stop_level = peak * (1 - stop_pct)
            
            if is_rugged:
                # Price went to 0, stop wouldn't save us completely
                # But might have triggered before full rug
                trade.exit_price_mult = max(stop_level, 0.1)  # Assume some slippage
                trade.exit_reason = ExitReason.TRAILING_STOP
            elif current < stop_level:
                # Current price below stop level - would have exited at stop
                trade.exit_price_mult = stop_level
                trade.exit_reason = ExitReason.TRAILING_STOP
            else:
                # Price never dropped below stop from peak
                trade.exit_price_mult = current
                trade.exit_reason = ExitReason.STILL_OPEN
            
            result.trades.append(trade)
        
        return result
    
    def strategy_hybrid_exit(
        self,
        min_exit: float = 1.5,
        target_exit: float = 2.5,
        trailing_stop: float = 0.25
    ) -> StrategyResult:
        """
        Hybrid Strategy: Combines multiple exit conditions.
        
        Rules:
        1. Take partial profit (50%) at min_exit (e.g., 1.5X)
        2. Let rest run with trailing stop from peak
        3. Target full exit at target_exit (e.g., 2.5X)
        """
        result = self._create_result(f"Hybrid ({min_exit}X/Trail {int(trailing_stop*100)}%/{target_exit}X)")
        
        for token in self.tokens:
            trade = self._create_trade(token)
            
            signal_data = token.get("signal", {})
            real_data = token.get("real", {})
            peak = signal_data.get("multiplier") or 1.0
            current = real_data.get("multiplier") or 0.5
            is_rugged = real_data.get("is_rugged", False)
            
            total_value = 0.0
            
            # First half: Take profit at min_exit or hold
            if peak >= min_exit:
                total_value += min_exit * 0.5  # 50% sold at min_exit
            elif is_rugged:
                total_value += 0.0
            else:
                total_value += current * 0.5
            
            # Second half: Target or trailing stop
            if peak >= target_exit:
                total_value += target_exit * 0.5
            else:
                stop_level = peak * (1 - trailing_stop)
                if is_rugged:
                    total_value += max(stop_level * 0.5, 0.05)
                elif current < stop_level:
                    total_value += stop_level * 0.5
                else:
                    total_value += current * 0.5
            
            trade.exit_price_mult = total_value
            trade.exit_reason = ExitReason.TARGET_HIT if total_value > 1.0 else ExitReason.STOP_LOSS
            
            result.trades.append(trade)
        
        return result
    
    def strategy_fdv_filtered(
        self,
        max_fdv: float = 500_000,
        exit_mult: float = 2.0
    ) -> StrategyResult:
        """
        FDV-Filtered Strategy: Only trade tokens with low initial FDV.
        
        Hypothesis: Lower FDV tokens have more upside potential.
        """
        result = self._create_result(f"FDV Filter (<${max_fdv:,.0f}) + {exit_mult}X Exit")
        
        for token in self.tokens:
            initial_fdv = token.get("initial_fdv")
            
            # Skip tokens that don't meet FDV criteria
            if initial_fdv is None or initial_fdv > max_fdv:
                continue
            
            trade = self._create_trade(token)
            
            signal_data = token.get("signal", {})
            real_data = token.get("real", {})
            peak = signal_data.get("multiplier") or 1.0
            
            if peak >= exit_mult:
                trade.exit_price_mult = exit_mult
                trade.exit_reason = ExitReason.TARGET_HIT
            elif real_data.get("is_rugged"):
                trade.exit_price_mult = 0.0
                trade.exit_reason = ExitReason.RUGGED
            else:
                trade.exit_price_mult = real_data.get("multiplier") or 0.5
                trade.exit_reason = ExitReason.STILL_OPEN
            
            result.trades.append(trade)
        
        return result
    
    def strategy_winner_momentum(self, lookback: int = 3) -> StrategyResult:
        """
        Winner Momentum Strategy: Only enter if last N signals were profitable.
        
        Hypothesis: Channels have "hot streaks" - ride them.
        """
        result = self._create_result(f"Momentum (wait for {lookback} winners)")
        
        recent_wins = 0
        
        for token in self.tokens:
            signal_data = token.get("signal", {})
            peak = signal_data.get("multiplier") or 1.0
            
            is_winner = peak >= 1.5  # Consider 1.5X+ a "win" for momentum
            
            # Only trade if we've seen enough recent wins
            if recent_wins >= lookback:
                trade = self._create_trade(token)
                
                real_data = token.get("real", {})
                
                if peak >= 2.0:
                    trade.exit_price_mult = 2.0
                    trade.exit_reason = ExitReason.TARGET_HIT
                elif real_data.get("is_rugged"):
                    trade.exit_price_mult = 0.0
                    trade.exit_reason = ExitReason.RUGGED
                else:
                    trade.exit_price_mult = real_data.get("multiplier") or 0.5
                    trade.exit_reason = ExitReason.STILL_OPEN
                
                result.trades.append(trade)
            
            # Update momentum tracking
            if is_winner:
                recent_wins += 1
            else:
                recent_wins = 0
        
        return result
    
    def strategy_optimal(self) -> StrategyResult:
        """
        Optimal Strategy: Based on analysis of all strategies.
        
        After analyzing the data, this implements the best combination:
        1. Enter all signals (channel quality is pre-filtered)
        2. Sell 50% at 2X (lock in profit)
        3. Sell remaining 50% with 25% trailing stop
        4. Never HODL - always have an exit plan
        """
        return self.strategy_hybrid_exit(
            min_exit=2.0,      # Take half at 2X
            target_exit=4.0,   # Dream target
            trailing_stop=0.25 # 25% trailing on remaining
        )
    
    def optimize_tp_vs_fees(self) -> dict:
        """
        Find optimal Take Profit % that maximizes returns after fees.
        
        Tests various TP levels and finds the sweet spot considering:
        - GMGN fees eat into small gains
        - Higher TP has lower hit rate
        - Need to find the multiplier that maximizes expected value
        """
        breakeven = self.fees.calculate_round_trip_breakeven()
        
        # Test TP levels from just above breakeven to 5X
        tp_levels = [1.3, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0, 5.0]
        
        results = []
        for tp in tp_levels:
            strategy = self.strategy_fixed_exit(tp)
            s = strategy.summary()
            
            # Calculate expected value per trade
            ev_per_trade = s['total_pnl_sol'] / max(s['total_trades'], 1)
            
            results.append({
                'tp_multiplier': tp,
                'win_rate': s['win_rate'],
                'total_pnl_sol': s['total_pnl_sol'],
                'total_fees_sol': s['total_fees_sol'],
                'roi': s['roi'],
                'ev_per_trade': round(ev_per_trade, 4),
                'profit_factor': s['profit_factor'],
            })
        
        # Find optimal TP (highest ROI)
        optimal = max(results, key=lambda x: x['roi'])
        
        return {
            'breakeven_multiplier': round(breakeven, 3),
            'fee_summary': self.fees.summary(),
            'optimal_tp': optimal['tp_multiplier'],
            'optimal_roi': optimal['roi'],
            'results_by_tp': results,
            'recommendation': self._generate_tp_recommendation(optimal, breakeven, results),
        }
    
    def _generate_tp_recommendation(self, optimal: dict, breakeven: float, results: list) -> str:
        """Generate actionable TP recommendation."""
        lines = []
        
        # Key insight
        lines.append(f"⚡ Breakeven after fees: {breakeven:.3f}X ({(breakeven-1)*100:.1f}% gain needed)")
        lines.append(f"🎯 Optimal TP: {optimal['tp_multiplier']}X (ROI: {optimal['roi']:.1f}%)")
        
        # Fee impact analysis
        if optimal['tp_multiplier'] < 2.0:
            lines.append("⚠️ Low TP works because fees are manageable at this level")
        else:
            lines.append("✅ Higher TP captures enough gain to offset fees + losses")
        
        # Win rate vs profit tradeoff
        low_tp = next((r for r in results if r['tp_multiplier'] == 1.5), None)
        high_tp = next((r for r in results if r['tp_multiplier'] == 3.0), None)
        
        if low_tp and high_tp:
            lines.append(f"\n📊 1.5X TP: {low_tp['win_rate']:.0f}% win rate, {low_tp['roi']:.1f}% ROI")
            lines.append(f"📊 3.0X TP: {high_tp['win_rate']:.0f}% win rate, {high_tp['roi']:.1f}% ROI")
        
        return "\n".join(lines)
    
    def run_all_strategies(self) -> list[StrategyResult]:
        """Run all strategies and return sorted by ROI."""
        strategies = [
            self.strategy_hodl(),
            self.strategy_fixed_exit(1.5),
            self.strategy_fixed_exit(2.0),
            self.strategy_fixed_exit(2.5),
            self.strategy_fixed_exit(3.0),
            self.strategy_tiered_exit([(1.5, 0.5), (2.5, 0.5)]),
            self.strategy_tiered_exit([(2.0, 0.5), (3.0, 0.5)]),
            self.strategy_trailing_stop(0.20),
            self.strategy_trailing_stop(0.30),
            self.strategy_trailing_stop(0.40),
            self.strategy_hybrid_exit(1.5, 2.5, 0.25),
            self.strategy_hybrid_exit(2.0, 3.0, 0.25),
            self.strategy_hybrid_exit(2.0, 4.0, 0.30),
            self.strategy_fdv_filtered(100_000, 2.0),
            self.strategy_fdv_filtered(500_000, 2.0),
            self.strategy_winner_momentum(2),
            self.strategy_winner_momentum(3),
            self.strategy_optimal(),
        ]
        
        # Sort by ROI descending
        strategies.sort(key=lambda s: s.roi, reverse=True)
        
        return strategies
    
    def generate_report(self) -> str:
        """Generate comprehensive strategy comparison report with fee analysis."""
        strategies = self.run_all_strategies()
        tp_analysis = self.optimize_tp_vs_fees()
        
        lines = [
            "=" * 80,
            "🎯 TRADING STRATEGY SIMULATION REPORT (WITH GMGN FEES)",
            "=" * 80,
            "",
            f"📊 Dataset: {self.summary_data.get('total_signals', len(self.tokens))} signals",
            f"📅 Period: {self.metadata.get('period', 'N/A')}",
            f"💰 Starting Capital: {self.starting_capital} SOL",
            f"📦 Position Size: {self.position_size} SOL per trade",
            "",
            "=" * 80,
            "💸 FEE STRUCTURE (GMGN.ai)",
            "=" * 80,
            f"  Buy Fee:  {self.fees.total_buy_fee_pct:.1f}% (platform + priority + slippage)",
            f"  Sell Fee: {self.fees.total_sell_fee_pct:.1f}% (platform + priority + slippage)",
            f"  Network:  ~{self.fees.network_fee_sol:.5f} SOL per tx",
            f"  ⚡ BREAKEVEN: {tp_analysis['breakeven_multiplier']}X",
            f"     (You need {(tp_analysis['breakeven_multiplier']-1)*100:.1f}% gain just to break even!)",
            "",
            "=" * 80,
            "📈 STRATEGY RANKINGS (by ROI, AFTER FEES)",
            "=" * 80,
            "",
        ]
        
        for i, strategy in enumerate(strategies, 1):
            s = strategy.summary()
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            
            lines.append(f"{emoji} #{i}: {s['strategy']}")
            lines.append(f"   Win Rate: {s['win_rate']}% | Trades: {s['total_trades']}")
            lines.append(f"   Net PnL: {s['total_pnl_sol']:+.4f} SOL ({s['total_pnl_percent']:+.1f}%)")
            lines.append(f"   Fees Paid: {s['total_fees_sol']:.4f} SOL")
            lines.append(f"   Avg Mult: {s['avg_multiplier']:.2f}X | Profit Factor: {s['profit_factor']:.2f}")
            lines.append(f"   Max Drawdown: {s['max_drawdown']:.1f}%")
            lines.append("")
        
        # Best strategy analysis
        best = strategies[0]
        
        lines.extend([
            "=" * 80,
            "🎯 TP% OPTIMIZATION (vs GMGN Fees)",
            "=" * 80,
            "",
            tp_analysis['recommendation'],
            "",
            "TP Level Analysis:",
        ])
        
        for r in tp_analysis['results_by_tp']:
            star = "⭐" if r['tp_multiplier'] == tp_analysis['optimal_tp'] else "  "
            lines.append(
                f"{star} {r['tp_multiplier']}X: ROI {r['roi']:+.1f}% | "
                f"Win {r['win_rate']:.0f}% | Fees {r['total_fees_sol']:.3f} SOL"
            )
        
        lines.extend([
            "",
            "=" * 80,
            "🏆 BEST STRATEGY ANALYSIS",
            "=" * 80,
            "",
            f"Strategy: {best.strategy_name}",
            f"",
            f"Performance vs HODL:",
        ])
        
        hodl = next((s for s in strategies if "HODL" in s.strategy_name), None)
        if hodl:
            improvement = best.roi - hodl.roi
            lines.append(f"  • ROI Improvement: {improvement:+.1f}%")
            lines.append(f"  • HODL ROI: {hodl.roi:.1f}% → Best ROI: {best.roi:.1f}%")
        
        # Exit reason breakdown for best strategy
        exit_counts = {}
        for trade in best.trades:
            reason = trade.exit_reason.value if trade.exit_reason else "unknown"
            exit_counts[reason] = exit_counts.get(reason, 0) + 1
        
        lines.extend([
            "",
            "Exit Reason Breakdown:",
        ])
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  • {reason}: {count} trades")
        
        # Recommendations
        lines.extend([
            "",
            "=" * 80,
            "💡 RECOMMENDATIONS (FEE-AWARE)",
            "=" * 80,
            "",
        ])
        
        # Analyze patterns
        signal_data = self.summary_data.get("signal_pnl", {})
        real_data = self.summary_data.get("real_pnl", {})
        signal_wr = signal_data.get("win_rate", 0)
        real_wr = real_data.get("win_rate", 0)
        
        # Fee-aware recommendations
        lines.append(f"💸 Fee Impact: ~{(tp_analysis['breakeven_multiplier']-1)*100:.1f}% of capital per round trip")
        
        if tp_analysis['optimal_tp'] >= 2.0:
            lines.append(f"✅ Optimal TP ({tp_analysis['optimal_tp']}X) captures enough to offset fees")
        else:
            lines.append(f"⚠️ Low optimal TP - consider higher targets to reduce fee drag")
        
        if signal_wr > 50:
            lines.append("✅ Signal quality is good (>50% reach profit targets)")
        
        if signal_wr - real_wr > 20:
            lines.append("⚠️  Significant decay between peak and current price")
            lines.append("   → CRITICAL: Implement exit strategy, do not HODL")
        
        if best.strategy_name != "HODL (No Exit)":
            lines.append(f"✅ Active exit strategy outperforms HODL")
            lines.append(f"   → Use: {best.strategy_name}")
        
        rugged_count = self.summary_data.get("rugged_count", 0)
        total = self.summary_data.get("total_signals", len(self.tokens))
        if total > 0 and rugged_count / total > 0.1:
            lines.append(f"⚠️  High rug rate ({rugged_count}/{total} = {rugged_count/total*100:.0f}%)")
            lines.append("   → Consider tighter stop losses or faster exits")
        
        return "\n".join(lines)
    
    def get_optimal_settings(self) -> dict:
        """Return the optimal strategy settings for bot configuration."""
        strategies = self.run_all_strategies()
        best = strategies[0]
        
        # Extract settings from best strategy name
        settings = {
            "strategy": best.strategy_name,
            "roi": best.roi,
            "win_rate": best.win_rate,
            "recommended_settings": {}
        }
        
        # Parse strategy parameters
        if "Hybrid" in best.strategy_name:
            settings["recommended_settings"] = {
                "partial_take_profit_at": 2.0,
                "partial_take_profit_pct": 50,
                "trailing_stop_pct": 25,
                "max_target": 4.0,
            }
        elif "Fixed Exit" in best.strategy_name:
            mult = float(best.strategy_name.split()[-1].replace("X", ""))
            settings["recommended_settings"] = {
                "sell_at_multiplier": mult,
                "sell_percentage": 100,
            }
        elif "Tiered" in best.strategy_name:
            settings["recommended_settings"] = {
                "tier_1": {"multiplier": 1.5, "sell_pct": 50},
                "tier_2": {"multiplier": 2.5, "sell_pct": 50},
            }
        elif "Trailing" in best.strategy_name:
            pct = int(best.strategy_name.split("(")[1].split("%")[0])
            settings["recommended_settings"] = {
                "trailing_stop_pct": pct,
            }
        
        return settings


def load_compare_json(filepath: str) -> dict:
    """Load compare results JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def simulate_from_file(filepath: str, position_size: float = 0.1, capital: float = 10.0) -> str:
    """
    Run simulation from a compare results JSON file.
    
    Args:
        filepath: Path to compare_*.json file
        position_size: SOL per trade
        capital: Starting capital in SOL
    
    Returns:
        Strategy report as string
    """
    data = load_compare_json(filepath)
    simulator = StrategySimulator(data, position_size, capital)
    return simulator.generate_report()


def simulate_from_data(data: dict, position_size: float = 0.1, capital: float = 10.0) -> tuple[str, dict]:
    """
    Run simulation from compare results data.
    
    Returns:
        Tuple of (report string, optimal settings dict)
    """
    simulator = StrategySimulator(data, position_size, capital)
    report = simulator.generate_report()
    optimal = simulator.get_optimal_settings()
    return report, optimal


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python strategy_simulator.py <compare_results.json> [position_size] [capital]")
        sys.exit(1)
    
    filepath = sys.argv[1]
    pos_size = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
    capital = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    
    report = simulate_from_file(filepath, pos_size, capital)
    print(report)
