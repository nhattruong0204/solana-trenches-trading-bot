"""
Tests for the strategy_simulator module.

Tests TradingFees, Trade, StrategyResult, and StrategySimulator classes.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.strategy_simulator import (
    TradingFees,
    DEFAULT_FEES,
    ExitReason,
    Trade,
    StrategyResult,
    StrategySimulator,
)


class TestTradingFees:
    """Tests for TradingFees dataclass."""
    
    def test_default_fees(self):
        """Test default fee values."""
        fees = TradingFees()
        
        assert fees.buy_fee_pct == 1.0
        assert fees.sell_fee_pct == 1.0
        assert fees.priority_fee_pct == 0.5
        assert fees.slippage_pct == 1.0
        assert fees.network_fee_sol == 0.00025
    
    def test_custom_fees(self):
        """Test custom fee configuration."""
        fees = TradingFees(
            buy_fee_pct=2.0,
            sell_fee_pct=2.0,
            priority_fee_pct=1.0,
            slippage_pct=2.0,
        )
        
        assert fees.buy_fee_pct == 2.0
        assert fees.total_buy_fee_pct == 5.0  # 2 + 1 + 2
    
    def test_total_buy_fee_pct(self):
        """Test total buy fee percentage calculation."""
        fees = TradingFees()
        
        # buy_fee + priority + slippage = 1 + 0.5 + 1 = 2.5%
        assert fees.total_buy_fee_pct == 2.5
    
    def test_total_sell_fee_pct(self):
        """Test total sell fee percentage calculation."""
        fees = TradingFees()
        
        # sell_fee + priority + slippage = 1 + 0.5 + 1 = 2.5%
        assert fees.total_sell_fee_pct == 2.5
    
    def test_calculate_buy_cost(self):
        """Test buy cost calculation."""
        fees = TradingFees()
        position = 1.0  # 1 SOL
        
        effective, fee_amount = fees.calculate_buy_cost(position)
        
        # 2.5% fee + network fee
        expected_pct_fee = 1.0 * (2.5 / 100)  # 0.025 SOL
        expected_total_fee = expected_pct_fee + 0.00025
        
        assert abs(fee_amount - expected_total_fee) < 0.001
        assert abs(effective - (1.0 - expected_total_fee)) < 0.001
    
    def test_calculate_buy_cost_small_position(self):
        """Test buy cost with small position."""
        fees = TradingFees()
        position = 0.1
        
        effective, fee_amount = fees.calculate_buy_cost(position)
        
        assert effective > 0
        assert effective < position
        assert fee_amount > 0
    
    def test_calculate_sell_proceeds(self):
        """Test sell proceeds calculation."""
        fees = TradingFees()
        gross = 2.0  # 2 SOL gross
        
        net, fee_amount = fees.calculate_sell_proceeds(gross)
        
        assert net < gross
        assert fee_amount > 0
    
    def test_calculate_sell_proceeds_zero(self):
        """Test sell proceeds with zero value."""
        fees = TradingFees()
        
        net, fee_amount = fees.calculate_sell_proceeds(0)
        
        assert net == 0
    
    def test_calculate_round_trip_breakeven(self):
        """Test breakeven multiplier calculation."""
        fees = TradingFees()
        
        breakeven = fees.calculate_round_trip_breakeven()
        
        # Should be around 1.05 for default fees
        assert 1.0 < breakeven < 1.1
    
    def test_summary(self):
        """Test fee summary string."""
        fees = TradingFees()
        
        summary = fees.summary()
        
        assert "Buy Fee" in summary
        assert "Sell Fee" in summary
        assert "Breakeven" in summary
        assert "%" in summary


class TestExitReason:
    """Tests for ExitReason enum."""
    
    def test_all_exit_reasons(self):
        """Test all exit reasons exist."""
        assert ExitReason.TARGET_HIT.value == "target_hit"
        assert ExitReason.STOP_LOSS.value == "stop_loss"
        assert ExitReason.TIME_EXIT.value == "time_exit"
        assert ExitReason.TRAILING_STOP.value == "trailing_stop"
        assert ExitReason.RUGGED.value == "rugged"
        assert ExitReason.STILL_OPEN.value == "still_open"
    
    def test_exit_reason_iteration(self):
        """Test iterating over exit reasons."""
        reasons = list(ExitReason)
        assert len(reasons) == 6


class TestTrade:
    """Tests for Trade dataclass."""
    
    @pytest.fixture
    def sample_trade(self):
        """Create a sample trade."""
        return Trade(
            symbol="TEST",
            address="addr123456789012345678901234567890",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=2.0,
            exit_reason=ExitReason.TARGET_HIT,
            position_size=1.0,
            peak_multiplier=2.5,
        )
    
    def test_create_trade(self, sample_trade):
        """Test creating a trade."""
        assert sample_trade.symbol == "TEST"
        assert sample_trade.entry_price_mult == 1.0
        assert sample_trade.exit_price_mult == 2.0
    
    def test_effective_entry_sol(self, sample_trade):
        """Test effective entry after buy fees."""
        effective = sample_trade.effective_entry_sol
        
        # Should be less than position size due to fees
        assert effective < 1.0
        assert effective > 0.9  # But not much less
    
    def test_buy_fees_sol(self, sample_trade):
        """Test buy fees calculation."""
        fees = sample_trade.buy_fees_sol
        
        assert fees > 0
        assert fees < 0.1  # Should be small percentage
    
    def test_gross_exit_value(self, sample_trade):
        """Test gross exit value before sell fees."""
        gross = sample_trade.gross_exit_value
        
        # 2x on effective entry
        effective = sample_trade.effective_entry_sol
        expected = effective * 2.0
        
        assert abs(gross - expected) < 0.01
    
    def test_gross_exit_value_no_exit(self):
        """Test gross exit when no exit price."""
        trade = Trade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
        )
        
        assert trade.gross_exit_value == 0.0
    
    def test_net_exit_value(self, sample_trade):
        """Test net exit value after sell fees."""
        net = sample_trade.net_exit_value
        gross = sample_trade.gross_exit_value
        
        assert net < gross
        assert net > 0
    
    def test_sell_fees_sol(self, sample_trade):
        """Test sell fees calculation."""
        sell_fees = sample_trade.sell_fees_sol
        
        assert sell_fees > 0
    
    def test_sell_fees_no_exit(self):
        """Test sell fees when no exit."""
        trade = Trade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
        )
        
        assert trade.sell_fees_sol == 0.0
    
    def test_total_fees_sol(self, sample_trade):
        """Test total fees (buy + sell)."""
        total = sample_trade.total_fees_sol
        buy = sample_trade.buy_fees_sol
        sell = sample_trade.sell_fees_sol
        
        assert total == buy + sell
    
    def test_pnl_multiplier_winning(self, sample_trade):
        """Test PnL multiplier for winning trade."""
        pnl_mult = sample_trade.pnl_multiplier
        
        # 2x exit should be profitable even after fees
        assert pnl_mult > 1.0
        assert pnl_mult < 2.0  # Less than 2x due to fees
    
    def test_pnl_multiplier_no_exit(self):
        """Test PnL multiplier when no exit."""
        trade = Trade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
        )
        
        assert trade.pnl_multiplier == 0.0
    
    def test_pnl_percent(self, sample_trade):
        """Test PnL as percentage."""
        pnl_pct = sample_trade.pnl_percent
        
        # 2x = ~100% profit before fees, less after
        assert pnl_pct > 50  # Still profitable
        assert pnl_pct < 100  # But less than 100% due to fees
    
    def test_pnl_sol(self, sample_trade):
        """Test PnL in SOL."""
        pnl = sample_trade.pnl_sol
        
        # Net exit - position
        expected = sample_trade.net_exit_value - 1.0
        
        assert abs(pnl - expected) < 0.01
    
    def test_is_winner_true(self, sample_trade):
        """Test is_winner for profitable trade."""
        assert sample_trade.is_winner is True
    
    def test_is_winner_false(self):
        """Test is_winner for losing trade."""
        trade = Trade(
            symbol="LOSE",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=0.5,
            position_size=1.0,
        )
        
        assert trade.is_winner is False


class TestStrategyResult:
    """Tests for StrategyResult dataclass."""
    
    @pytest.fixture
    def winning_trade(self):
        return Trade(
            symbol="WIN",
            address="addr1",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=2.0,
            position_size=0.1,
        )
    
    @pytest.fixture
    def losing_trade(self):
        return Trade(
            symbol="LOSE",
            address="addr2",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=0.5,
            position_size=0.1,
        )
    
    def test_empty_result(self):
        """Test empty result."""
        result = StrategyResult(strategy_name="Empty")
        
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.total_pnl_sol == 0.0
    
    def test_total_trades(self, winning_trade, losing_trade):
        """Test total trades count."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade, winning_trade],
        )
        
        assert result.total_trades == 3
    
    def test_winners_and_losers(self, winning_trade, losing_trade):
        """Test winner/loser count."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, winning_trade, losing_trade],
        )
        
        assert result.winners == 2
        assert result.losers == 1
    
    def test_win_rate(self, winning_trade, losing_trade):
        """Test win rate calculation."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        # 50% win rate (1 win, 1 loss)
        assert result.win_rate == 50.0
    
    def test_total_pnl_sol(self, winning_trade, losing_trade):
        """Test total PnL in SOL."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        expected = winning_trade.pnl_sol + losing_trade.pnl_sol
        assert abs(result.total_pnl_sol - expected) < 0.001
    
    def test_total_fees_sol(self, winning_trade, losing_trade):
        """Test total fees across trades."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        expected = winning_trade.total_fees_sol + losing_trade.total_fees_sol
        assert abs(result.total_fees_sol - expected) < 0.001
    
    def test_total_pnl_percent(self, winning_trade):
        """Test total PnL as percentage of capital."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade],
            total_capital=1.0,
        )
        
        expected = (winning_trade.pnl_sol / 1.0) * 100
        assert abs(result.total_pnl_percent - expected) < 0.1
    
    def test_total_pnl_percent_zero_capital(self):
        """Test PnL percent with zero capital."""
        result = StrategyResult(
            strategy_name="Test",
            total_capital=0,
        )
        
        assert result.total_pnl_percent == 0.0
    
    def test_avg_multiplier(self, winning_trade, losing_trade):
        """Test average multiplier."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        expected = (winning_trade.pnl_multiplier + losing_trade.pnl_multiplier) / 2
        assert abs(result.avg_multiplier - expected) < 0.01
    
    def test_max_drawdown_no_trades(self):
        """Test max drawdown with no trades."""
        result = StrategyResult(strategy_name="Empty")
        
        assert result.max_drawdown == 0.0
    
    def test_max_drawdown_with_trades(self, winning_trade, losing_trade):
        """Test max drawdown calculation."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade, losing_trade],
            total_capital=1.0,
        )
        
        # Should have some drawdown
        assert result.max_drawdown >= 0
    
    def test_profit_factor(self, winning_trade, losing_trade):
        """Test profit factor calculation."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        # profit / loss
        assert result.profit_factor > 0
    
    def test_profit_factor_no_losses(self, winning_trade):
        """Test profit factor with no losses."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade, winning_trade],
        )
        
        # Should be infinity if all wins
        assert result.profit_factor == float('inf')
    
    def test_profit_factor_no_profits(self, losing_trade):
        """Test profit factor with no profits."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[losing_trade, losing_trade],
        )
        
        assert result.profit_factor == 0.0
    
    def test_roi(self, winning_trade):
        """Test ROI calculation."""
        result = StrategyResult(
            strategy_name="Test",
            trades=[winning_trade],
            total_capital=1.0,
        )
        
        assert result.roi == result.total_pnl_percent
    
    def test_summary(self, winning_trade, losing_trade):
        """Test summary dict generation."""
        result = StrategyResult(
            strategy_name="Test Strategy",
            trades=[winning_trade, losing_trade],
        )
        
        summary = result.summary()
        
        assert summary["strategy"] == "Test Strategy"
        assert "total_trades" in summary
        assert "win_rate" in summary
        assert "total_pnl_sol" in summary
        assert "total_fees_sol" in summary


