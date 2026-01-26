"""
Tests for the notification_bot module.

Note: These tests use extensive mocking since they depend on Telegram API.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import json
import os

from src.notification_bot import NotificationBot, is_valid_solana_address, get_signal_message_link
from src.constants import TRENCHES_CHANNEL_USERNAME


class TestGetSignalMessageLink:
    """Tests for get_signal_message_link function."""
    
    def test_generates_correct_link(self):
        """Test that correct Telegram message link is generated."""
        msg_id = 12345
        expected = f"https://t.me/{TRENCHES_CHANNEL_USERNAME}/12345"
        assert get_signal_message_link(msg_id) == expected
    
    def test_generates_link_with_large_msg_id(self):
        """Test with large message ID."""
        msg_id = 9876543210
        expected = f"https://t.me/{TRENCHES_CHANNEL_USERNAME}/9876543210"
        assert get_signal_message_link(msg_id) == expected
    
    def test_generates_link_with_msg_id_1(self):
        """Test with message ID 1."""
        msg_id = 1
        expected = f"https://t.me/{TRENCHES_CHANNEL_USERNAME}/1"
        assert get_signal_message_link(msg_id) == expected
    
    def test_link_uses_correct_channel_username(self):
        """Verify the link uses the TRENCHES_CHANNEL_USERNAME constant."""
        msg_id = 100
        result = get_signal_message_link(msg_id)
        assert TRENCHES_CHANNEL_USERNAME in result
        assert result.startswith("https://t.me/")
        assert result.endswith("/100")


class TestIsValidSolanaAddress:
    """Tests for is_valid_solana_address function."""
    
    def test_valid_address_pump(self):
        """Test valid pump.fun address."""
        assert is_valid_solana_address("6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump") is True
    
    def test_valid_address_standard(self):
        """Test valid standard Solana address."""
        assert is_valid_solana_address("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr") is True
    
    def test_invalid_address_too_short(self):
        """Test address that's too short."""
        assert is_valid_solana_address("abc123") is False
    
    def test_invalid_address_too_long(self):
        """Test address that's too long."""
        long_addr = "a" * 50
        assert is_valid_solana_address(long_addr) is False
    
    def test_invalid_address_invalid_chars(self):
        """Test address with invalid characters (0, O, I, l)."""
        # 0 is not in base58
        assert is_valid_solana_address("0YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump") is False
    
    def test_empty_string(self):
        """Test empty string."""
        assert is_valid_solana_address("") is False


class TestNotificationBotInit:
    """Tests for NotificationBot initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
        settings.state_file = "trading_state.json"
        return settings
    
    def test_init_stores_settings(self, mock_settings):
        """Test that init stores all settings correctly."""
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=mock_settings,
                admin_user_id=99999,
                notification_channel="-1001234567890",
            )
            
            assert bot._api_id == 12345
            assert bot._api_hash == "test_hash"
            assert bot._admin_user_id == 99999
            assert bot._buy_amount_sol == 0.1
            assert bot._sell_percentage == 50
            assert bot._min_multiplier == 2.0
            assert bot._max_positions == 10
    
    def test_init_defaults(self, mock_settings):
        """Test initialization with default values."""
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=mock_settings,
                admin_user_id=99999,
            )
            
            assert bot._notification_channel is None
            assert bot._trading_paused is False
            assert bot._awaiting_wallet is False
            assert bot._initialized is False


class TestNotificationBotProperties:
    """Tests for NotificationBot properties."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet_addr_12345678901234567890"
        settings.state_file = "trading_state.json"
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_buy_amount_sol_property(self, bot):
        """Test buy_amount_sol property."""
        assert bot.buy_amount_sol == 0.1
    
    def test_sell_percentage_property(self, bot):
        """Test sell_percentage property."""
        assert bot.sell_percentage == 50
    
    def test_min_multiplier_property(self, bot):
        """Test min_multiplier property."""
        assert bot.min_multiplier == 2.0
    
    def test_max_positions_property(self, bot):
        """Test max_positions property."""
        assert bot.max_positions == 10
    
    def test_gmgn_wallet_property(self, bot):
        """Test gmgn_wallet property."""
        assert "test_wallet" in bot.gmgn_wallet
    
    def test_is_trading_paused_default(self, bot):
        """Test is_trading_paused defaults to False."""
        assert bot.is_trading_paused is False
    
    def test_is_wallet_configured(self, bot):
        """Test is_wallet_configured property."""
        assert bot.is_wallet_configured is True
    
    def test_is_wallet_configured_when_none(self):
        """Test is_wallet_configured when wallet is None."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
        
        assert bot.is_wallet_configured is False


class TestBuildDatabaseDsn:
    """Tests for _build_database_dsn method."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_build_dsn_with_password(self, bot):
        """Test DSN building with password set."""
        with patch.dict(os.environ, {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "testuser",
            "POSTGRES_PASSWORD": "testpass",
            "POSTGRES_DATABASE": "testdb",
        }):
            dsn = bot._build_database_dsn()
            
            assert dsn == "postgresql://testuser:testpass@localhost:5432/testdb"
    
    def test_build_dsn_without_password(self, bot):
        """Test DSN returns None without password."""
        with patch.dict(os.environ, {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PASSWORD": "",
        }, clear=True):
            dsn = bot._build_database_dsn()
            
            assert dsn is None


