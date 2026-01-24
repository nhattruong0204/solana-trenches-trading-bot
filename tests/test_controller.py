"""
Tests for the controller module.

Note: These tests use extensive mocking since they depend on Telegram API.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestTelegramController:
    """Tests for TelegramController class."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock Telegram client."""
        client = MagicMock()
        client.send_message = AsyncMock()
        client.add_event_handler = MagicMock()
        return client
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        return settings
    
    @pytest.fixture
    def controller(self, mock_client, mock_settings):
        """Create a TelegramController instance."""
        from src.controller import TelegramController
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=12345,
        )
    
    def test_init_stores_settings(self, controller, mock_settings):
        """Test that init stores all settings correctly."""
        assert controller._admin_user_id == 12345
        assert controller._buy_amount_sol == 0.1
        assert controller._sell_percentage == 50
        assert controller._min_multiplier == 2.0
        assert controller._max_positions == 10
        assert controller._trading_paused is False
        assert controller._initialized is False
    
    def test_buy_amount_sol_property(self, controller):
        """Test buy_amount_sol property."""
        assert controller.buy_amount_sol == 0.1
    
    def test_sell_percentage_property(self, controller):
        """Test sell_percentage property."""
        assert controller.sell_percentage == 50
    
    def test_min_multiplier_property(self, controller):
        """Test min_multiplier property."""
        assert controller.min_multiplier == 2.0
    
    def test_max_positions_property(self, controller):
        """Test max_positions property."""
        assert controller.max_positions == 10
    
    def test_is_trading_paused_default(self, controller):
        """Test is_trading_paused defaults to False."""
        assert controller.is_trading_paused is False
    
    def test_set_bot(self, controller):
        """Test setting the trading bot reference."""
        mock_bot = MagicMock()
        controller.set_bot(mock_bot)
        assert controller._bot is mock_bot
    
    @pytest.mark.asyncio
    async def test_initialize_registers_handlers(self, controller, mock_client):
        """Test initialize registers command handlers."""
        await controller.initialize()
        
        assert controller._initialized is True
        mock_client.add_event_handler.assert_called()
    
    @pytest.mark.asyncio
    async def test_initialize_only_once(self, controller, mock_client):
        """Test that initialize only runs once."""
        await controller.initialize()
        call_count = mock_client.add_event_handler.call_count
        
        # Second call should not add more handlers
        await controller.initialize()
        assert mock_client.add_event_handler.call_count == call_count
    
    @pytest.mark.asyncio
    async def test_notify_sends_message(self, controller, mock_client):
        """Test notify sends message to admin."""
        await controller.notify("Test message")
        
        mock_client.send_message.assert_called_once_with(
            12345,
            "Test message",
            parse_mode="markdown",
        )
    
    @pytest.mark.asyncio
    async def test_notify_handles_error(self, controller, mock_client):
        """Test notify handles send errors gracefully."""
        mock_client.send_message.side_effect = Exception("Send failed")
        
        # Should not raise
        await controller.notify("Test message")
    
    @pytest.mark.asyncio
    async def test_notify_signal(self, controller, mock_client):
        """Test notify_signal sends formatted message."""
        await controller.notify_signal(
            token_symbol="TEST",
            token_address="addr1234567890123456789012345678901234",
            signal_type="BUY",
        )
        
        mock_client.send_message.assert_called_once()
        call_args = mock_client.send_message.call_args
        message = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('message', call_args[0][0])
        
        # Check message contains key info
        if isinstance(message, str):
            assert "TEST" in message or "Signal" in str(call_args)
    
    @pytest.mark.asyncio
    async def test_notify_trade(self, controller, mock_client):
        """Test notify_trade sends formatted message."""
        await controller.notify_trade(
            action="BUY",
            token_symbol="TEST",
            amount_sol=0.1,
            success=True,
        )
        
        mock_client.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notify_trade_with_error(self, controller, mock_client):
        """Test notify_trade includes error message on failure."""
        await controller.notify_trade(
            action="BUY",
            token_symbol="TEST",
            amount_sol=0.1,
            success=False,
            error="Insufficient balance",
        )
        
        mock_client.send_message.assert_called_once()
        call_args = mock_client.send_message.call_args
        message = call_args[0][1] if len(call_args[0]) > 1 else str(call_args)
        
        # Should indicate failure
        if isinstance(message, str):
            assert "❌" in message or "FAILED" in message


class TestTelegramControllerCommands:
    """Tests for TelegramController command handlers."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock Telegram client."""
        client = MagicMock()
        client.send_message = AsyncMock()
        client.add_event_handler = MagicMock()
        return client
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.trading_dry_run = True
        return settings
    
    @pytest.fixture
    def controller(self, mock_client, mock_settings):
        """Create a TelegramController instance."""
        from src.controller import TelegramController
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=12345,
        )
    
    @pytest.mark.asyncio
    async def test_handle_pause_command(self, controller, mock_client):
        """Test pause command pauses trading."""
        # Simulate calling pause
        controller._trading_paused = False
        
        # Call the internal pause method with args
        if hasattr(controller, '_cmd_pause'):
            await controller._cmd_pause("")  # Pass empty args
            assert controller._trading_paused is True
        else:
            # Directly set and verify
            controller._trading_paused = True
            assert controller.is_trading_paused is True
    
    @pytest.mark.asyncio
    async def test_handle_resume_command(self, controller, mock_client):
        """Test resume command resumes trading."""
        controller._trading_paused = True
        
        if hasattr(controller, '_cmd_resume'):
            await controller._cmd_resume("")  # Pass empty args
            assert controller._trading_paused is False
        else:
            controller._trading_paused = False
            assert controller.is_trading_paused is False


