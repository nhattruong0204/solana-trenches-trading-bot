"""
Tests for the strategies module - Take Profit Strategy Management.
"""

import pytest
from src.strategies import (
    TakeProfitStrategy,
    StrategyType,
    StrategyManager,
    ALL_STRATEGIES,
    get_strategy_by_id,
    get_default_strategies,
    TRAILING_STOP_15,
    TRAILING_STOP_20,
    FIXED_EXIT_2X,
    TIERED_2X_3X,
)


class TestTakeProfitStrategy:
    """Tests for TakeProfitStrategy dataclass."""
    
    def test_create_trailing_stop_strategy(self):
        """Test creating a trailing stop strategy."""
        strategy = TakeProfitStrategy(
            id="test_trailing",
            name="Test Trailing Stop (20%)",
            strategy_type=StrategyType.TRAILING_STOP,
            rank=1,
            params={"stop_pct": 0.20},
            win_rate=75.0,
            net_pnl_sol=3.5,
            roi_pct=35.0,
        )
        
        assert strategy.id == "test_trailing"
        assert strategy.strategy_type == StrategyType.TRAILING_STOP
        assert strategy.params["stop_pct"] == 0.20
        assert strategy.enabled is False  # Default
    
    def test_create_fixed_exit_strategy(self):
        """Test creating a fixed exit strategy."""
        strategy = TakeProfitStrategy(
            id="test_fixed",
            name="Test Fixed Exit 3X",
            strategy_type=StrategyType.FIXED_EXIT,
            rank=2,
            params={"target_mult": 3.0, "stop_loss_mult": 0.5},
        )
        
        assert strategy.strategy_type == StrategyType.FIXED_EXIT
        assert strategy.params["target_mult"] == 3.0
    
    def test_create_tiered_strategy(self):
        """Test creating a tiered exit strategy."""
        strategy = TakeProfitStrategy(
            id="test_tiered",
            name="Test Tiered 2X+3X",
            strategy_type=StrategyType.TIERED_EXIT,
            rank=3,
            params={"tiers": [(2.0, 0.50), (3.0, 0.50)]},
        )
        
        assert strategy.strategy_type == StrategyType.TIERED_EXIT
        assert len(strategy.params["tiers"]) == 2
    
    def test_strategy_validation_empty_id(self):
        """Test that empty ID raises ValueError."""
        with pytest.raises(ValueError, match="Strategy ID cannot be empty"):
            TakeProfitStrategy(
                id="",
                name="Test",
                strategy_type=StrategyType.FIXED_EXIT,
                rank=1,
            )
    
    def test_strategy_validation_empty_name(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Strategy name cannot be empty"):
            TakeProfitStrategy(
                id="test",
                name="",
                strategy_type=StrategyType.FIXED_EXIT,
                rank=1,
            )
    
    def test_strategy_validation_invalid_rank(self):
        """Test that invalid rank raises ValueError."""
        with pytest.raises(ValueError, match="Rank must be >= 1"):
            TakeProfitStrategy(
                id="test",
                name="Test",
                strategy_type=StrategyType.FIXED_EXIT,
                rank=0,
            )
    
    def test_short_name_trailing_stop(self):
        """Test short_name for trailing stop strategy."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Long Name",
            strategy_type=StrategyType.TRAILING_STOP,
            rank=1,
            params={"stop_pct": 0.25},
        )
        assert strategy.short_name == "Trail 25%"
    
    def test_short_name_fixed_exit(self):
        """Test short_name for fixed exit strategy."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Long Name",
            strategy_type=StrategyType.FIXED_EXIT,
            rank=1,
            params={"target_mult": 3.5},
        )
        assert strategy.short_name == "Fixed 3.5X"
    
    def test_short_name_tiered_two_tiers(self):
        """Test short_name for 2-tier strategy."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Long Name",
            strategy_type=StrategyType.TIERED_EXIT,
            rank=1,
            params={"tiers": [(2.0, 0.5), (3.0, 0.5)]},
        )
        assert strategy.short_name == "Tiered 2.0X+3.0X"
    
    def test_short_name_tiered_three_tiers(self):
        """Test short_name for 3-tier strategy."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Long Name",
            strategy_type=StrategyType.TIERED_EXIT,
            rank=1,
            params={"tiers": [(2.0, 0.33), (3.0, 0.33), (5.0, 0.34)]},
        )
        assert strategy.short_name == "Tiered 3-way"
    
    def test_display_status(self):
        """Test display_status property."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Test",
            strategy_type=StrategyType.FIXED_EXIT,
            rank=1,
            enabled=False,
        )
        assert strategy.display_status == "⬜"
        
        strategy.enabled = True
        assert strategy.display_status == "✅"
    
    def test_rank_emoji(self):
        """Test rank_emoji property."""
        strategy = TakeProfitStrategy(
            id="test",
            name="Test",
            strategy_type=StrategyType.FIXED_EXIT,
            rank=1,
        )
        assert strategy.rank_emoji == "🥇"
        
        strategy.rank = 2
        assert strategy.rank_emoji == "🥈"
        
        strategy.rank = 3
        assert strategy.rank_emoji == "🥉"
        
        strategy.rank = 4
        assert strategy.rank_emoji == "#4"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        strategy = TakeProfitStrategy(
            id="test_id",
            name="Test Strategy",
            strategy_type=StrategyType.TRAILING_STOP,
            rank=5,
            enabled=True,
            params={"stop_pct": 0.15},
            win_rate=80.0,
            net_pnl_sol=4.5,
            roi_pct=45.0,
        )
        
        data = strategy.to_dict()
        
        assert data["id"] == "test_id"
        assert data["name"] == "Test Strategy"
        assert data["strategy_type"] == "trailing_stop"
        assert data["rank"] == 5
        assert data["enabled"] is True
        assert data["params"]["stop_pct"] == 0.15
        assert data["win_rate"] == 80.0
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "restored_id",
            "name": "Restored Strategy",
            "strategy_type": "fixed_exit",
            "rank": 3,
            "enabled": True,
            "params": {"target_mult": 2.5},
            "win_rate": 65.0,
            "net_pnl_sol": 2.0,
            "roi_pct": 20.0,
        }
        
        strategy = TakeProfitStrategy.from_dict(data)
        
        assert strategy.id == "restored_id"
        assert strategy.strategy_type == StrategyType.FIXED_EXIT
        assert strategy.enabled is True
        assert strategy.params["target_mult"] == 2.5


class TestStrategyManager:
    """Tests for StrategyManager."""
    
    def test_create_manager_with_defaults(self):
        """Test creating manager with default strategies."""
        manager = StrategyManager()
        
        assert len(manager.strategies) == 13  # All predefined strategies
        assert manager.active_strategy is None  # None enabled by default
    
    def test_get_strategy_by_id(self):
        """Test getting strategy by ID."""
        manager = StrategyManager()
        
        strategy = manager.get_strategy("trailing_15")
        assert strategy is not None
        assert strategy.name == "Trailing Stop (15%)"
        
        not_found = manager.get_strategy("nonexistent")
        assert not_found is None
    
    def test_toggle_strategy(self):
        """Test toggling strategy enabled state."""
        manager = StrategyManager()
        
        # Initially disabled
        strategy = manager.get_strategy("trailing_15")
        assert strategy.enabled is False
        
        # Toggle on
        new_state = manager.toggle_strategy("trailing_15")
        assert new_state is True
        assert strategy.enabled is True
        
        # Toggle off
        new_state = manager.toggle_strategy("trailing_15")
        assert new_state is False
        assert strategy.enabled is False
    
    def test_enable_strategy(self):
        """Test enabling a strategy."""
        manager = StrategyManager()
        
        result = manager.enable_strategy("fixed_2x")
        assert result is True
        
        strategy = manager.get_strategy("fixed_2x")
        assert strategy.enabled is True
    
    def test_disable_strategy(self):
        """Test disabling a strategy."""
        manager = StrategyManager()
        
        manager.enable_strategy("fixed_2x")
        result = manager.disable_strategy("fixed_2x")
        assert result is True
        
        strategy = manager.get_strategy("fixed_2x")
        assert strategy.enabled is False
    
    def test_disable_all(self):
        """Test disabling all strategies."""
        manager = StrategyManager()
        
        # Enable some strategies
        manager.enable_strategy("trailing_15")
        manager.enable_strategy("fixed_2x")
        manager.enable_strategy("tiered_2_3")
        
        assert len(manager.enabled_strategies) == 3
        
        manager.disable_all()
        assert len(manager.enabled_strategies) == 0
    
    def test_enable_only(self):
        """Test enabling only one strategy."""
        manager = StrategyManager()
        
        # Enable multiple
        manager.enable_strategy("trailing_15")
        manager.enable_strategy("fixed_2x")
        
        # Enable only one specific
        manager.enable_only("fixed_3x")
        
        enabled = manager.enabled_strategies
        assert len(enabled) == 1
        assert enabled[0].id == "fixed_3x"
    
    def test_active_strategy_returns_best_ranked(self):
        """Test that active_strategy returns highest-ranked enabled."""
        manager = StrategyManager()
        
        # Enable rank 3 and rank 11
        manager.enable_strategy("trailing_25")  # rank 3
        manager.enable_strategy("fixed_2x")     # rank 11
        
        active = manager.active_strategy
        assert active is not None
        assert active.id == "trailing_25"  # Should be rank 3
    
    def test_enabled_strategies_property(self):
        """Test enabled_strategies property."""
        manager = StrategyManager()
        
        assert len(manager.enabled_strategies) == 0
        
        manager.enable_strategy("trailing_15")
        manager.enable_strategy("trailing_20")
        
        enabled = manager.enabled_strategies
        assert len(enabled) == 2
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        manager = StrategyManager()
        manager.enable_strategy("trailing_15")
        manager.enable_strategy("fixed_3x")
        
        data = manager.to_dict()
        
        # Create new manager and restore
        new_manager = StrategyManager.from_dict(data)
        
        # Check enabled state preserved
        assert new_manager.get_strategy("trailing_15").enabled is True
        assert new_manager.get_strategy("fixed_3x").enabled is True
        assert new_manager.get_strategy("fixed_2x").enabled is False
    
    def test_should_sell_trailing_stop(self):
        """Test should_sell for trailing stop strategy."""
        manager = StrategyManager()
        manager.enable_only("trailing_20")  # 20% trailing stop
        
        # Peak at 3.0X, current at 2.5X (16.7% drop - should NOT sell)
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=2.5,
            peak_multiplier=3.0,
        )
        assert should_sell is False
        
        # Peak at 3.0X, current at 2.3X (23% drop - should sell)
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=2.3,
            peak_multiplier=3.0,
        )
        assert should_sell is True
        assert pct == 100.0
        assert "Trailing stop" in reason
    
    def test_should_sell_fixed_exit_target(self):
        """Test should_sell for fixed exit - target hit."""
        manager = StrategyManager()
        manager.enable_only("fixed_2x")  # 2.0X target
        
        # Current at 1.8X - should NOT sell
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=1.8,
            peak_multiplier=2.0,
        )
        assert should_sell is False
        
        # Current at 2.0X - should sell
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=2.0,
            peak_multiplier=2.0,
        )
        assert should_sell is True
        assert "Target" in reason
    
    def test_should_sell_fixed_exit_stop_loss(self):
        """Test should_sell for fixed exit - stop loss hit."""
        manager = StrategyManager()
        manager.enable_only("fixed_2x")  # Has 0.5X stop loss
        
        # Current at 0.4X - should sell (stop loss)
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=0.4,
            peak_multiplier=1.5,
        )
        assert should_sell is True
        assert "Stop loss" in reason
    
    def test_should_sell_tiered_exit(self):
        """Test should_sell for tiered exit strategy."""
        manager = StrategyManager()
        manager.enable_only("tiered_2_3")  # 2X(50%) + 3X(50%)
        
        # Current at 1.5X - should NOT sell
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=1.5,
            peak_multiplier=1.5,
        )
        assert should_sell is False
        
        # Current at 2.0X - should sell 50%
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=2.0,
            peak_multiplier=2.0,
        )
        assert should_sell is True
        assert "Tier" in reason
        assert pct == 50.0
    
    def test_should_sell_no_active_strategy(self):
        """Test should_sell when no strategy enabled."""
        manager = StrategyManager()
        
        should_sell, reason, pct = manager.should_sell(
            current_multiplier=5.0,
            peak_multiplier=5.0,
        )
        
        assert should_sell is False
        assert reason is None
        assert pct == 0.0


class TestPredefinedStrategies:
    """Tests for predefined strategy constants."""
    
    def test_all_strategies_count(self):
        """Test that ALL_STRATEGIES has correct count."""
        assert len(ALL_STRATEGIES) == 13
    
    def test_all_strategies_sorted_by_rank(self):
        """Test that ALL_STRATEGIES is sorted by rank."""
        ranks = [s.rank for s in ALL_STRATEGIES]
        assert ranks == sorted(ranks)
    
    def test_get_strategy_by_id_function(self):
        """Test get_strategy_by_id helper function."""
        strategy = get_strategy_by_id("trailing_15")
        assert strategy is not None
        assert strategy.rank == 1
        
        not_found = get_strategy_by_id("nonexistent")
        assert not_found is None
    
    def test_get_default_strategies(self):
        """Test get_default_strategies returns copies."""
        strategies = get_default_strategies()
        
        # Modify one
        strategies[0].enabled = True
        
        # Get again - should be fresh copies
        fresh = get_default_strategies()
        assert fresh[0].enabled is False
    
    def test_trailing_stop_15_is_rank_1(self):
        """Test that Trailing Stop 15% is rank 1 (best)."""
        assert TRAILING_STOP_15.rank == 1
        assert TRAILING_STOP_15.roi_pct == 40.3
    
    def test_all_strategy_types_present(self):
        """Test that all strategy types are represented."""
        types = {s.strategy_type for s in ALL_STRATEGIES}
        
        assert StrategyType.TRAILING_STOP in types
        assert StrategyType.FIXED_EXIT in types
        assert StrategyType.TIERED_EXIT in types


class TestStrategyType:
    """Tests for StrategyType enum."""
    
    def test_strategy_type_values(self):
        """Test StrategyType enum values."""
        assert StrategyType.TRAILING_STOP.value == "trailing_stop"
        assert StrategyType.FIXED_EXIT.value == "fixed_exit"
        assert StrategyType.TIERED_EXIT.value == "tiered_exit"
    
    def test_strategy_type_str(self):
        """Test StrategyType string representation."""
        assert str(StrategyType.TRAILING_STOP) == "trailing_stop"