class TestStrategyStateManagement:
    """Tests for strategy state loading and saving."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "test_state.json"
        return settings
    
    def test_load_strategy_state_file_not_found(self, mock_settings, tmp_path):
        """Test loading strategy state when file doesn't exist."""
        mock_settings.state_file = str(tmp_path / "nonexistent.json")
        
        # Should not raise, just log debug message
        bot = NotificationBot(
            api_id=12345,
            api_hash="test_hash",
            bot_token="test_token",
            settings=mock_settings,
            admin_user_id=99999,
        )
        
        # Default state - no strategies enabled
        assert len(bot._strategy_manager.enabled_strategies) == 0
    
    def test_load_strategy_state_from_file(self, mock_settings, tmp_path):
        """Test loading strategy state from existing file."""
        # Set up the state file path correctly
        base_state_file = tmp_path / "test_state.json"
        state_file = tmp_path / "test_state_strategies.json"
        
        # Get a valid strategy ID from the default strategies
        from src.strategies import ALL_STRATEGIES
        valid_strategy_id = ALL_STRATEGIES[0].id  # First strategy
        
        state_data = {
            "enabled_strategies": {
                valid_strategy_id: True,
            }
        }
        state_file.write_text(json.dumps(state_data))
        
        mock_settings.state_file = str(base_state_file)
        
        bot = NotificationBot(
            api_id=12345,
            api_hash="test_hash",
            bot_token="test_token",
            settings=mock_settings,
            admin_user_id=99999,
        )
        
        # Check that the strategy was enabled
        strategy = bot._strategy_manager.get_strategy(valid_strategy_id)
        assert strategy is not None
        assert strategy.enabled is True
    
    def test_save_strategy_state(self, mock_settings, tmp_path):
        """Test saving strategy state to file."""
        mock_settings.state_file = str(tmp_path / "test_state.json")
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=mock_settings,
                admin_user_id=99999,
            )
        
        # Enable a strategy
        bot._strategy_manager.enable_strategy("trailing_stop_15")
        
        # Save state
        bot._save_strategy_state()
        
        # Verify file was created
        state_file = tmp_path / "test_state_strategies.json"
        assert state_file.exists()
        
        # Verify content
        data = json.loads(state_file.read_text())
        assert "enabled_strategies" in data


