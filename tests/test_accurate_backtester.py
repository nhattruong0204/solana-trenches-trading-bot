"""
Tests for the accurate_backtester module.

Tests dataclasses, calculations, and backtest logic without requiring network calls.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.accurate_backtester import (
    BacktestConfig,
    BacktestTrade,
    BacktestResult,
    AccurateBacktester,
)
from src.strategy_simulator import ExitReason, TradingFees, DEFAULT_FEES


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = BacktestConfig()
        
        assert config.position_size == 0.1
        assert config.starting_capital == 10.0
        assert config.max_hold_hours == 72
        assert config.candle_timeframe == 15
        assert config.fees is not None
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = BacktestConfig(
            position_size=0.5,
            starting_capital=50.0,
            max_hold_hours=24,
            candle_timeframe=5,
        )
        
        assert config.position_size == 0.5
        assert config.starting_capital == 50.0
        assert config.max_hold_hours == 24
        assert config.candle_timeframe == 5


class TestBacktestTrade:
    """Tests for BacktestTrade dataclass."""
    
    @pytest.fixture
    def sample_trade(self):
        """Create a sample trade for testing."""
        return BacktestTrade(
            symbol="TEST",
            address="addr123456789012345678901234567890",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=2),
            exit_price=0.002,
            exit_reason=ExitReason.TRAILING_STOP,
            exit_multiplier=2.0,
            peak_price=0.0025,
            peak_multiplier=2.5,
            position_size=0.1,
        )
    
    def test_create_trade(self, sample_trade):
        """Test creating a trade."""
        assert sample_trade.symbol == "TEST"
        assert sample_trade.exit_multiplier == 2.0
        assert sample_trade.peak_multiplier == 2.5
    
    def test_pnl_multiplier_winning_trade(self, sample_trade):
        """Test PnL multiplier for a winning trade."""
        # Exit multiplier is 2.0, should be profitable after fees
        pnl = sample_trade.pnl_multiplier
        assert pnl > 1.0  # Profitable
        assert pnl < 2.0  # Less than 2x due to fees
    
    def test_pnl_multiplier_no_exit(self):
        """Test PnL multiplier when no exit."""
        trade = BacktestTrade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            position_size=0.1,
        )
        
        assert trade.pnl_multiplier == 0.0
    
    def test_pnl_sol_winning(self, sample_trade):
        """Test PnL in SOL for winning trade."""
        pnl = sample_trade.pnl_sol
        # Position is 0.1 SOL at 2x, should be positive
        assert pnl > 0
    
    def test_pnl_sol_losing(self):
        """Test PnL in SOL for losing trade."""
        trade = BacktestTrade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_time=datetime.now(timezone.utc),
            exit_price=0.0005,
            exit_multiplier=0.5,
            position_size=0.1,
        )
        
        assert trade.pnl_sol < 0  # Lost money
    
    def test_total_fees_sol_without_exit(self):
        """Test fees when trade has no exit."""
        trade = BacktestTrade(
            symbol="TEST",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            position_size=0.1,
        )
        
        # Should only have buy fees
        fees = trade.total_fees_sol
        assert fees > 0
    
    def test_total_fees_sol_with_exit(self, sample_trade):
        """Test total fees with both buy and sell."""
        fees = sample_trade.total_fees_sol
        assert fees > 0  # Should have both buy and sell fees


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""
    
    @pytest.fixture
    def winning_trade(self):
        return BacktestTrade(
            symbol="WIN",
            address="addr1",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            exit_price=0.003,
            exit_multiplier=3.0,
            position_size=0.1,
        )
    
    @pytest.fixture
    def losing_trade(self):
        return BacktestTrade(
            symbol="LOSE",
            address="addr2",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_time=datetime.now(timezone.utc) + timedelta(hours=1),
            exit_price=0.0005,
            exit_multiplier=0.5,
            position_size=0.1,
        )
    
    def test_empty_result(self):
        """Test empty backtest result."""
        result = BacktestResult(strategy_name="Test")
        
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.total_pnl_sol == 0.0
        assert result.avg_multiplier == 0.0
    
    def test_total_trades(self, winning_trade, losing_trade):
        """Test total trades count."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade, winning_trade],
        )
        
        assert result.total_trades == 3
    
    def test_winning_and_losing_trades(self, winning_trade, losing_trade):
        """Test winning/losing trade count."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade, winning_trade, losing_trade],
        )
        
        assert result.winning_trades == 2
        assert result.losing_trades == 1
    
    def test_win_rate(self, winning_trade, losing_trade):
        """Test win rate calculation."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],  # 50% win rate
        )
        
        # Win rate = winning / total * 100
        # 1 winning, 1 losing = 50%
        assert result.win_rate == 50.0
    
    def test_total_pnl_sol(self, winning_trade, losing_trade):
        """Test total PnL calculation."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        # Sum of PnL from both trades
        expected = winning_trade.pnl_sol + losing_trade.pnl_sol
        assert result.total_pnl_sol == expected
    
    def test_roi(self, winning_trade):
        """Test ROI calculation."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade],
            total_capital=1.0,
        )
        
        # ROI = (PnL / capital) * 100
        expected_roi = (winning_trade.pnl_sol / 1.0) * 100
        assert abs(result.roi - expected_roi) < 0.01
    
    def test_roi_zero_capital(self):
        """Test ROI with zero capital."""
        result = BacktestResult(
            strategy_name="Test",
            total_capital=0,
        )
        
        assert result.roi == 0.0
    
    def test_avg_multiplier(self, winning_trade, losing_trade):
        """Test average multiplier."""
        result = BacktestResult(
            strategy_name="Test",
            trades=[winning_trade, losing_trade],
        )
        
        # Average of multipliers
        expected = (winning_trade.pnl_multiplier + losing_trade.pnl_multiplier) / 2
        assert abs(result.avg_multiplier - expected) < 0.01
    
    def test_avg_hold_time_hours(self):
        """Test average hold time calculation."""
        entry = datetime.now(timezone.utc)
        trade1 = BacktestTrade(
            symbol="T1", address="a1",
            entry_time=entry,
            entry_price=0.001,
            exit_time=entry + timedelta(hours=2),
            exit_multiplier=1.5,
        )
        trade2 = BacktestTrade(
            symbol="T2", address="a2",
            entry_time=entry,
            entry_price=0.001,
            exit_time=entry + timedelta(hours=4),
            exit_multiplier=1.5,
        )
        
        result = BacktestResult(
            strategy_name="Test",
            trades=[trade1, trade2],
        )
        
        # Average of 2 and 4 hours = 3
        assert abs(result.avg_hold_time_hours - 3.0) < 0.1
    
    def test_summary(self, winning_trade):
        """Test summary dict generation."""
        result = BacktestResult(
            strategy_name="Test Strategy",
            trades=[winning_trade],
            tokens_with_data=10,
            tokens_without_data=2,
            data_coverage_pct=83.3,
        )
        
        summary = result.summary()
        
        assert summary["strategy"] == "Test Strategy"
        assert summary["total_trades"] == 1
        assert "win_rate" in summary
        assert "total_pnl_sol" in summary
        assert "roi" in summary
        assert summary["tokens_with_data"] == 10


