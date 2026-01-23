"""
Accurate Backtesting Simulator with Real Price History

This module fetches actual OHLCV candle data from GeckoTerminal
to perform accurate strategy backtesting with trailing stops.

Unlike the basic simulator that uses only peak/current multipliers,
this fetches full price history for each token to simulate:
- Exact trailing stop triggers
- Time-based exits at actual prices
- Multi-tier exits with precise timing
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Any
from enum import Enum

from src.price_history import (
    PriceHistory, 
    PriceHistoryFetcher, 
    get_price_fetcher,
    Candle,
    make_naive
)
from src.strategy_simulator import (
    TradingFees, 
    DEFAULT_FEES, 
    Trade, 
    ExitReason,
    StrategyResult
)

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    position_size: float = 0.1  # SOL per trade
    starting_capital: float = 10.0  # Total SOL
    max_hold_hours: int = 72  # Max hours to hold a position
    candle_timeframe: int = 15  # Minutes per candle
    fees: TradingFees = field(default_factory=lambda: DEFAULT_FEES)


@dataclass
class BacktestTrade:
    """A single backtest trade with full execution details."""
    symbol: str
    address: str
    entry_time: datetime
    entry_price: float  # Actual entry price in USD
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    exit_multiplier: Optional[float] = None
    peak_price: float = 0.0
    peak_multiplier: float = 0.0
    position_size: float = 0.1
    fees: TradingFees = field(default_factory=lambda: DEFAULT_FEES)
    
    # Execution details
    candles_held: int = 0
    triggered_at_candle: Optional[int] = None
    
    @property
    def pnl_multiplier(self) -> float:
        """Net return multiplier after fees."""
        if self.exit_multiplier is None:
            return 0.0
        
        # Calculate effective position after buy fees
        effective_entry, _ = self.fees.calculate_buy_cost(self.position_size)
        
        # Calculate gross exit value
        gross_exit = effective_entry * self.exit_multiplier
        
        # Calculate net after sell fees
        net_exit, _ = self.fees.calculate_sell_proceeds(gross_exit)
        
        return net_exit / self.position_size
    
    @property
    def pnl_sol(self) -> float:
        """Net PnL in SOL."""
        return self.position_size * (self.pnl_multiplier - 1)
    
    @property
    def total_fees_sol(self) -> float:
        """Total fees paid."""
        effective_entry, buy_fees = self.fees.calculate_buy_cost(self.position_size)
        if self.exit_multiplier is None:
            return buy_fees
        gross_exit = effective_entry * self.exit_multiplier
        _, sell_fees = self.fees.calculate_sell_proceeds(gross_exit)
        return buy_fees + sell_fees


@dataclass
class BacktestResult:
    """Results from backtesting a strategy."""
    strategy_name: str
    trades: list[BacktestTrade] = field(default_factory=list)
    total_capital: float = 10.0
    position_size: float = 0.1
    config: BacktestConfig = field(default_factory=BacktestConfig)
    
    # Metadata
    tokens_with_data: int = 0
    tokens_without_data: int = 0
    data_coverage_pct: float = 0.0
    
    @property
    def total_trades(self) -> int:
        return len(self.trades)
    
    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_multiplier > 1)
    
    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t.pnl_multiplier <= 1)
    
    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return (self.winning_trades / len(self.trades)) * 100
    
    @property
    def total_pnl_sol(self) -> float:
        return sum(t.pnl_sol for t in self.trades)
    
    @property
    def total_fees_sol(self) -> float:
        return sum(t.total_fees_sol for t in self.trades)
    
    @property
    def roi(self) -> float:
        """Return on investment as percentage."""
        if self.total_capital == 0:
            return 0.0
        return (self.total_pnl_sol / self.total_capital) * 100
    
    @property
    def avg_multiplier(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.pnl_multiplier for t in self.trades) / len(self.trades)
    
    @property
    def avg_hold_time_hours(self) -> float:
        if not self.trades:
            return 0.0
        
        hold_times = []
        for t in self.trades:
            if t.exit_time and t.entry_time:
                delta = t.exit_time - t.entry_time
                hold_times.append(delta.total_seconds() / 3600)
        
        return sum(hold_times) / len(hold_times) if hold_times else 0.0
    
    def summary(self) -> dict:
        """Return summary dict for reporting."""
        return {
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 1),
            "total_pnl_sol": round(self.total_pnl_sol, 4),
            "total_fees_sol": round(self.total_fees_sol, 4),
            "roi": round(self.roi, 1),
            "avg_multiplier": round(self.avg_multiplier, 3),
            "avg_hold_hours": round(self.avg_hold_time_hours, 1),
            "data_coverage": round(self.data_coverage_pct, 1),
            "tokens_with_data": self.tokens_with_data,
            "tokens_without_data": self.tokens_without_data,
        }


class AccurateBacktester:
    """
    Accurate backtester using real OHLCV price history.
    
    This fetches candle data from GeckoTerminal and simulates
    strategies tick-by-tick for accurate trailing stop execution.
    """
    
    def __init__(
        self,
        signals: list[dict],
        config: Optional[BacktestConfig] = None,
        price_histories: Optional[dict[str, PriceHistory]] = None
    ):
        """
        Initialize backtester.
        
        Args:
            signals: List of signal dicts with token info
            config: Backtest configuration
            price_histories: Pre-fetched price histories (optional)
        """
        self.signals = signals
        self.config = config or BacktestConfig()
        self.price_histories = price_histories or {}
        self._fetcher: Optional[PriceHistoryFetcher] = None
    
    async def fetch_price_data(self, progress_callback=None) -> int:
        """
        Fetch price history for all tokens.
        
        Returns: Number of tokens with data
        """
        if not self._fetcher:
            self._fetcher = get_price_fetcher()
        
        addresses = [s.get("address") for s in self.signals if s.get("address")]
        total = len(addresses)
        
        async def update_progress(current: int, total: int):
            if progress_callback:
                await progress_callback(current, total)
        
        self.price_histories = await self._fetcher.fetch_multiple(
            addresses,
            timeframe_minutes=self.config.candle_timeframe,
            limit=1000,  # ~10 days of 15min candles
            progress_callback=update_progress
        )
        
        return len(self.price_histories)
    
    def _get_entry_price(self, history: PriceHistory, entry_time: datetime) -> Optional[float]:
        """Get the price at entry time."""
        return history.get_price_at(entry_time)
    
    async def backtest_trailing_stop(
        self,
        trailing_pct: float = 0.20,
        name: Optional[str] = None
    ) -> BacktestResult:
        """
        Backtest trailing stop strategy with real price data.
        
        Args:
            trailing_pct: Trailing stop percentage (0.20 = 20%)
            name: Strategy name for results
        """
        result = BacktestResult(
            strategy_name=name or f"Trailing Stop ({int(trailing_pct*100)}%)",
            total_capital=self.config.starting_capital,
            position_size=self.config.position_size,
            config=self.config,
        )
        
        tokens_with_data = 0
        tokens_without_data = 0
        
        for signal in self.signals:
            address = signal.get("address", "")
            symbol = signal.get("symbol", "UNKNOWN")
            
            # Parse entry time (convert to naive for comparison)
            try:
                entry_time = make_naive(datetime.fromisoformat(
                    signal.get("signal_timestamp", "").replace("Z", "+00:00")
                ))
            except:
                entry_time = datetime.now() - timedelta(days=7)
            
            # Check if we have price data
            history = self.price_histories.get(address)
            
            if not history or not history.candles:
                tokens_without_data += 1
                
                # Fallback to estimate using signal data
                trade = self._estimate_trade_without_history(signal, trailing_pct)
                if trade:
                    result.trades.append(trade)
                continue
            
            tokens_with_data += 1
            
            # Get entry price
            entry_price = self._get_entry_price(history, entry_time)
            if not entry_price:
                # Use first candle price
                entry_price = history.candles[0].close if history.candles else 1.0
            
            # Simulate trailing stop
            exit_mult, exit_reason, exit_time = history.simulate_trailing_stop(
                entry_time=entry_time,
                entry_price=entry_price,
                trailing_pct=trailing_pct,
                max_hold_hours=self.config.max_hold_hours
            )
            
            # Calculate peak multiplier safely
            high_after = history.get_high_after(entry_time)
            peak_mult = (high_after / entry_price) if (high_after and entry_price) else 1.0
            
            # Create trade
            trade = BacktestTrade(
                symbol=symbol,
                address=address,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=entry_price * exit_mult if exit_mult else None,
                exit_reason=self._map_exit_reason(exit_reason),
                exit_multiplier=exit_mult,
                peak_multiplier=peak_mult,
                position_size=self.config.position_size,
                fees=self.config.fees,
            )
            
            result.trades.append(trade)
        
        result.tokens_with_data = tokens_with_data
        result.tokens_without_data = tokens_without_data
        result.data_coverage_pct = (tokens_with_data / len(self.signals) * 100) if self.signals else 0
        
        return result
    
    async def backtest_fixed_exit(
        self,
        target_mult: float = 2.0,
        stop_loss_mult: float = 0.5,
        name: Optional[str] = None
    ) -> BacktestResult:
        """
        Backtest fixed take profit / stop loss strategy.
        """
        result = BacktestResult(
            strategy_name=name or f"Fixed Exit {target_mult}X",
            total_capital=self.config.starting_capital,
            position_size=self.config.position_size,
            config=self.config,
        )
        
        tokens_with_data = 0
        tokens_without_data = 0
        
        for signal in self.signals:
            address = signal.get("address", "")
            symbol = signal.get("symbol", "UNKNOWN")
            
            try:
                entry_time = make_naive(datetime.fromisoformat(
                    signal.get("signal_timestamp", "").replace("Z", "+00:00")
                ))
            except:
                entry_time = datetime.now() - timedelta(days=7)
            
            history = self.price_histories.get(address)
            
            if not history or not history.candles:
                tokens_without_data += 1
                # Use signal data to estimate
                trade = self._estimate_fixed_exit_trade(signal, target_mult)
                if trade:
                    result.trades.append(trade)
                continue
            
            tokens_with_data += 1
            
            entry_price = self._get_entry_price(history, entry_time)
            if not entry_price:
                entry_price = history.candles[0].close if history.candles else 1.0
            
            exit_mult, exit_reason, exit_time = history.simulate_fixed_exit(
                entry_time=entry_time,
                entry_price=entry_price,
                target_mult=target_mult,
                stop_loss_mult=stop_loss_mult,
                max_hold_hours=self.config.max_hold_hours
            )
            
            trade = BacktestTrade(
                symbol=symbol,
                address=address,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=entry_price * exit_mult if exit_mult else None,
                exit_reason=self._map_exit_reason(exit_reason),
                exit_multiplier=exit_mult,
                position_size=self.config.position_size,
                fees=self.config.fees,
            )
            
            result.trades.append(trade)
        
        result.tokens_with_data = tokens_with_data
        result.tokens_without_data = tokens_without_data
        result.data_coverage_pct = (tokens_with_data / len(self.signals) * 100) if self.signals else 0
        
        return result
    
    async def backtest_tiered_exit(
        self,
        tiers: list[tuple[float, float]],
        trailing_pct: float = 0.25,
        name: Optional[str] = None
    ) -> BacktestResult:
        """
        Backtest tiered exit with trailing on remainder.
        
        Args:
            tiers: [(multiplier, sell_pct), ...] e.g. [(2.0, 0.5), (3.0, 0.5)]
            trailing_pct: Trailing stop on remaining after tiers
        """
        tier_desc = "+".join([f"{m}X({int(p*100)}%)" for m, p in tiers])
        result = BacktestResult(
            strategy_name=name or f"Tiered {tier_desc}",
            total_capital=self.config.starting_capital,
            position_size=self.config.position_size,
            config=self.config,
        )
        
        tokens_with_data = 0
        tokens_without_data = 0
        
        for signal in self.signals:
            address = signal.get("address", "")
            symbol = signal.get("symbol", "UNKNOWN")
            
            try:
                entry_time = make_naive(datetime.fromisoformat(
                    signal.get("signal_timestamp", "").replace("Z", "+00:00")
                ))
            except:
                entry_time = datetime.now() - timedelta(days=7)
            
            history = self.price_histories.get(address)
            
            if not history or not history.candles:
                tokens_without_data += 1
                trade = self._estimate_tiered_trade(signal, tiers)
                if trade:
                    result.trades.append(trade)
                continue
            
            tokens_with_data += 1
            
            entry_price = self._get_entry_price(history, entry_time)
            if not entry_price:
                entry_price = history.candles[0].close if history.candles else 1.0
            
            weighted_mult, exit_reason, exits = history.simulate_tiered_exit(
                entry_time=entry_time,
                entry_price=entry_price,
                tiers=tiers,
                trailing_pct=trailing_pct,
                max_hold_hours=self.config.max_hold_hours
            )
            
            # Use last exit time
            exit_time = exits[-1][2] if exits else None
            
            trade = BacktestTrade(
                symbol=symbol,
                address=address,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=entry_price * weighted_mult if weighted_mult else None,
                exit_reason=self._map_exit_reason(exit_reason),
                exit_multiplier=weighted_mult,
                position_size=self.config.position_size,
                fees=self.config.fees,
            )
            
            result.trades.append(trade)
        
        result.tokens_with_data = tokens_with_data
        result.tokens_without_data = tokens_without_data
        result.data_coverage_pct = (tokens_with_data / len(self.signals) * 100) if self.signals else 0
        
        return result
    
    def _map_exit_reason(self, reason: str) -> ExitReason:
        """Map string reason to ExitReason enum."""
        mapping = {
            "trailing_stop": ExitReason.TRAILING_STOP,
            "target_hit": ExitReason.TARGET_HIT,
            "stop_loss": ExitReason.STOP_LOSS,
            "time_exit": ExitReason.TIME_EXIT,
            "still_open": ExitReason.STILL_OPEN,
        }
        return mapping.get(reason, ExitReason.STILL_OPEN)
    
    def _estimate_trade_without_history(
        self, 
        signal: dict, 
        trailing_pct: float
    ) -> Optional[BacktestTrade]:
        """
        Estimate trade result when we don't have price history.
        Uses signal peak and current price as approximation.
        """
        address = signal.get("address", "")
        symbol = signal.get("symbol", "UNKNOWN")
        
        try:
            entry_time = make_naive(datetime.fromisoformat(
                signal.get("signal_timestamp", "").replace("Z", "+00:00")
            ))
        except:
            entry_time = datetime.now() - timedelta(days=7)
        
        signal_data = signal.get("signal", {})
        real_data = signal.get("real", {})
        
        peak_mult = signal_data.get("multiplier") or 1.0
        current_mult = real_data.get("multiplier") or 0.5
        is_rugged = real_data.get("is_rugged", False)
        
        if is_rugged:
            exit_mult = 0.0
            exit_reason = ExitReason.RUGGED
        elif peak_mult > 1.0:
            # Estimate: trailing stop would capture (1 - trailing_pct) of peak
            exit_mult = peak_mult * (1 - trailing_pct)
            exit_reason = ExitReason.TRAILING_STOP
        else:
            exit_mult = current_mult
            exit_reason = ExitReason.STILL_OPEN
        
        return BacktestTrade(
            symbol=symbol,
            address=address,
            entry_time=entry_time,
            entry_price=1.0,  # Normalized
            exit_price=exit_mult,
            exit_reason=exit_reason,
            exit_multiplier=exit_mult,
            peak_multiplier=peak_mult,
            position_size=self.config.position_size,
            fees=self.config.fees,
        )
    
    def _estimate_fixed_exit_trade(
        self,
        signal: dict,
        target_mult: float
    ) -> Optional[BacktestTrade]:
        """Estimate fixed exit trade without price history."""
        address = signal.get("address", "")
        symbol = signal.get("symbol", "UNKNOWN")
        
        try:
            entry_time = make_naive(datetime.fromisoformat(
                signal.get("signal_timestamp", "").replace("Z", "+00:00")
            ))
        except:
            entry_time = datetime.now() - timedelta(days=7)
        
        signal_data = signal.get("signal", {})
        real_data = signal.get("real", {})
        
        peak_mult = signal_data.get("multiplier") or 1.0
        current_mult = real_data.get("multiplier") or 0.5
        is_rugged = real_data.get("is_rugged", False)
        
        if is_rugged:
            exit_mult = 0.0
            exit_reason = ExitReason.RUGGED
        elif peak_mult >= target_mult:
            exit_mult = target_mult
            exit_reason = ExitReason.TARGET_HIT
        else:
            exit_mult = current_mult
            exit_reason = ExitReason.STILL_OPEN
        
        return BacktestTrade(
            symbol=symbol,
            address=address,
            entry_time=entry_time,
            entry_price=1.0,
            exit_price=exit_mult,
            exit_reason=exit_reason,
            exit_multiplier=exit_mult,
            peak_multiplier=peak_mult,
            position_size=self.config.position_size,
            fees=self.config.fees,
        )
    
    def _estimate_tiered_trade(
        self,
        signal: dict,
        tiers: list[tuple[float, float]]
    ) -> Optional[BacktestTrade]:
        """Estimate tiered exit trade without price history."""
        address = signal.get("address", "")
        symbol = signal.get("symbol", "UNKNOWN")
        
        try:
            entry_time = make_naive(datetime.fromisoformat(
                signal.get("signal_timestamp", "").replace("Z", "+00:00")
            ))
        except:
            entry_time = datetime.now() - timedelta(days=7)
        
        signal_data = signal.get("signal", {})
        real_data = signal.get("real", {})
        
        peak_mult = signal_data.get("multiplier") or 1.0
        current_mult = real_data.get("multiplier") or 0.5
        is_rugged = real_data.get("is_rugged", False)
        
        if is_rugged:
            return BacktestTrade(
                symbol=symbol,
                address=address,
                entry_time=entry_time,
                entry_price=1.0,
                exit_price=0.0,
                exit_reason=ExitReason.RUGGED,
                exit_multiplier=0.0,
                peak_multiplier=peak_mult,
                position_size=self.config.position_size,
                fees=self.config.fees,
            )
        
        # Calculate weighted exit
        remaining = 1.0
        weighted_mult = 0.0
        
        for tier_mult, tier_pct in sorted(tiers, key=lambda x: x[0]):
            if peak_mult >= tier_mult:
                sell_pct = min(tier_pct, remaining)
                weighted_mult += tier_mult * sell_pct
                remaining -= sell_pct
        
        # Remaining exits at current price
        if remaining > 0:
            weighted_mult += current_mult * remaining
        
        return BacktestTrade(
            symbol=symbol,
            address=address,
            entry_time=entry_time,
            entry_price=1.0,
            exit_price=weighted_mult,
            exit_reason=ExitReason.TARGET_HIT if weighted_mult > 1 else ExitReason.STILL_OPEN,
            exit_multiplier=weighted_mult,
            peak_multiplier=peak_mult,
            position_size=self.config.position_size,
            fees=self.config.fees,
        )
    
    async def run_all_strategies(self, progress_callback=None) -> list[BacktestResult]:
        """
        Run all strategies and return sorted by ROI.
        
        This fetches price data first, then runs each strategy.
        """
        # Fetch price data
        if progress_callback:
            await progress_callback("Fetching price history from GeckoTerminal...")
        
        await self.fetch_price_data()
        
        if progress_callback:
            await progress_callback(f"Running backtests on {len(self.price_histories)} tokens with data...")
        
        # Run strategies
        results = []
        
        # Trailing stop variations
        for pct in [0.15, 0.20, 0.25, 0.30]:
            result = await self.backtest_trailing_stop(pct)
            results.append(result)
        
        # Fixed exit variations
        for mult in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
            result = await self.backtest_fixed_exit(mult)
            results.append(result)
        
        # Tiered exits
        tiered_configs = [
            [(1.5, 0.5), (2.5, 0.5)],
            [(2.0, 0.5), (3.0, 0.5)],
            [(2.0, 0.33), (3.0, 0.33), (5.0, 0.34)],
        ]
        for tiers in tiered_configs:
            result = await self.backtest_tiered_exit(tiers)
            results.append(result)
        
        # Sort by ROI
        results.sort(key=lambda r: r.roi, reverse=True)
        
        return results
    
    def generate_report(self, results: list[BacktestResult]) -> str:
        """Generate a comprehensive backtest report."""
        lines = [
            "=" * 80,
            "🎯 ACCURATE BACKTEST REPORT (Real Price History)",
            "=" * 80,
            "",
            f"📊 Total Signals: {len(self.signals)}",
            f"📈 Tokens with Price Data: {results[0].tokens_with_data if results else 0}",
            f"📉 Tokens without Data: {results[0].tokens_without_data if results else 0}",
            f"📊 Data Coverage: {results[0].data_coverage_pct if results else 0:.1f}%",
            "",
            f"💰 Starting Capital: {self.config.starting_capital} SOL",
            f"📦 Position Size: {self.config.position_size} SOL",
            f"⏱️ Max Hold Time: {self.config.max_hold_hours}h",
            "",
            "=" * 80,
            "💸 FEE STRUCTURE (GMGN.ai)",
            "=" * 80,
            f"  Buy Fee:  {self.config.fees.total_buy_fee_pct:.1f}%",
            f"  Sell Fee: {self.config.fees.total_sell_fee_pct:.1f}%",
            f"  Breakeven: {self.config.fees.calculate_round_trip_breakeven():.3f}X",
            "",
            "=" * 80,
            "📈 STRATEGY RANKINGS (by ROI, after fees)",
            "=" * 80,
            "",
        ]
        
        for i, result in enumerate(results, 1):
            s = result.summary()
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
            
            lines.append(f"{emoji} #{i}: {s['strategy']}")
            lines.append(f"   Win Rate: {s['win_rate']}% | Trades: {s['total_trades']}")
            lines.append(f"   Net PnL: {s['total_pnl_sol']:+.4f} SOL (ROI: {s['roi']:+.1f}%)")
            lines.append(f"   Fees Paid: {s['total_fees_sol']:.4f} SOL")
            lines.append(f"   Avg Mult: {s['avg_multiplier']:.3f}X | Avg Hold: {s['avg_hold_hours']:.1f}h")
            lines.append("")
        
        # Best strategy details
        if results:
            best = results[0]
            lines.extend([
                "=" * 80,
                "🏆 BEST STRATEGY ANALYSIS",
                "=" * 80,
                "",
                f"Strategy: {best.strategy_name}",
                f"ROI: {best.roi:.1f}%",
                f"Win Rate: {best.win_rate:.1f}%",
                "",
                "Exit Reason Breakdown:",
            ])
            
            exit_counts: dict[str, int] = {}
            for trade in best.trades:
                reason = trade.exit_reason.value if trade.exit_reason else "unknown"
                exit_counts[reason] = exit_counts.get(reason, 0) + 1
            
            for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
                lines.append(f"  • {reason}: {count} trades")
        
        lines.extend([
            "",
            "=" * 80,
            "⚠️ NOTE: Tokens without GeckoTerminal data use estimated exits",
            "   based on profit alert peaks. Results may vary for those tokens.",
            "=" * 80,
        ])
        
        return "\n".join(lines)


async def run_accurate_backtest(
    signals: list[dict],
    position_size: float = 0.1,
    capital: float = 10.0,
    progress_callback=None
) -> tuple[str, list[BacktestResult]]:
    """
    Run accurate backtest with real price data.
    
    Args:
        signals: List of signal dicts
        position_size: SOL per trade
        capital: Starting capital
        progress_callback: Async callback for progress updates
        
    Returns:
        (report_string, results_list)
    """
    config = BacktestConfig(
        position_size=position_size,
        starting_capital=capital,
    )
    
    backtester = AccurateBacktester(signals, config)
    results = await backtester.run_all_strategies(progress_callback)
    report = backtester.generate_report(results)
    
    return report, results