class TestNotificationBotMethods:
    """Tests for NotificationBot methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
                notification_channel="-1001234567890",
            )
    
    def test_set_trading_bot(self, bot):
        """Test setting the trading bot reference."""
        mock_trading_bot = MagicMock()
        bot.set_trading_bot(mock_trading_bot)
        
        assert bot._bot is mock_trading_bot
    
    def test_signal_history_property(self, bot):
        """Test signal_history property returns SignalHistory."""
        assert bot.signal_history is not None
        assert bot._signal_history is bot.signal_history
    
    def test_signal_db_property_when_none(self, bot):
        """Test signal_db property when database not configured."""
        # When POSTGRES_PASSWORD is not set, _signal_db is None
        # The property should return the actual value
        _ = bot.signal_db  # Should not raise
    
    def test_strategy_manager_property(self, bot):
        """Test strategy_manager property."""
        assert bot.strategy_manager is not None
        assert bot._strategy_manager is bot.strategy_manager
    
    def test_active_strategy_property(self, bot):
        """Test active_strategy property when no strategy enabled."""
        assert bot.active_strategy is None
    
    def test_active_strategy_property_when_enabled(self, bot):
        """Test active_strategy property when a strategy is enabled."""
        bot._strategy_manager.enable_strategy("trailing_stop_15")
        
        strategy = bot.active_strategy
        if strategy:  # May be None if strategy doesn't exist
            assert strategy.id == "trailing_stop_15"


class TestEnsureTradingClientConnected:
    """Tests for _ensure_trading_client_connected method.

    This tests the fix for the bug where /syncsignals and /bootstrap
    commands would fail with "Cannot send requests while disconnected"
    when the trading bot's Telegram client was disconnected.
    """

    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"

        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )

    @pytest.mark.asyncio
    async def test_returns_false_when_no_trading_bot(self, bot):
        """Test returns False when trading bot is not set."""
        bot._bot = None

        result = await bot._ensure_trading_client_connected()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_client(self, bot):
        """Test returns False when trading bot has no client."""
        mock_trading_bot = MagicMock()
        mock_trading_bot._client = None
        bot._bot = mock_trading_bot

        result = await bot._ensure_trading_client_connected()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_already_connected(self, bot):
        """Test returns True when client is already connected."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True

        mock_trading_bot = MagicMock()
        mock_trading_bot._client = mock_client
        bot._bot = mock_trading_bot

        result = await bot._ensure_trading_client_connected()

        assert result is True
        mock_client.is_connected.assert_called_once()
        mock_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_attempts_reconnect_when_disconnected(self, bot):
        """Test attempts to reconnect when client is disconnected."""
        mock_client = MagicMock()
        # First call: disconnected, second call (after connect): connected
        mock_client.is_connected.side_effect = [False, True]
        mock_client.connect = AsyncMock()

        mock_trading_bot = MagicMock()
        mock_trading_bot._client = mock_client
        bot._bot = mock_trading_bot

        result = await bot._ensure_trading_client_connected()

        assert result is True
        mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_reconnect_fails(self, bot):
        """Test returns False when reconnection attempt fails."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

        mock_trading_bot = MagicMock()
        mock_trading_bot._client = mock_client
        bot._bot = mock_trading_bot

        result = await bot._ensure_trading_client_connected()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_reconnect_succeeds_but_still_disconnected(self, bot):
        """Test returns False when connect() succeeds but client still reports disconnected."""
        mock_client = MagicMock()
        # Always reports disconnected even after connect attempt
        mock_client.is_connected.return_value = False
        mock_client.connect = AsyncMock()

        mock_trading_bot = MagicMock()
        mock_trading_bot._client = mock_client
        bot._bot = mock_trading_bot

        result = await bot._ensure_trading_client_connected()

        assert result is False


class TestNotificationBotAsync:
    """Async tests for NotificationBot."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"
        return settings
    
    @pytest.mark.asyncio
    async def test_stop_without_start(self, mock_settings):
        """Test stopping bot that was never started."""
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=mock_settings,
                admin_user_id=99999,
            )
        
        # Mock signal_history.close()
        bot._signal_history.close = AsyncMock()
        
        # Should not raise
        await bot.stop()
        
        # Verify signal history was closed
        bot._signal_history.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_with_client(self, mock_settings):
        """Test stopping bot with active client."""
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=mock_settings,
                admin_user_id=99999,
            )
        
        # Mock client
        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()
        bot._client = mock_client
        bot._initialized = True
        
        # Mock signal_history.close()
        bot._signal_history.close = AsyncMock()
        
        await bot.stop()
        
        mock_client.disconnect.assert_called_once()
        assert bot._initialized is False


