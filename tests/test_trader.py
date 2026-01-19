"""
Tests for the trader module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.trader import GMGNTrader, MockTrader
from src.models import TradeResult


class TestGMGNTrader:
    """Tests for GMGNTrader."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock Telegram client."""
        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=MagicMock())
        client.send_message = AsyncMock()
        return client
    
    @pytest.fixture
    def trader(self, mock_client):
        """Create a GMGN trader instance."""
        return GMGNTrader(mock_client, dry_run=True)
    
    @pytest.mark.asyncio
    async def test_initialize(self, trader, mock_client):
        """Test trader initialization."""
        await trader.initialize()
        
        assert trader.is_initialized
        mock_client.get_entity.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_buy_token_dry_run(self, trader):
        """Test buy token in dry run mode."""
        await trader.initialize()
        
        result = await trader.buy_token(
            token_address="test_address_12345678901234567890123",
            amount_sol=0.1,
            symbol="TEST",
        )
        
        assert result.success is True
        assert result.dry_run is True
        assert result.action == "buy"
        assert result.amount == 0.1
    
    @pytest.mark.asyncio
    async def test_sell_token_dry_run(self, trader):
        """Test sell token in dry run mode."""
        await trader.initialize()
        
        result = await trader.sell_token(
            token_address="test_address_12345678901234567890123",
            percentage=50,
            symbol="TEST",
        )
        
        assert result.success is True
        assert result.dry_run is True
        assert result.action == "sell"
        assert result.amount == 50.0
    
    @pytest.mark.asyncio
    async def test_buy_token_live(self, mock_client):
        """Test buy token in live mode."""
        trader = GMGNTrader(mock_client, dry_run=False)
        await trader.initialize()
        
        result = await trader.buy_token(
            token_address="test_address_12345678901234567890123",
            amount_sol=0.1,
            symbol="TEST",
        )
        
        assert result.success is True
        assert result.dry_run is False
        mock_client.send_message.assert_called_once()
        
        # Check command format
        call_args = mock_client.send_message.call_args
        command = call_args[0][1]
        assert "/buy" in command
        assert "0.1" in command
    
    @pytest.mark.asyncio
    async def test_sell_token_live(self, mock_client):
        """Test sell token in live mode."""
        trader = GMGNTrader(mock_client, dry_run=False)
        await trader.initialize()
        
        result = await trader.sell_token(
            token_address="test_address_12345678901234567890123",
            percentage=50,
            symbol="TEST",
        )
        
        assert result.success is True
        mock_client.send_message.assert_called_once()
        
        # Check command format
        call_args = mock_client.send_message.call_args
        command = call_args[0][1]
        assert "/sell" in command
        assert "50%" in command
    
    @pytest.mark.asyncio
    async def test_trade_count(self, mock_client):
        """Test trade counter."""
        trader = GMGNTrader(mock_client, dry_run=False)
        await trader.initialize()
        
        assert trader.trade_count == 0
        
        await trader.buy_token("addr1234567890123456789012345678901", 0.1, "TEST")
        assert trader.trade_count == 1
        
        await trader.sell_token("addr1234567890123456789012345678901", 50, "TEST")
        assert trader.trade_count == 2


class TestMockTrader:
    """Tests for MockTrader."""
    
    @pytest.mark.asyncio
    async def test_mock_buy(self):
        """Test mock buy records trade."""
        trader = MockTrader()
        await trader.initialize()
        
        result = await trader.buy_token(
            token_address="test_address_12345678901234567890123",
            amount_sol=0.1,
            symbol="TEST",
        )
        
        assert result.success is True
        assert len(trader.trades) == 1
        assert trader.trades[0].is_buy is True
    
    @pytest.mark.asyncio
    async def test_mock_sell(self):
        """Test mock sell records trade."""
        trader = MockTrader()
        await trader.initialize()
        
        result = await trader.sell_token(
            token_address="test_address_12345678901234567890123",
            percentage=50,
            symbol="TEST",
        )
        
        assert result.success is True
        assert len(trader.trades) == 1
        assert trader.trades[0].is_sell is True
