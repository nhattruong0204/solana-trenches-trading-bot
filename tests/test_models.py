"""
Tests for the models module.
"""

import pytest
from datetime import datetime, timezone, timedelta

from src.models import (
    Position,
    PositionStatus,
    BuySignal,
    ProfitAlert,
    TradeResult,
)


class TestPosition:
    """Tests for the Position model."""
    
    def test_create_position(self, sample_position):
        """Test creating a position with default values."""
        pos = sample_position
        
        assert pos.token_address == "6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump"
        assert pos.token_symbol == "TRUMP"
        assert pos.buy_amount_sol == 0.1
        assert pos.status == PositionStatus.OPEN
        assert pos.sold_percentage == 0.0
        assert pos.last_multiplier == 1.0
    
    def test_position_validation(self):
        """Test position validation on creation."""
        with pytest.raises(ValueError, match="Token address cannot be empty"):
            Position(
                token_address="",
                token_symbol="TEST",
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=0.1,
                signal_msg_id=1,
            )
        
        with pytest.raises(ValueError, match="Buy amount must be positive"):
            Position(
                token_address="validaddress123456789012345678901234",
                token_symbol="TEST",
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=-0.1,
                signal_msg_id=1,
            )
    
    def test_position_is_open(self, sample_position):
        """Test is_open property."""
        assert sample_position.is_open is True
        sample_position.status = PositionStatus.PARTIAL_SOLD
        assert sample_position.is_open is False
    
    def test_position_remaining_percentage(self, sample_position):
        """Test remaining_percentage calculation."""
        assert sample_position.remaining_percentage == 100.0
        sample_position.sold_percentage = 50.0
        assert sample_position.remaining_percentage == 50.0
    
    def test_position_estimated_value(self, sample_position):
        """Test estimated value calculation."""
        sample_position.last_multiplier = 2.0
        assert sample_position.estimated_value_sol == 0.2  # 0.1 * 1.0 * 2.0
        
        sample_position.sold_percentage = 50.0
        assert sample_position.estimated_value_sol == 0.1  # 0.1 * 0.5 * 2.0
    
    def test_position_holding_duration(self, sample_position):
        """Test holding duration calculation."""
        # Position created now, so duration should be very small
        assert sample_position.holding_duration < 1  # Less than 1 hour
    
    def test_position_to_dict(self, sample_position):
        """Test serialization to dictionary."""
        data = sample_position.to_dict()
        
        assert data["token_address"] == sample_position.token_address
        assert data["token_symbol"] == sample_position.token_symbol
        assert data["buy_amount_sol"] == sample_position.buy_amount_sol
        assert data["status"] == "open"
        assert "buy_time" in data
    
    def test_position_from_dict(self, sample_position):
        """Test deserialization from dictionary."""
        data = sample_position.to_dict()
        restored = Position.from_dict(data)
        
        assert restored.token_address == sample_position.token_address
        assert restored.token_symbol == sample_position.token_symbol
        assert restored.buy_amount_sol == sample_position.buy_amount_sol
        assert restored.status == sample_position.status
    
    def test_position_mark_partial_sell(self, sample_position):
        """Test marking position as partially sold."""
        sample_position.mark_partial_sell(50.0, 2.5)
        
        assert sample_position.status == PositionStatus.PARTIAL_SOLD
        assert sample_position.sold_percentage == 50.0
        assert sample_position.last_multiplier == 2.5
    
    def test_position_mark_closed(self, sample_position):
        """Test marking position as closed."""
        sample_position.mark_closed(3.0)
        
        assert sample_position.status == PositionStatus.CLOSED
        assert sample_position.sold_percentage == 100.0
        assert sample_position.last_multiplier == 3.0


class TestBuySignal:
    """Tests for the BuySignal model."""
    
    def test_create_buy_signal(self, sample_buy_signal):
        """Test creating a buy signal."""
        signal = sample_buy_signal
        
        assert signal.message_id == 12345
        assert signal.token_symbol == "TRUMP"
        assert signal.token_address == "6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump"
    
    def test_buy_signal_validation(self):
        """Test buy signal validation."""
        with pytest.raises(ValueError, match="Token address cannot be empty"):
            BuySignal(
                message_id=1,
                token_symbol="TEST",
                token_address="",
            )
        
        with pytest.raises(ValueError, match="Invalid Solana address"):
            BuySignal(
                message_id=1,
                token_symbol="TEST",
                token_address="short",
            )


class TestProfitAlert:
    """Tests for the ProfitAlert model."""
    
    def test_create_profit_alert(self, sample_profit_alert):
        """Test creating a profit alert."""
        alert = sample_profit_alert
        
        assert alert.message_id == 12346
        assert alert.reply_to_msg_id == 12345
        assert alert.multiplier == 2.5
    
    def test_profit_alert_validation(self):
        """Test profit alert validation."""
        with pytest.raises(ValueError, match="Multiplier must be positive"):
            ProfitAlert(
                message_id=1,
                reply_to_msg_id=100,
                multiplier=-1.0,
            )


class TestTradeResult:
    """Tests for the TradeResult model."""
    
    def test_create_trade_result(self):
        """Test creating a trade result."""
        result = TradeResult(
            success=True,
            token_address="address123",
            token_symbol="TEST",
            action="buy",
            amount=0.1,
            message="Buy successful",
        )
        
        assert result.success is True
        assert result.is_buy is True
        assert result.is_sell is False
    
    def test_trade_result_sell(self):
        """Test sell trade result."""
        result = TradeResult(
            success=True,
            token_address="address123",
            token_symbol="TEST",
            action="sell",
            amount=50.0,
            message="Sell successful",
        )
        
        assert result.is_buy is False
        assert result.is_sell is True