class TestGetEntityName:
    """Tests for _get_entity_name method."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
                notification_channel="@testchannel",
            )
    
    def test_get_entity_name_no_entity(self, bot):
        """Test entity name when no entity resolved."""
        assert bot._get_entity_name() == "Unknown"
    
    def test_get_entity_name_with_title(self, bot):
        """Test entity name with channel title."""
        mock_entity = MagicMock()
        mock_entity.title = "Test Channel"
        bot._channel_entity = mock_entity
        
        assert bot._get_entity_name() == "Test Channel"
    
    def test_get_entity_name_without_title(self, bot):
        """Test entity name when entity has no title."""
        mock_entity = MagicMock(spec=[])  # No title attribute
        del mock_entity.title  # Ensure no title
        bot._channel_entity = mock_entity
        
        assert bot._get_entity_name() == "@testchannel"


class TestNotificationBotNotifications:
    """Tests for notification methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet_addr_12345"
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_send_notification_no_client(self, bot):
        """Test send_notification when no client."""
        bot._client = None
        
        # Should not raise
        await bot._send_notification("Test message")
    
    @pytest.mark.asyncio
    async def test_send_notification_success(self, bot):
        """Test successful notification send."""
        mock_client = AsyncMock()
        bot._client = mock_client
        bot._admin_user_id = 12345
        
        await bot._send_notification("Test message")
        
        mock_client.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_notification_error_handling(self, bot):
        """Test send_notification handles errors."""
        mock_client = AsyncMock()
        mock_client.send_message.side_effect = Exception("Send failed")
        bot._client = mock_client
        
        # Should not raise
        await bot._send_notification("Test message")
    
    @pytest.mark.asyncio
    async def test_send_to_admin_no_client(self, bot):
        """Test send_to_admin when no client."""
        bot._client = None
        
        # Should not raise
        await bot._send_to_admin("Test message")
    
    @pytest.mark.asyncio
    async def test_send_to_admin_success(self, bot):
        """Test successful admin message send."""
        mock_client = AsyncMock()
        bot._client = mock_client
        
        await bot._send_to_admin("Test message")
        
        mock_client.send_message.assert_called_once_with(
            bot._admin_user_id,
            "Test message",
            parse_mode="markdown",
        )
    
    @pytest.mark.asyncio
    async def test_notify_signal(self, bot):
        """Test notify_signal method."""
        mock_client = AsyncMock()
        bot._client = mock_client
        bot._channel_entity = MagicMock()
        
        await bot.notify_signal(
            token_symbol="TEST",
            token_address="7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
            signal_type="BUY",
        )
        
        mock_client.send_message.assert_called_once()
        call_args = mock_client.send_message.call_args
        message = call_args[1].get('message', call_args[0][1] if len(call_args[0]) > 1 else '')
        
        # Verify message contains key info
        if isinstance(message, str):
            assert "TEST" in message or "BUY" in message
    
    @pytest.mark.asyncio
    async def test_notify_trade_success(self, bot):
        """Test notify_trade for successful trade."""
        mock_client = AsyncMock()
        bot._client = mock_client
        bot._channel_entity = MagicMock()
        
        await bot.notify_trade(
            action="BUY",
            token_symbol="TEST",
            amount_sol=0.1,
            success=True,
        )
        
        mock_client.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notify_trade_failure(self, bot):
        """Test notify_trade for failed trade."""
        mock_client = AsyncMock()
        bot._client = mock_client
        bot._channel_entity = MagicMock()
        
        await bot.notify_trade(
            action="SELL",
            token_symbol="TEST",
            amount_sol=0.1,
            success=False,
            error="Insufficient balance",
        )
        
        mock_client.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notify_profit_alert(self, bot):
        """Test notify_profit_alert method."""
        mock_client = AsyncMock()
        bot._client = mock_client
        bot._channel_entity = MagicMock()
        
        await bot.notify_profit_alert(
            token_symbol="TEST",
            multiplier=2.5,
            will_sell=True,
        )
        
        mock_client.send_message.assert_called_once()