class TestStrategySimulator:
    """Tests for StrategySimulator class."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for simulator."""
        return {
            "tokens": [
                {
                    "symbol": "TEST1",
                    "address": "addr1",
                    "signal_timestamp": "2024-01-01T12:00:00Z",
                    "peak_multiplier": 3.0,
                    "current_multiplier": 0.5,
                    "has_profit_alert": True,
                },
                {
                    "symbol": "TEST2",
                    "address": "addr2",
                    "signal_timestamp": "2024-01-02T12:00:00Z",
                    "peak_multiplier": 5.0,
                    "current_multiplier": 2.0,
                    "has_profit_alert": True,
                },
                {
                    "symbol": "RUG",
                    "address": "addr3",
                    "signal_timestamp": "2024-01-03T12:00:00Z",
                    "peak_multiplier": 1.0,
                    "current_multiplier": 0.1,
                    "has_profit_alert": False,
                },
            ]
        }
    
    def test_create_simulator(self, sample_data):
        """Test creating a simulator."""
        sim = StrategySimulator(sample_data)
        
        assert len(sim.tokens) == 3
        assert sim.position_size == 0.1
        assert sim.starting_capital == 10.0
    
    def test_custom_parameters(self, sample_data):
        """Test custom simulator parameters."""
        sim = StrategySimulator(
            sample_data,
            position_size=0.5,
            starting_capital=50.0,
        )
        
        assert sim.position_size == 0.5
        assert sim.starting_capital == 50.0
    
    def test_custom_fees(self, sample_data):
        """Test simulator with custom fees."""
        custom_fees = TradingFees(buy_fee_pct=2.0, sell_fee_pct=2.0)
        sim = StrategySimulator(sample_data, fees=custom_fees)
        
        assert sim.fees.buy_fee_pct == 2.0
    
    def test_empty_data(self):
        """Test simulator with empty data."""
        sim = StrategySimulator({})
        
        assert len(sim.tokens) == 0


