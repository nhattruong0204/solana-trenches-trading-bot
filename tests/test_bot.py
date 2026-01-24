"""
Tests for the bot module (TradingBot orchestrator).
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path
import asyncio

from src.bot import TradingBot
from src.config import Settings
from src.exceptions import (
    TelegramConnectionError,
    TelegramAuthenticationError,
    ChannelNotFoundError,
)


class TestTradingBotInit:
    """Tests for TradingBot initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.trading_dry_run = True
        settings.trading_buy_amount_sol = 0.1
        settings.signal_channel = "test_channel"
        settings.gmgn_bot = "GMGN_sol_bot"
        settings.controller_enabled = False
        settings.admin_user_id = None
        settings.bot_token = None
        
        # Create nested trading mock
        trading = MagicMock()
        trading.buy_amount_sol = 0.1
        trading.sell_percentage = 50
        trading.min_multiplier_to_sell = 2.0
        trading.max_open_positions = 10
        trading.dry_run = True
        settings.trading = trading
        
        # Create nested telegram mock
        telegram = MagicMock()
        telegram.api_id = 12345
        telegram.api_hash = "test_hash"
        telegram.session_name = "test_session"
        settings.telegram = telegram
        
        return settings
    
    def test_init_creates_instance(self, mock_settings):
        """Test TradingBot initialization."""
        bot = TradingBot(mock_settings)
        
        assert bot._settings is mock_settings
        assert bot._client is None
        assert bot._trader is None
        assert bot._running is False
    
    def test_is_running_default_false(self, mock_settings):
        """Test is_running property defaults to False."""
        bot = TradingBot(mock_settings)
        assert bot.is_running is False
    
    def test_uptime_none_when_not_started(self, mock_settings):
        """Test uptime is None when bot hasn't started."""
        bot = TradingBot(mock_settings)
        assert bot.uptime is None
    
    def test_uptime_returns_seconds(self, mock_settings):
        """Test uptime returns seconds when bot is running."""
        bot = TradingBot(mock_settings)
        bot._start_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        
        uptime = bot.uptime
        assert uptime is not None
        assert 59 < uptime < 61
    
    def test_state_property(self, mock_settings):
        """Test state property."""
        bot = TradingBot(mock_settings)
        assert bot.state is None
        
        # Simulate state being set
        mock_state = MagicMock()
        bot._state = mock_state
        assert bot.state is mock_state