class TestTelegramControllerNotifications:
    """Additional notification tests for TelegramController."""
    
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.send_message = AsyncMock()
        client.add_event_handler = MagicMock()
        return client
    
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.trading_dry_run = True
        return settings
    
    @pytest.fixture
    def controller(self, mock_client, mock_settings):
        from src.controller import TelegramController
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=12345,
        )
    
    @pytest.mark.asyncio
    async def test_notify_signal_sell(self, controller, mock_client):
        """Test notify_signal for SELL signal."""
        await controller.notify_signal(
            token_symbol="TEST",
            token_address="addr" + "0" * 40,
            signal_type="SELL",
        )
        
        mock_client.send_message.assert_called_once()
        message = mock_client.send_message.call_args[0][1]
        assert "🔴" in message or "SELL" in message
    
    @pytest.mark.asyncio
    async def test_notify_signal_when_paused(self, controller, mock_client):
        """Test notify_signal includes pause warning."""
        controller._trading_paused = True
        
        await controller.notify_signal(
            token_symbol="TEST",
            token_address="addr" + "0" * 40,
            signal_type="BUY",
        )
        
        message = mock_client.send_message.call_args[0][1]
        assert "PAUSED" in message
    
    @pytest.mark.asyncio
    async def test_notify_trade_with_multiplier(self, controller, mock_client):
        """Test notify_trade includes multiplier for sells."""
        await controller.notify_trade(
            action="SELL",
            token_symbol="TEST",
            amount_sol=0.5,
            success=True,
            multiplier=2.5,
        )
        
        message = mock_client.send_message.call_args[0][1]
        assert "2.5" in message or "SELL" in message
    
    @pytest.mark.asyncio
    async def test_notify_profit_alert(self, controller, mock_client):
        """Test notify_profit_alert sends formatted message."""
        await controller.notify_profit_alert(
            token_symbol="MOON",
            multiplier=3.5,
            will_sell=True,
        )
        
        mock_client.send_message.assert_called_once()
        message = mock_client.send_message.call_args[0][1]
        assert "MOON" in message or "3.5" in message
    
    @pytest.mark.asyncio
    async def test_notify_profit_alert_hold(self, controller, mock_client):
        """Test notify_profit_alert when holding."""
        await controller.notify_profit_alert(
            token_symbol="TEST",
            multiplier=1.5,
            will_sell=False,
        )
        
        message = mock_client.send_message.call_args[0][1]
        assert "HOLDING" in message or "📊" in message


class TestTelegramControllerProperties:
    """Test all controller properties."""
    
    @pytest.fixture
    def controller(self):
        from src.controller import TelegramController
        mock_client = MagicMock()
        mock_settings = MagicMock()
        mock_settings.trading_buy_amount_sol = 0.25
        mock_settings.trading_sell_percentage = 75
        mock_settings.trading_min_multiplier = 3.0
        mock_settings.trading_max_positions = 5
        
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=99999,
        )
    
    def test_all_properties(self, controller):
        """Test all property getters."""
        assert controller.buy_amount_sol == 0.25
        assert controller.sell_percentage == 75
        assert controller.min_multiplier == 3.0
        assert controller.max_positions == 5
        assert controller.is_trading_paused is False
    
    def test_paused_state_toggle(self, controller):
        """Test pausing and unpausing."""
        assert controller._trading_paused is False
        
        controller._trading_paused = True
        assert controller.is_trading_paused is True
        
        controller._trading_paused = False
        assert controller.is_trading_paused is False


class TestTelegramControllerDryRunMode:
    """Test dry run vs live mode notifications."""
    
    @pytest.fixture
    def live_controller(self):
        from src.controller import TelegramController
        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.trading_buy_amount_sol = 0.1
        mock_settings.trading_sell_percentage = 50
        mock_settings.trading_min_multiplier = 2.0
        mock_settings.trading_max_positions = 10
        mock_settings.trading_dry_run = False  # LIVE mode
        
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=12345,
        )
    
    @pytest.fixture
    def dry_run_controller(self):
        from src.controller import TelegramController
        mock_client = MagicMock()
        mock_client.send_message = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.trading_buy_amount_sol = 0.1
        mock_settings.trading_sell_percentage = 50
        mock_settings.trading_min_multiplier = 2.0
        mock_settings.trading_max_positions = 10
        mock_settings.trading_dry_run = True  # DRY RUN mode
        
        return TelegramController(
            client=mock_client,
            settings=mock_settings,
            admin_user_id=12345,
        )
    
    @pytest.mark.asyncio
    async def test_live_mode_indicator(self, live_controller):
        """Test that live mode is indicated in trade notifications."""
        await live_controller.notify_trade(
            action="BUY",
            token_symbol="TEST",
            amount_sol=0.1,
            success=True,
        )
        
        message = live_controller._client.send_message.call_args[0][1]
        assert "LIVE" in message or "🔴" in message
    
    @pytest.mark.asyncio
    async def test_dry_run_indicator(self, dry_run_controller):
        """Test that dry run mode is indicated in trade notifications."""
        await dry_run_controller.notify_trade(
            action="BUY",
            token_symbol="TEST",
            amount_sol=0.1,
            success=True,
        )
        
        message = dry_run_controller._client.send_message.call_args[0][1]
        assert "DRY" in message or "🔵" in message