class TestAccurateBacktester:
    """Tests for AccurateBacktester class."""
    
    @pytest.fixture
    def sample_signals(self):
        """Create sample signals for backtesting."""
        return [
            {
                "symbol": "TEST1",
                "address": "addr1111111111111111111111111111111",
                "signal_timestamp": "2024-01-01T12:00:00Z",
            },
            {
                "symbol": "TEST2",
                "address": "addr2222222222222222222222222222222",
                "signal_timestamp": "2024-01-02T12:00:00Z",
            },
        ]
    
    def test_create_backtester(self, sample_signals):
        """Test creating a backtester."""
        backtester = AccurateBacktester(sample_signals)
        
        assert len(backtester.signals) == 2
        assert backtester.config.position_size == 0.1
        assert backtester.price_histories == {}
    
    def test_create_with_custom_config(self, sample_signals):
        """Test creating backtester with custom config."""
        config = BacktestConfig(position_size=0.5)
        backtester = AccurateBacktester(sample_signals, config=config)
        
        assert backtester.config.position_size == 0.5
    
    def test_create_with_pre_fetched_histories(self, sample_signals):
        """Test creating backtester with pre-fetched data."""
        histories = {"addr1": MagicMock()}
        backtester = AccurateBacktester(
            sample_signals,
            price_histories=histories
        )
        
        assert len(backtester.price_histories) == 1


