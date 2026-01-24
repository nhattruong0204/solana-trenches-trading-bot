"""
Tests for the exceptions module.
"""

import pytest

from src.exceptions import (
    TradingBotError,
    ConfigurationError,
    MissingEnvironmentVariableError,
    TelegramError,
    TelegramConnectionError,
    TelegramAuthenticationError,
    ChannelNotFoundError,
    BotNotFoundError,
    TradingError,
    TradingDisabledError,
    MaxPositionsReachedError,
    DuplicatePositionError,
    PositionNotFoundError,
    TradeExecutionError,
    ParserError,
    InvalidSignalFormatError,
    TokenAddressExtractionError,
    StateError,
    StatePersistenceError,
    StateCorruptionError,
)


class TestTradingBotError:
    """Tests for base TradingBotError."""
    
    def test_create_error_with_message(self):
        """Test creating error with message only."""
        error = TradingBotError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.cause is None
    
    def test_create_error_with_cause(self):
        """Test creating error with cause."""
        cause = ValueError("Original error")
        error = TradingBotError("Test error", cause=cause)
        
        assert "Test error" in str(error)
        assert "Original error" in str(error)
        assert error.cause is cause
    
    def test_is_exception(self):
        """Test that TradingBotError is an Exception."""
        error = TradingBotError("Test")
        assert isinstance(error, Exception)


class TestConfigurationErrors:
    """Tests for configuration-related exceptions."""
    
    def test_configuration_error(self):
        """Test ConfigurationError."""
        error = ConfigurationError("Invalid config")
        assert isinstance(error, TradingBotError)
        assert "Invalid config" in str(error)
    
    def test_missing_environment_variable_error(self):
        """Test MissingEnvironmentVariableError."""
        error = MissingEnvironmentVariableError("API_KEY")
        
        assert isinstance(error, ConfigurationError)
        assert "API_KEY" in str(error)
        assert error.variable_name == "API_KEY"


class TestTelegramErrors:
    """Tests for Telegram-related exceptions."""
    
    def test_telegram_error_base(self):
        """Test TelegramError base class."""
        error = TelegramError("Telegram failed")
        assert isinstance(error, TradingBotError)
    
    def test_telegram_connection_error(self):
        """Test TelegramConnectionError."""
        error = TelegramConnectionError("Connection refused")
        assert isinstance(error, TelegramError)
    
    def test_telegram_authentication_error(self):
        """Test TelegramAuthenticationError."""
        error = TelegramAuthenticationError("Invalid API key")
        assert isinstance(error, TelegramError)
    
    def test_channel_not_found_error(self):
        """Test ChannelNotFoundError."""
        error = ChannelNotFoundError("test_channel")
        
        assert isinstance(error, TelegramError)
        assert "test_channel" in str(error)
        assert error.channel_username == "test_channel"
    
    def test_bot_not_found_error(self):
        """Test BotNotFoundError."""
        error = BotNotFoundError("gmgn_bot")
        
        assert isinstance(error, TelegramError)
        assert "gmgn_bot" in str(error)
        assert error.bot_username == "gmgn_bot"


class TestTradingErrors:
    """Tests for trading-related exceptions."""
    
    def test_trading_error_base(self):
        """Test TradingError base class."""
        error = TradingError("Trade failed")
        assert isinstance(error, TradingBotError)
    
    def test_trading_disabled_error(self):
        """Test TradingDisabledError."""
        error = TradingDisabledError()
        
        assert isinstance(error, TradingError)
        assert "disabled" in str(error).lower()
    
    def test_max_positions_reached_error(self):
        """Test MaxPositionsReachedError."""
        error = MaxPositionsReachedError(max_positions=10, current_positions=10)
        
        assert isinstance(error, TradingError)
        assert "10" in str(error)
        assert error.max_positions == 10
        assert error.current_positions == 10
    
    def test_duplicate_position_error(self):
        """Test DuplicatePositionError."""
        error = DuplicatePositionError(
            token_address="7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
            token_symbol="TEST",
        )
        
        assert isinstance(error, TradingError)
        assert "TEST" in str(error)
        assert error.token_symbol == "TEST"
        assert error.token_address == "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
    
    def test_position_not_found_error(self):
        """Test PositionNotFoundError."""
        error = PositionNotFoundError("token123")
        
        assert isinstance(error, TradingError)
        assert "token123" in str(error)
        assert error.identifier == "token123"
    
    def test_trade_execution_error(self):
        """Test TradeExecutionError."""
        cause = ConnectionError("Network down")
        error = TradeExecutionError(
            action="BUY",
            token_address="7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
            token_symbol="TEST",
            cause=cause,
        )
        
        assert isinstance(error, TradingError)
        assert "BUY" in str(error)
        assert "TEST" in str(error)
        assert error.action == "BUY"
        assert error.token_symbol == "TEST"
        assert error.cause is cause