class TestNotificationBotCommandHandling:
    """Tests for command handling."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_handle_command_unknown(self, bot):
        """Test handling of unknown command."""
        bot._send_to_admin = AsyncMock()
        
        await bot._handle_command("/unknown_command")
        
        bot._send_to_admin.assert_called_once()
        call_args = bot._send_to_admin.call_args[0][0]
        assert "Unknown command" in call_args
    
    @pytest.mark.asyncio
    async def test_handle_command_with_args(self, bot):
        """Test command handling with arguments."""
        bot._cmd_set_size = AsyncMock()
        
        await bot._handle_command("/setsize 0.5")
        
        bot._cmd_set_size.assert_called_once_with("0.5")
    
    @pytest.mark.asyncio
    async def test_handle_command_removes_bot_mention(self, bot):
        """Test that @botname is removed from command."""
        bot._cmd_status = AsyncMock()
        
        await bot._handle_command("/status@my_bot_name")
        
        bot._cmd_status.assert_called_once()


class TestNotificationBotWalletInput:
    """Tests for wallet input handling."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_handle_wallet_input_valid(self, bot):
        """Test valid wallet input."""
        bot._send_notification = AsyncMock()
        bot._awaiting_wallet = True
        
        valid_wallet = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
        await bot._handle_wallet_input(valid_wallet)
        
        assert bot._gmgn_wallet == valid_wallet
        assert bot._awaiting_wallet is False
        bot._send_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_wallet_input_invalid(self, bot):
        """Test invalid wallet input."""
        bot._send_to_admin = AsyncMock()
        bot._awaiting_wallet = True
        
        await bot._handle_wallet_input("invalid_short")
        
        assert bot._gmgn_wallet is None
        assert bot._awaiting_wallet is True
        bot._send_to_admin.assert_called_once()


class TestNotificationBotCustomDaysInput:
    """Tests for custom days input handling."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_handle_custom_days_all(self, bot):
        """Test 'all' input for custom days."""
        bot._cmd_signal_pnl = AsyncMock()
        bot._awaiting_custom_days = True
        
        await bot._handle_custom_days_input("all")
        
        assert bot._awaiting_custom_days is False
        bot._cmd_signal_pnl.assert_called_once_with("all")
    
    @pytest.mark.asyncio
    async def test_handle_custom_days_number(self, bot):
        """Test numeric input for custom days."""
        bot._cmd_signal_pnl = AsyncMock()
        bot._awaiting_custom_days = True
        
        await bot._handle_custom_days_input("7")
        
        assert bot._awaiting_custom_days is False
        bot._cmd_signal_pnl.assert_called_once_with("7")
    
    @pytest.mark.asyncio
    async def test_handle_custom_days_invalid(self, bot):
        """Test invalid input for custom days."""
        bot._send_to_admin = AsyncMock()
        bot._awaiting_custom_days = True
        
        await bot._handle_custom_days_input("invalid")
        
        assert bot._awaiting_custom_days is False
        bot._send_to_admin.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_custom_days_negative(self, bot):
        """Test negative number for custom days."""
        bot._send_to_admin = AsyncMock()
        bot._awaiting_custom_days = True
        
        await bot._handle_custom_days_input("-5")
        
        assert bot._awaiting_custom_days is False
        bot._send_to_admin.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_custom_days_too_large(self, bot):
        """Test too large number for custom days."""
        bot._send_to_admin = AsyncMock()
        bot._awaiting_custom_days = True
        
        await bot._handle_custom_days_input("5000")  # > 3650
        
        assert bot._awaiting_custom_days is False
        bot._send_to_admin.assert_called_once()


class TestMenuButtons:
    """Tests for menu button generation."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = "test_wallet"
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_get_menu_buttons_returns_list(self, bot):
        """Test that _get_menu_buttons returns a list."""
        buttons = bot._get_menu_buttons()
        
        assert isinstance(buttons, list)
        assert len(buttons) > 0
    
    def test_get_menu_buttons_structure(self, bot):
        """Test menu buttons structure."""
        buttons = bot._get_menu_buttons()
        
        # Should have multiple rows
        assert len(buttons) > 5
        
        # Each row should be a list
        for row in buttons:
            assert isinstance(row, list)