class TestTradingFees:
    """Tests for fee calculations."""
    
    def test_default_fees(self):
        """Test default fee structure."""
        fees = DEFAULT_FEES
        
        assert fees.buy_fee_pct > 0
        assert fees.network_fee_sol > 0
    
    def test_calculate_buy_cost(self):
        """Test buy cost calculation."""
        fees = DEFAULT_FEES
        position = 1.0
        
        effective, fee_amount = fees.calculate_buy_cost(position)
        
        assert effective < position  # Got less due to fees
        assert fee_amount > 0
    
    def test_calculate_sell_proceeds(self):
        """Test sell proceeds calculation."""
        fees = DEFAULT_FEES
        gross = 2.0
        
        net, fee_amount = fees.calculate_sell_proceeds(gross)
        
        assert net < gross  # Got less due to fees
        assert fee_amount > 0


class TestExitReason:
    """Tests for ExitReason enum."""
    
    def test_exit_reasons_exist(self):
        """Test that exit reasons are defined."""
        assert ExitReason.TRAILING_STOP is not None
        assert ExitReason.STOP_LOSS is not None
        assert ExitReason.TARGET_HIT is not None
        assert ExitReason.TIME_EXIT is not None
    
    def test_exit_reason_values(self):
        """Test exit reason string values."""
        assert ExitReason.TRAILING_STOP.value == "trailing_stop"
        assert ExitReason.RUGGED.value == "rugged"


class TestBacktestTradeEdgeCases:
    """Test edge cases for BacktestTrade."""
    
    def test_trade_at_1x_multiplier(self):
        """Test trade that breaks even (1x)."""
        trade = BacktestTrade(
            symbol="EVEN",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_multiplier=1.0,
            position_size=0.1,
        )
        
        # At 1x, after fees should be slightly negative
        assert trade.pnl_multiplier < 1.0
    
    def test_trade_very_small_multiplier(self):
        """Test trade with very small exit multiplier."""
        trade = BacktestTrade(
            symbol="TINY",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_multiplier=0.01,  # 99% loss
            position_size=0.1,
        )
        
        assert trade.pnl_multiplier < 0.1
        assert trade.pnl_sol < 0
    
    def test_trade_very_large_multiplier(self):
        """Test trade with very large exit multiplier."""
        trade = BacktestTrade(
            symbol="MOON",
            address="addr123",
            entry_time=datetime.now(timezone.utc),
            entry_price=0.001,
            exit_multiplier=100.0,  # 100x
            position_size=0.1,
        )
        
        assert trade.pnl_multiplier > 90  # Should be close to 100x after fees
        assert trade.pnl_sol > 0


class TestBacktestResultEdgeCases:
    """Test edge cases for BacktestResult."""
    
    def test_all_winning_trades(self):
        """Test result with all winning trades."""
        trades = [
            BacktestTrade(
                symbol=f"WIN{i}",
                address=f"addr{i}",
                entry_time=datetime.now(timezone.utc),
                entry_price=0.001,
                exit_multiplier=2.0,
            ) for i in range(5)
        ]
        
        result = BacktestResult(strategy_name="Winners", trades=trades)
        
        assert result.win_rate == 100.0
        assert result.total_pnl_sol > 0
    
    def test_all_losing_trades(self):
        """Test result with all losing trades."""
        trades = [
            BacktestTrade(
                symbol=f"LOSE{i}",
                address=f"addr{i}",
                entry_time=datetime.now(timezone.utc),
                entry_price=0.001,
                exit_multiplier=0.5,
            ) for i in range(5)
        ]
        
        result = BacktestResult(strategy_name="Losers", trades=trades)
        
        assert result.win_rate == 0.0
        assert result.total_pnl_sol < 0
    
    def test_large_trade_count(self):
        """Test result with many trades."""
        trades = [
            BacktestTrade(
                symbol=f"T{i}",
                address=f"addr{i}",
                entry_time=datetime.now(timezone.utc),
                entry_price=0.001,
                exit_multiplier=1.5 if i % 2 == 0 else 0.5,
            ) for i in range(100)
        ]
        
        result = BacktestResult(strategy_name="Large", trades=trades)
        
        assert result.total_trades == 100
        # 50 wins, 50 losses
        assert result.win_rate == 50.0