class TestTradingBotInitialization:
    """Tests for TradingBot _initialize method."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.trading_dry_run = True
        settings.signal_channel = "test_channel"
        settings.gmgn_bot = "GMGN_sol_bot"
        settings.controller_enabled = False
        settings.admin_user_id = None
        settings.bot_token = None
        
        telegram = MagicMock()
        telegram.api_id = 12345
        telegram.api_hash = "test_hash"
        telegram.session_name = "test_session"
        settings.telegram = telegram
        
        trading = MagicMock()
        trading.buy_amount_sol = 0.1
        trading.dry_run = True
        settings.trading = trading
        
        return settings
    
    @pytest.mark.asyncio
    async def test_init_telegram_connection_error(self, mock_settings):
        """Test handling of Telegram connection error."""
        bot = TradingBot(mock_settings)
        
        with patch('src.bot.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect.side_effect = Exception("Connection failed")
            mock_client_class.return_value = mock_client
            
            with patch('src.bot.TradingState'):
                with pytest.raises(TelegramConnectionError):
                    await bot._initialize()
    
    @pytest.mark.asyncio
    async def test_init_telegram_auth_error(self, mock_settings):
        """Test handling of Telegram authentication error."""
        bot = TradingBot(mock_settings)
        
        with patch('src.bot.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client
            
            with patch('src.bot.TradingState'):
                with pytest.raises(TelegramAuthenticationError):
                    await bot._initialize()


class TestTradingBotShutdown:
    """Tests for TradingBot shutdown."""
    
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        return settings
    
    @pytest.mark.asyncio
    async def test_shutdown_saves_state(self, mock_settings):
        """Test that shutdown saves state."""
        bot = TradingBot(mock_settings)
        
        mock_state = MagicMock()
        bot._state = mock_state
        
        await bot._shutdown()
        
        mock_state.save.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_handles_state_save_error(self, mock_settings):
        """Test shutdown handles state save error gracefully."""
        bot = TradingBot(mock_settings)
        
        mock_state = MagicMock()
        mock_state.save.side_effect = Exception("Save failed")
        bot._state = mock_state
        
        # Should not raise
        await bot._shutdown()
    
    @pytest.mark.asyncio
    async def test_shutdown_disconnects_client(self, mock_settings):
        """Test that shutdown disconnects Telegram client."""
        bot = TradingBot(mock_settings)
        
        mock_client = AsyncMock()
        bot._client = mock_client
        
        await bot._shutdown()
        
        mock_client.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_stops_notification_bot(self, mock_settings):
        """Test that shutdown stops notification bot."""
        bot = TradingBot(mock_settings)
        
        mock_notification_bot = AsyncMock()
        bot._notification_bot = mock_notification_bot
        
        await bot._shutdown()
        
        mock_notification_bot.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_sets_running_false(self, mock_settings):
        """Test that shutdown sets running to False."""
        bot = TradingBot(mock_settings)
        bot._running = True
        
        await bot._shutdown()
        
        assert bot._running is False


class TestTradingBotRequestShutdown:
    """Tests for shutdown request handling."""
    
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        return settings
    
    def test_request_shutdown_sets_event(self, mock_settings):
        """Test that request_shutdown sets the shutdown event."""
        bot = TradingBot(mock_settings)
        
        assert not bot._shutdown_event.is_set()
        
        bot._request_shutdown()
        
        assert bot._shutdown_event.is_set()


class TestTradingBotContextManager:
    """Tests for TradingBot async context manager."""
    
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        settings.telegram_api_id = 12345
        settings.telegram_api_hash = "test_hash"
        settings.controller_enabled = False
        
        telegram = MagicMock()
        telegram.api_id = 12345
        telegram.api_hash = "test_hash"
        telegram.session_name = "test_session"
        settings.telegram = telegram
        
        return settings
    
    @pytest.mark.asyncio
    async def test_aenter_calls_initialize(self, mock_settings):
        """Test that __aenter__ calls _initialize."""
        bot = TradingBot(mock_settings)
        
        with patch.object(bot, '_initialize', new_callable=AsyncMock) as mock_init:
            result = await bot.__aenter__()
            
            mock_init.assert_called_once()
            assert result is bot
    
    @pytest.mark.asyncio
    async def test_aexit_calls_shutdown(self, mock_settings):
        """Test that __aexit__ calls _shutdown."""
        bot = TradingBot(mock_settings)
        
        with patch.object(bot, '_shutdown', new_callable=AsyncMock) as mock_shutdown:
            await bot.__aexit__(None, None, None)
            
            mock_shutdown.assert_called_once()


class TestTradingBotBannerPrint:
    """Tests for startup banner."""
    
    @pytest.fixture
    def mock_settings(self):
        settings = MagicMock(spec=Settings)
        settings.state_file = "test_state.json"
        
        trading = MagicMock()
        trading.buy_amount_sol = 0.1
        trading.min_multiplier_to_sell = 2.0
        trading.sell_percentage = 50
        trading.max_open_positions = 10
        trading.dry_run = True
        settings.trading = trading
        
        return settings
    
    def test_print_startup_banner_dry_run(self, mock_settings, capsys):
        """Test startup banner in dry run mode."""
        bot = TradingBot(mock_settings)
        
        mock_state = MagicMock()
        mock_state.open_position_count = 3
        bot._state = mock_state
        
        bot._print_startup_banner()
        
        captured = capsys.readouterr()
        assert "SOLANA AUTO TRADING BOT" in captured.out
        assert "DRY RUN MODE" in captured.out
    
    def test_print_startup_banner_live(self, mock_settings, capsys):
        """Test startup banner in live mode."""
        mock_settings.trading.dry_run = False
        bot = TradingBot(mock_settings)
        
        mock_state = MagicMock()
        mock_state.open_position_count = 0
        bot._state = mock_state
        
        bot._print_startup_banner()
        
        captured = capsys.readouterr()
        assert "LIVE TRADING MODE" in captured.out