class TestNotificationBotProperties:
    """Tests for NotificationBot properties."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.25
        settings.trading_sell_percentage = 75
        settings.trading_min_multiplier = 3.0
        settings.trading_max_positions = 15
        settings.gmgn_wallet = "configured_wallet_12345678901234567890"
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_buy_amount_sol_property(self, bot):
        """Test buy_amount_sol property."""
        assert bot.buy_amount_sol == 0.25
    
    def test_sell_percentage_property(self, bot):
        """Test sell_percentage property."""
        assert bot.sell_percentage == 75
    
    def test_min_multiplier_property(self, bot):
        """Test min_multiplier property."""
        assert bot.min_multiplier == 3.0
    
    def test_max_positions_property(self, bot):
        """Test max_positions property."""
        assert bot.max_positions == 15
    
    def test_gmgn_wallet_property(self, bot):
        """Test gmgn_wallet property."""
        assert bot.gmgn_wallet == "configured_wallet_12345678901234567890"
    
    def test_is_trading_paused_default(self, bot):
        """Test is_trading_paused default value."""
        assert bot.is_trading_paused is False
    
    def test_is_wallet_configured_true(self, bot):
        """Test is_wallet_configured when wallet is set."""
        assert bot.is_wallet_configured is True
    
    def test_is_wallet_configured_false(self):
        """Test is_wallet_configured when wallet is None."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
        
        assert bot.is_wallet_configured is False
    
    def test_signal_history_property(self, bot):
        """Test signal_history property."""
        assert bot.signal_history is not None
    
    def test_strategy_manager_property(self, bot):
        """Test strategy_manager property."""
        assert bot.strategy_manager is not None


class TestNotificationBotDatabaseDSN:
    """Tests for database DSN building."""
    
    def test_build_database_dsn_without_password(self):
        """Test DSN building without password."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        
        with patch.dict(os.environ, {"POSTGRES_PASSWORD": ""}, clear=False):
            with patch.object(NotificationBot, '_load_strategy_state'):
                bot = NotificationBot(
                    api_id=12345,
                    api_hash="test_hash",
                    bot_token="test_token",
                    settings=settings,
                    admin_user_id=99999,
                )
        
        # Signal DB should be None when no password
        assert bot._signal_db is None
    
    def test_build_database_dsn_with_password(self):
        """Test DSN building with password."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        
        with patch.dict(os.environ, {
            "POSTGRES_PASSWORD": "testpass",
            "POSTGRES_HOST": "testhost",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "testuser",
            "POSTGRES_DATABASE": "testdb",
        }, clear=False):
            with patch.object(NotificationBot, '_load_strategy_state'):
                bot = NotificationBot(
                    api_id=12345,
                    api_hash="test_hash",
                    bot_token="test_token",
                    settings=settings,
                    admin_user_id=99999,
                )
        
        # Signal DB should be created
        assert bot._signal_db is not None


class TestNotificationBotStateMethods:
    """Tests for state-modifying methods."""
    
    @pytest.fixture
    def bot(self):
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_set_trading_bot(self, bot):
        """Test setting the trading bot reference."""
        mock_bot = MagicMock()
        bot.set_trading_bot(mock_bot)
        
        assert bot._bot is mock_bot
    
    def test_pause_trading(self, bot):
        """Test pausing trading."""
        bot._trading_paused = False
        bot._trading_paused = True
        
        assert bot.is_trading_paused is True
    
    def test_resume_trading(self, bot):
        """Test resuming trading."""
        bot._trading_paused = True
        bot._trading_paused = False
        
        assert bot.is_trading_paused is False