class TestTradeEdgeCases:
    """Test edge cases for Trade class."""
    
    def test_trade_breakeven_multiplier(self):
        """Test trade at exact breakeven multiplier."""
        fees = TradingFees()
        breakeven = fees.calculate_round_trip_breakeven()
        
        trade = Trade(
            symbol="BE",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=breakeven,
            position_size=1.0,
        )
        
        # Should be approximately 0 PnL
        assert abs(trade.pnl_sol) < 0.01
    
    def test_trade_100x(self):
        """Test trade with 100x multiplier."""
        trade = Trade(
            symbol="MOON",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=100.0,
            position_size=0.1,
        )
        
        assert trade.pnl_multiplier > 90
        assert trade.pnl_sol > 0
    
    def test_trade_rug(self):
        """Test trade that gets rugged (near 0)."""
        trade = Trade(
            symbol="RUG",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=0.001,
            position_size=0.1,
            exit_reason=ExitReason.RUGGED,
        )
        
        assert trade.pnl_multiplier < 0.01
        assert trade.pnl_sol < 0
        assert trade.exit_reason == ExitReason.RUGGED


class TestStrategyResultEdgeCases:
    """Test edge cases for StrategyResult."""
    
    def test_all_open_trades(self):
        """Test result with all open trades (no exits)."""
        trades = [
            Trade(
                symbol=f"OPEN{i}",
                address=f"addr{i}",
                entry_time=datetime.now(timezone.utc),
                # No exit
            ) for i in range(5)
        ]
        
        result = StrategyResult(strategy_name="Open", trades=trades)
        
        assert result.total_trades == 5
        assert result.winners == 0
        assert result.losers == 0  # Not counted as losses
        assert result.win_rate == 0.0
    
    def test_mixed_open_and_closed(self):
        """Test result with mix of open and closed trades."""
        closed = Trade(
            symbol="CLOSED",
            address="addr1",
            entry_time=datetime.now(timezone.utc),
            exit_price_mult=2.0,
        )
        open_trade = Trade(
            symbol="OPEN",
            address="addr2",
            entry_time=datetime.now(timezone.utc),
        )
        
        result = StrategyResult(
            strategy_name="Mixed",
            trades=[closed, open_trade],
        )
        
        # Win rate only considers closed trades
        assert result.win_rate == 100.0  # 1 closed winning trade