class TestParserErrors:
    """Tests for parser-related exceptions."""
    
    def test_parser_error_base(self):
        """Test ParserError base class."""
        error = ParserError("Parse failed")
        assert isinstance(error, TradingBotError)
    
    def test_invalid_signal_format_error(self):
        """Test InvalidSignalFormatError."""
        error = InvalidSignalFormatError("Some invalid message text")
        
        assert isinstance(error, ParserError)
        assert "invalid" in str(error).lower() or "Invalid" in str(error)
    
    def test_invalid_signal_format_error_truncates_long_messages(self):
        """Test that long messages are truncated."""
        long_message = "x" * 200
        error = InvalidSignalFormatError(long_message)
        
        # Should truncate to ~100 chars + "..."
        assert len(str(error)) < 250
        assert "..." in str(error)
    
    def test_token_address_extraction_error(self):
        """Test TokenAddressExtractionError."""
        error = TokenAddressExtractionError("Could not find address")
        assert isinstance(error, ParserError)


class TestStateErrors:
    """Tests for state management exceptions."""
    
    def test_state_error_base(self):
        """Test StateError base class."""
        error = StateError("State error")
        assert isinstance(error, TradingBotError)
    
    def test_state_persistence_error(self):
        """Test StatePersistenceError."""
        cause = IOError("File not writable")
        error = StatePersistenceError(
            operation="save",
            filepath="/path/to/state.json",
            cause=cause,
        )
        
        assert isinstance(error, StateError)
        assert "save" in str(error)
        assert "/path/to/state.json" in str(error)
        assert error.operation == "save"
        assert error.filepath == "/path/to/state.json"
        assert error.cause is cause
    
    def test_state_corruption_error(self):
        """Test StateCorruptionError."""
        cause = ValueError("Invalid JSON")
        error = StateCorruptionError(
            filepath="/path/to/corrupt.json",
            cause=cause,
        )
        
        assert isinstance(error, StateError)
        assert "corrupt" in str(error).lower()
        assert error.filepath == "/path/to/corrupt.json"
        assert error.cause is cause


class TestExceptionHierarchy:
    """Tests for exception inheritance hierarchy."""
    
    def test_all_inherit_from_base(self):
        """Test all exceptions inherit from TradingBotError."""
        exceptions = [
            ConfigurationError("test"),
            MissingEnvironmentVariableError("VAR"),
            TelegramError("test"),
            TelegramConnectionError("test"),
            TelegramAuthenticationError("test"),
            ChannelNotFoundError("channel"),
            BotNotFoundError("bot"),
            TradingError("test"),
            TradingDisabledError(),
            MaxPositionsReachedError(10, 10),
            DuplicatePositionError("addr", "SYM"),
            PositionNotFoundError("id"),
            TradeExecutionError("BUY", "addr", "SYM"),
            ParserError("test"),
            InvalidSignalFormatError("msg"),
            TokenAddressExtractionError("test"),
            StateError("test"),
            StatePersistenceError("save", "path"),
            StateCorruptionError("path"),
        ]
        
        for exc in exceptions:
            assert isinstance(exc, TradingBotError), f"{type(exc).__name__} should inherit from TradingBotError"
    
    def test_can_catch_by_category(self):
        """Test exceptions can be caught by category."""
        # Should be catchable as TelegramError
        try:
            raise ChannelNotFoundError("test")
        except TelegramError:
            pass  # Expected
        
        # Should be catchable as TradingError
        try:
            raise MaxPositionsReachedError(10, 10)
        except TradingError:
            pass  # Expected
        
        # Should be catchable as base
        try:
            raise StatePersistenceError("load", "file.json")
        except TradingBotError:
            pass  # Expected