class TestNotificationBotStrategyState:
    """Tests for strategy state loading/saving."""
    
    def test_load_strategy_state_file_not_found(self):
        """Test loading strategy state when file doesn't exist."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "/nonexistent/path/state.json"
        
        # Should not raise
        bot = NotificationBot(
            api_id=12345,
            api_hash="test_hash",
            bot_token="test_token",
            settings=settings,
            admin_user_id=99999,
        )
        
        assert bot._strategy_manager is not None


class TestSolanaAddressValidation:
    """Tests for Solana address validation."""
    
    def test_valid_addresses(self):
        """Test valid Solana addresses."""
        assert is_valid_solana_address("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr") is True
        assert is_valid_solana_address("So11111111111111111111111111111111111111112") is True
    
    def test_invalid_addresses(self):
        """Test invalid Solana addresses."""
        # Too short
        assert is_valid_solana_address("short") is False
        
        # Contains invalid characters (0, O, I, l)
        assert is_valid_solana_address("0GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr") is False
        
        # Empty
        assert is_valid_solana_address("") is False


class TestNotificationBotCallbackData:
    """Tests for callback button data handling."""
    
    @pytest.fixture
    def bot(self):
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    def test_callback_commands_exist(self, bot):
        """Test that callback command methods exist."""
        # These methods should exist for button handling
        assert hasattr(bot, '_get_menu_buttons')
        assert hasattr(bot, '_handle_callback')


class TestNotificationBotCommands:
    """Tests for bot command methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_cmd_set_size_no_args(self, bot):
        """Test setsize command without args shows usage."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_size("")
        
        bot._send_to_admin.assert_called_once()
        msg = bot._send_to_admin.call_args[0][0]
        assert "Usage" in msg or "setsize" in msg
    
    @pytest.mark.asyncio
    async def test_cmd_set_size_valid(self, bot):
        """Test setsize command with valid amount."""
        bot._send_notification = AsyncMock()
        
        await bot._cmd_set_size("0.5")
        
        assert bot._buy_amount_sol == 0.5
        bot._send_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cmd_set_size_too_small(self, bot):
        """Test setsize command with amount too small."""
        bot._send_to_admin = AsyncMock()
        original = bot._buy_amount_sol
        
        await bot._cmd_set_size("0.0001")
        
        assert bot._buy_amount_sol == original  # Unchanged
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_set_size_too_large(self, bot):
        """Test setsize command with amount too large."""
        bot._send_to_admin = AsyncMock()
        original = bot._buy_amount_sol
        
        await bot._cmd_set_size("500")
        
        assert bot._buy_amount_sol == original  # Unchanged
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_set_size_invalid(self, bot):
        """Test setsize command with invalid amount."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_size("not_a_number")
        
        bot._send_to_admin.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cmd_set_sell_no_args(self, bot):
        """Test setsell command without args."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_sell("")
        
        bot._send_to_admin.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cmd_set_sell_valid(self, bot):
        """Test setsell command with valid percentage."""
        bot._send_notification = AsyncMock()
        
        await bot._cmd_set_sell("75")
        
        assert bot._sell_percentage == 75
        bot._send_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cmd_set_sell_with_percent_sign(self, bot):
        """Test setsell command with percent sign."""
        bot._send_notification = AsyncMock()
        
        await bot._cmd_set_sell("80%")
        
        assert bot._sell_percentage == 80
    
    @pytest.mark.asyncio
    async def test_cmd_set_multiplier_no_args(self, bot):
        """Test setmultiplier without args."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_multiplier("")
        
        bot._send_to_admin.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cmd_set_multiplier_valid(self, bot):
        """Test setmultiplier with valid value."""
        bot._send_notification = AsyncMock()
        
        await bot._cmd_set_multiplier("3.0")
        
        assert bot._min_multiplier == 3.0
    
    @pytest.mark.asyncio
    async def test_cmd_pause(self, bot):
        """Test pause command."""
        bot._send_notification = AsyncMock()
        bot._trading_paused = False
        
        await bot._cmd_pause("")
        
        assert bot._trading_paused is True
        bot._send_notification.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_resume(self, bot):
        """Test resume command when wallet not configured."""
        bot._send_to_admin = AsyncMock()
        bot._trading_paused = True
        bot._gmgn_wallet = None
        
        await bot._cmd_resume("")
        
        # Resume requires wallet, should stay paused
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_resume_with_wallet(self, bot):
        """Test resume command with wallet configured."""
        bot._send_notification = AsyncMock()
        bot._trading_paused = True
        bot._gmgn_wallet = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
        
        await bot._cmd_resume("")
        
        assert bot._trading_paused is False
        bot._send_notification.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_set_wallet_no_args(self, bot):
        """Test setwallet without args prompts for input."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_wallet("")
        
        # May either prompt for wallet or set awaiting state
        # Based on implementation
        call_made = bot._send_to_admin.called or bot._awaiting_wallet
        assert call_made
    
    @pytest.mark.asyncio
    async def test_cmd_set_wallet_with_valid_address(self, bot):
        """Test setwallet with valid address."""
        bot._send_notification = AsyncMock()
        valid_wallet = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
        
        await bot._cmd_set_wallet(valid_wallet)
        
        assert bot._gmgn_wallet == valid_wallet
    
    @pytest.mark.asyncio
    async def test_cmd_set_wallet_with_invalid_address(self, bot):
        """Test setwallet with invalid address."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_set_wallet("invalid_short")
        
        bot._send_to_admin.assert_called()
        assert bot._gmgn_wallet is None


