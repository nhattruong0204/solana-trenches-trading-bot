"""
Custom exceptions for the trading bot.

Defines a hierarchy of exceptions for different error scenarios,
enabling precise error handling throughout the application.
"""

from __future__ import annotations

from typing import Optional


class TradingBotError(Exception):
    """Base exception for all trading bot errors."""
    
    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause
    
    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


# ==============================================================================
# Configuration Errors
# ==============================================================================

class ConfigurationError(TradingBotError):
    """Raised when configuration is invalid or missing."""
    pass


class MissingEnvironmentVariableError(ConfigurationError):
    """Raised when a required environment variable is missing."""
    
    def __init__(self, variable_name: str) -> None:
        super().__init__(f"Missing required environment variable: {variable_name}")
        self.variable_name = variable_name


# ==============================================================================
# Telegram Errors
# ==============================================================================

class TelegramError(TradingBotError):
    """Base exception for Telegram-related errors."""
    pass


class TelegramConnectionError(TelegramError):
    """Raised when connection to Telegram fails."""
    pass


class TelegramAuthenticationError(TelegramError):
    """Raised when Telegram authentication fails."""
    pass


class ChannelNotFoundError(TelegramError):
    """Raised when the signal channel cannot be found."""
    
    def __init__(self, channel_username: str) -> None:
        super().__init__(f"Channel not found: @{channel_username}")
        self.channel_username = channel_username


class BotNotFoundError(TelegramError):
    """Raised when the GMGN bot cannot be found."""
    
    def __init__(self, bot_username: str) -> None:
        super().__init__(f"Bot not found: @{bot_username}")
        self.bot_username = bot_username


# ==============================================================================
# Trading Errors
# ==============================================================================

class TradingError(TradingBotError):
    """Base exception for trading-related errors."""
    pass


class TradingDisabledError(TradingError):
    """Raised when attempting to trade while trading is disabled."""
    
    def __init__(self) -> None:
        super().__init__("Trading is currently disabled")


class MaxPositionsReachedError(TradingError):
    """Raised when maximum open positions limit is reached."""
    
    def __init__(self, max_positions: int, current_positions: int) -> None:
        super().__init__(
            f"Maximum positions limit reached: {current_positions}/{max_positions}"
        )
        self.max_positions = max_positions
        self.current_positions = current_positions


class DuplicatePositionError(TradingError):
    """Raised when attempting to open a duplicate position."""
    
    def __init__(self, token_address: str, token_symbol: str) -> None:
        super().__init__(f"Position already exists for {token_symbol} ({token_address[:12]}...)")
        self.token_address = token_address
        self.token_symbol = token_symbol


class PositionNotFoundError(TradingError):
    """Raised when a position cannot be found."""
    
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Position not found: {identifier}")
        self.identifier = identifier


class TradeExecutionError(TradingError):
    """Raised when trade execution fails."""
    
    def __init__(
        self,
        action: str,
        token_address: str,
        token_symbol: str,
        cause: Optional[Exception] = None
    ) -> None:
        super().__init__(
            f"Failed to execute {action} for {token_symbol} ({token_address[:12]}...)",
            cause=cause
        )
        self.action = action
        self.token_address = token_address
        self.token_symbol = token_symbol


# ==============================================================================
# Parser Errors
# ==============================================================================

class ParserError(TradingBotError):
    """Base exception for message parsing errors."""
    pass


class InvalidSignalFormatError(ParserError):
    """Raised when a signal message has invalid format."""
    
    def __init__(self, message_preview: str) -> None:
        # Truncate message for readability
        preview = message_preview[:100] + "..." if len(message_preview) > 100 else message_preview
        super().__init__(f"Invalid signal format: {preview}")


class TokenAddressExtractionError(ParserError):
    """Raised when token address cannot be extracted from message."""
    pass


# ==============================================================================
# State Management Errors
# ==============================================================================

class StateError(TradingBotError):
    """Base exception for state management errors."""
    pass


class StatePersistenceError(StateError):
    """Raised when state cannot be saved or loaded."""
    
    def __init__(self, operation: str, filepath: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"Failed to {operation} state from {filepath}", cause=cause)
        self.operation = operation
        self.filepath = filepath


class StateCorruptionError(StateError):
    """Raised when state file is corrupted."""
    
    def __init__(self, filepath: str, cause: Optional[Exception] = None) -> None:
        super().__init__(f"State file is corrupted: {filepath}", cause=cause)
        self.filepath = filepath