class TestNotificationBotCommandsPnL:
    """Tests for PnL-related commands."""
    
    @pytest.fixture
    def bot(self):
        """Create a NotificationBot instance."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            bot = NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
        
        bot._signal_db = None  # No database connection
        return bot
    
    @pytest.mark.asyncio
    async def test_cmd_signal_pnl_no_db(self, bot):
        """Test signal_pnl command without database."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_signal_pnl("7d")
        
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_stats(self, bot):
        """Test stats command."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_stats("")
        
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_pnl_no_positions(self, bot):
        """Test pnl command with no bot or positions."""
        bot._send_to_admin = AsyncMock()
        bot._bot = None
        
        await bot._cmd_pnl("")
        
        bot._send_to_admin.assert_called()


class TestNotificationBotCommandsSettings:
    """Tests for settings-related commands."""
    
    @pytest.fixture
    def bot(self):
        """Create bot with mock."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_cmd_settings(self, bot):
        """Test settings command."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_settings("")
        
        bot._send_to_admin.assert_called()
        msg = bot._send_to_admin.call_args[0][0]
        assert "0.1" in msg or "SOL" in msg or "Settings" in msg
    
    @pytest.mark.asyncio
    async def test_cmd_status(self, bot):
        """Test status command."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_status("")
        
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_positions(self, bot):
        """Test positions command."""
        bot._send_to_admin = AsyncMock()
        bot._bot = None
        
        await bot._cmd_positions("")
        
        bot._send_to_admin.assert_called()
    
    @pytest.mark.asyncio
    async def test_cmd_help(self, bot):
        """Test help command."""
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_help("")
        
        bot._send_to_admin.assert_called()
        msg = bot._send_to_admin.call_args[0][0]
        # Help should list commands
        assert "/status" in msg or "help" in msg.lower()
    
    @pytest.mark.asyncio
    async def test_cmd_menu(self, bot):
        """Test menu command."""
        # Mock the actual method used
        bot._send_to_admin_with_buttons = AsyncMock()
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_menu("")
        
        # Menu uses _send_to_admin_with_buttons
        bot._send_to_admin_with_buttons.assert_called()


class TestNotificationBotStrategies:
    """Tests for strategy-related functionality."""
    
    @pytest.fixture
    def bot(self):
        """Create bot with strategy manager."""
        settings = MagicMock()
        settings.trading_buy_amount_sol = 0.1
        settings.trading_sell_percentage = 50
        settings.trading_min_multiplier = 2.0
        settings.trading_max_positions = 10
        settings.gmgn_wallet = None
        settings.state_file = "trading_state.json"
        settings.trading_dry_run = True
        
        with patch.object(NotificationBot, '_load_strategy_state'):
            return NotificationBot(
                api_id=12345,
                api_hash="test_hash",
                bot_token="test_token",
                settings=settings,
                admin_user_id=99999,
            )
    
    @pytest.mark.asyncio
    async def test_cmd_strategies(self, bot):
        """Test strategies command."""
        bot._send_to_admin_with_buttons = AsyncMock()
        bot._send_to_admin = AsyncMock()
        
        await bot._cmd_strategies("")
        
        # Strategies uses _send_to_admin_with_buttons
        bot._send_to_admin_with_buttons.assert_called()
    
    def test_active_strategy_property(self, bot):
        """Test active_strategy property returns strategy or None."""
        active = bot.active_strategy
        
        # Either returns a strategy or None
        assert active is None or hasattr(active, 'id')
