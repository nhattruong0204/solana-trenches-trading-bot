"""
Message parsers for extracting trading signals.

This module contains parsers for different types of signals
from the Telegram channel, with robust error handling and validation.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TypeVar, Generic, Dict, List

from src.constants import (
    BUY_SIGNAL_INDICATORS,
    MULTIPLIER_PATTERN,
    PROFIT_ALERT_INDICATORS,
    TOKEN_ADDRESS_PATTERN,
    TOKEN_SYMBOL_PATTERN,
    MAIN_BUY_SIGNAL_INDICATORS,
    MAIN_PROFIT_ALERT_INDICATORS,
    CHANNEL_VOLSM,
    CHANNEL_MAIN,
)
from src.models import BuySignal, ProfitAlert

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SignalParser(ABC, Generic[T]):
    """Abstract base class for signal parsers."""
    
    @abstractmethod
    def parse(self, message_id: int, text: str, reply_to_msg_id: Optional[int] = None) -> Optional[T]:
        """
        Parse a message and extract signal data.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of message being replied to (if any)
            
        Returns:
            Parsed signal object or None if not a valid signal
        """
        pass
    
    @abstractmethod
    def can_parse(self, text: str) -> bool:
        """
        Check if this parser can handle the given message.
        
        Args:
            text: Message text content
            
        Returns:
            True if this parser should attempt to parse the message
        """
        pass


class BuySignalParser(SignalParser[BuySignal]):
    """
    Parser for buy signals from the trenches channel.
    
    Detects messages containing "VOLUME + SM APE SIGNAL DETECTED"
    and extracts token symbol and address.
    """
    
    def __init__(self) -> None:
        self._symbol_pattern = re.compile(TOKEN_SYMBOL_PATTERN, re.IGNORECASE)
        self._address_pattern = re.compile(TOKEN_ADDRESS_PATTERN)
    
    def can_parse(self, text: str) -> bool:
        """Check if message contains buy signal indicators."""
        return any(indicator in text for indicator in BUY_SIGNAL_INDICATORS)
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> Optional[BuySignal]:
        """
        Parse a buy signal message.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: Not used for buy signals
            
        Returns:
            BuySignal if valid, None otherwise
        """
        if not self.can_parse(text):
            return None
        
        # Extract token symbol
        symbol_match = self._symbol_pattern.search(text)
        symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
        
        # Extract token address
        address_match = self._address_pattern.search(text)
        if not address_match:
            logger.warning(f"Buy signal detected but no address found in message {message_id}")
            return None
        
        address = address_match.group(1)
        
        # Validate address format (basic Solana address validation)
        if not self._is_valid_solana_address(address):
            logger.warning(f"Invalid Solana address format: {address}")
            return None
        
        return BuySignal(
            message_id=message_id,
            token_symbol=symbol.upper(),
            token_address=address,
            timestamp=datetime.now(timezone.utc),
            raw_text=text,
        )
    
    @staticmethod
    def _is_valid_solana_address(address: str) -> bool:
        """
        Validate Solana address format.
        
        Args:
            address: Potential Solana address
            
        Returns:
            True if address appears valid
        """
        # Solana addresses are base58 encoded, 32-44 characters
        if not 32 <= len(address) <= 44:
            return False
        
        # Check for valid base58 characters (no 0, O, I, l)
        invalid_chars = set("0OIl")
        return not any(c in invalid_chars for c in address)


class ProfitAlertParser(SignalParser[ProfitAlert]):
    """
    Parser for profit alerts from the trenches channel.
    
    Detects messages containing "PROFIT ALERT" and extracts
    the multiplier value and reference to the original signal.
    """
    
    def __init__(self) -> None:
        self._multiplier_pattern = re.compile(MULTIPLIER_PATTERN, re.IGNORECASE)
    
    def can_parse(self, text: str) -> bool:
        """Check if message contains profit alert indicators."""
        return any(indicator in text for indicator in PROFIT_ALERT_INDICATORS)
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> Optional[ProfitAlert]:
        """
        Parse a profit alert message.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of the original signal message (required)
            
        Returns:
            ProfitAlert if valid, None otherwise
        """
        if not self.can_parse(text):
            return None
        
        # Profit alerts must reference an original signal
        if reply_to_msg_id is None:
            logger.debug(f"Profit alert in message {message_id} has no reply reference")
            return None
        
        # Extract multiplier
        multiplier_match = self._multiplier_pattern.search(text)
        if not multiplier_match:
            logger.warning(f"Profit alert detected but no multiplier found in message {message_id}")
            return None
        
        try:
            multiplier = float(multiplier_match.group(1))
        except ValueError:
            logger.warning(f"Invalid multiplier format in message {message_id}")
            return None
        
        # Validate multiplier value
        if multiplier <= 0 or multiplier > 1000:
            logger.warning(f"Unrealistic multiplier value: {multiplier}")
            return None
        
        return ProfitAlert(
            message_id=message_id,
            reply_to_msg_id=reply_to_msg_id,
            multiplier=multiplier,
            timestamp=datetime.now(timezone.utc),
        )


@dataclass
class ParseResult:
    """Result container for message parsing."""
    
    buy_signal: Optional[BuySignal] = None
    profit_alert: Optional[ProfitAlert] = None
    
    @property
    def has_signal(self) -> bool:
        """Check if any signal was parsed."""
        return self.buy_signal is not None or self.profit_alert is not None


# =============================================================================
# MAIN Channel Parsers
# =============================================================================


class MainChannelBuySignalParser(SignalParser[BuySignal]):
    """
    Parser for buy signals from the MAIN trenches channel.
    
    The MAIN channel has a different format than VOLSM.
    Detects two types of signals:
    - "🚀 NEW-LAUNCH SIGNAL" - New token launch signals
    - "// MID-SIZED SIGNAL DETECTED" - Smart money mid-sized signals
    
    Both are treated as "ape" signals for tracking purposes.
    """
    
    def __init__(self) -> None:
        self._symbol_pattern = re.compile(TOKEN_SYMBOL_PATTERN, re.IGNORECASE)
        self._address_pattern = re.compile(TOKEN_ADDRESS_PATTERN)
    
    def can_parse(self, text: str) -> bool:
        """Check if message contains MAIN channel buy signal indicators."""
        return any(indicator in text for indicator in MAIN_BUY_SIGNAL_INDICATORS)
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> Optional[BuySignal]:
        """
        Parse a buy signal message from MAIN channel.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: Not used for buy signals
            
        Returns:
            BuySignal if valid, None otherwise
        """
        if not self.can_parse(text):
            return None
        
        # Extract token symbol
        symbol_match = self._symbol_pattern.search(text)
        symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
        
        # Extract token address
        address_match = self._address_pattern.search(text)
        if not address_match:
            logger.warning(f"[MAIN] Buy signal detected but no address found in message {message_id}")
            return None
        
        address = address_match.group(1)
        
        # Validate address format
        if not self._is_valid_solana_address(address):
            logger.warning(f"[MAIN] Invalid Solana address format: {address}")
            return None
        
        return BuySignal(
            message_id=message_id,
            token_symbol=symbol.upper(),
            token_address=address,
            timestamp=datetime.now(timezone.utc),
            raw_text=text,
        )
    
    @staticmethod
    def _is_valid_solana_address(address: str) -> bool:
        """Validate Solana address format."""
        if not 32 <= len(address) <= 44:
            return False
        invalid_chars = set("0OIl")
        return not any(c in invalid_chars for c in address)


class MainChannelProfitAlertParser(SignalParser[ProfitAlert]):
    """
    Parser for profit alerts from the MAIN trenches channel.
    
    The MAIN channel has a different format than VOLSM.
    Detects messages containing "PROFIT ALERT 🚀" pattern.
    """
    
    def __init__(self) -> None:
        self._multiplier_pattern = re.compile(MULTIPLIER_PATTERN, re.IGNORECASE)
    
    def can_parse(self, text: str) -> bool:
        """Check if message contains MAIN channel profit alert indicators."""
        return any(indicator in text for indicator in MAIN_PROFIT_ALERT_INDICATORS)
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> Optional[ProfitAlert]:
        """
        Parse a profit alert message from MAIN channel.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of the original signal message (required)
            
        Returns:
            ProfitAlert if valid, None otherwise
        """
        if not self.can_parse(text):
            return None
        
        if reply_to_msg_id is None:
            logger.debug(f"[MAIN] Profit alert in message {message_id} has no reply reference")
            return None
        
        multiplier_match = self._multiplier_pattern.search(text)
        if not multiplier_match:
            logger.warning(f"[MAIN] Profit alert detected but no multiplier found in message {message_id}")
            return None
        
        try:
            multiplier = float(multiplier_match.group(1))
        except ValueError:
            logger.warning(f"[MAIN] Invalid multiplier format in message {message_id}")
            return None
        
        if multiplier <= 0 or multiplier > 1000:
            logger.warning(f"[MAIN] Unrealistic multiplier value: {multiplier}")
            return None
        
        return ProfitAlert(
            message_id=message_id,
            reply_to_msg_id=reply_to_msg_id,
            multiplier=multiplier,
            timestamp=datetime.now(timezone.utc),
        )


# =============================================================================
# Parser Registry - Multi-Channel Support
# =============================================================================


@dataclass
class ChannelParsers:
    """Container for a channel's parsers."""
    buy_parser: SignalParser[BuySignal]
    profit_parser: SignalParser[ProfitAlert]


class ParserRegistry:
    """
    Registry mapping channel IDs to their specific parsers.
    
    Each channel can have different message formats, so we use
    channel-specific parsers to handle the variations.
    """
    
    def __init__(self) -> None:
        self._parsers: Dict[str, ChannelParsers] = {
            CHANNEL_VOLSM: ChannelParsers(
                buy_parser=BuySignalParser(),
                profit_parser=ProfitAlertParser(),
            ),
            CHANNEL_MAIN: ChannelParsers(
                buy_parser=MainChannelBuySignalParser(),
                profit_parser=MainChannelProfitAlertParser(),
            ),
        }
        # Default parsers for unknown channels (fallback to VOLSM)
        self._default_parsers = self._parsers[CHANNEL_VOLSM]
    
    def get_parsers(self, channel_id: str) -> ChannelParsers:
        """
        Get parsers for a specific channel.
        
        Args:
            channel_id: Channel identifier (e.g., 'volsm', 'main')
            
        Returns:
            ChannelParsers for the channel, or default if unknown
        """
        return self._parsers.get(channel_id, self._default_parsers)
    
    def get_buy_parser(self, channel_id: str) -> SignalParser[BuySignal]:
        """Get the buy signal parser for a channel."""
        return self.get_parsers(channel_id).buy_parser
    
    def get_profit_parser(self, channel_id: str) -> SignalParser[ProfitAlert]:
        """Get the profit alert parser for a channel."""
        return self.get_parsers(channel_id).profit_parser
    
    def supported_channels(self) -> List[str]:
        """Get list of supported channel IDs."""
        return list(self._parsers.keys())


class ChannelMessageParser:
    """
    Channel-aware message parser.
    
    Unlike MessageParser, this parser knows which channel a message
    came from and uses the appropriate parser for that channel.
    """
    
    def __init__(self, channel_id: str = CHANNEL_VOLSM) -> None:
        """
        Initialize parser for a specific channel.
        
        Args:
            channel_id: Channel identifier (default: volsm)
        """
        self._channel_id = channel_id
        self._registry = ParserRegistry()
        parsers = self._registry.get_parsers(channel_id)
        self._buy_parser = parsers.buy_parser
        self._profit_parser = parsers.profit_parser
    
    @property
    def channel_id(self) -> str:
        """Get the channel ID this parser is configured for."""
        return self._channel_id
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> ParseResult:
        """
        Parse a message using channel-specific parsers.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of message being replied to (if any)
            
        Returns:
            ParseResult containing any extracted signals
        """
        result = ParseResult()
        
        if self._buy_parser.can_parse(text):
            result.buy_signal = self._buy_parser.parse(message_id, text, reply_to_msg_id)
        
        if self._profit_parser.can_parse(text):
            result.profit_alert = self._profit_parser.parse(message_id, text, reply_to_msg_id)
        
        return result
    
    def parse_buy_signal(
        self,
        message_id: int,
        text: str
    ) -> Optional[BuySignal]:
        """Parse a message specifically for buy signals."""
        return self._buy_parser.parse(message_id, text)
    
    def parse_profit_alert(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int]
    ) -> Optional[ProfitAlert]:
        """Parse a message specifically for profit alerts."""
        return self._profit_parser.parse(message_id, text, reply_to_msg_id)


class MessageParser:
    """
    Unified message parser that delegates to specialized parsers.
    
    This class orchestrates parsing of channel messages and determines
    the appropriate parser based on message content.
    
    Note: For multi-channel support, prefer using ChannelMessageParser
    or ParserRegistry directly.
    """
    
    def __init__(self, channel_id: str = CHANNEL_VOLSM) -> None:
        """
        Initialize parser.
        
        Args:
            channel_id: Optional channel identifier for channel-specific parsing.
                       Defaults to VOLSM for backward compatibility.
        """
        self._channel_id = channel_id
        registry = ParserRegistry()
        parsers = registry.get_parsers(channel_id)
        self._buy_parser = parsers.buy_parser
        self._profit_parser = parsers.profit_parser
    
    @property
    def channel_id(self) -> str:
        """Get the channel ID this parser is configured for."""
        return self._channel_id
    
    def parse(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int] = None
    ) -> ParseResult:
        """
        Parse a message and extract any trading signals.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of message being replied to (if any)
            
        Returns:
            ParseResult containing any extracted signals
        """
        result = ParseResult()
        
        # Try to parse as buy signal
        if self._buy_parser.can_parse(text):
            result.buy_signal = self._buy_parser.parse(message_id, text, reply_to_msg_id)
        
        # Try to parse as profit alert
        if self._profit_parser.can_parse(text):
            result.profit_alert = self._profit_parser.parse(message_id, text, reply_to_msg_id)
        
        return result
    
    def parse_buy_signal(
        self,
        message_id: int,
        text: str
    ) -> Optional[BuySignal]:
        """
        Parse a message specifically for buy signals.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            
        Returns:
            BuySignal if valid, None otherwise
        """
        return self._buy_parser.parse(message_id, text)
    
    def parse_profit_alert(
        self,
        message_id: int,
        text: str,
        reply_to_msg_id: Optional[int]
    ) -> Optional[ProfitAlert]:
        """
        Parse a message specifically for profit alerts.
        
        Args:
            message_id: Telegram message ID
            text: Message text content
            reply_to_msg_id: ID of the original signal message
            
        Returns:
            ProfitAlert if valid, None otherwise
        """
        return self._profit_parser.parse(message_id, text, reply_to_msg_id)


# =============================================================================
# Module-level utilities
# =============================================================================


# Module-level parser instance for convenience (backward compatibility)
_default_parser: Optional[MessageParser] = None
_parser_registry: Optional[ParserRegistry] = None


def get_parser(channel_id: str = CHANNEL_VOLSM) -> MessageParser:
    """
    Get a message parser instance.
    
    Args:
        channel_id: Channel identifier for channel-specific parsing.
                   Defaults to VOLSM for backward compatibility.
    
    Returns:
        MessageParser configured for the specified channel.
    """
    global _default_parser
    # For default (VOLSM), use cached instance
    if channel_id == CHANNEL_VOLSM:
        if _default_parser is None:
            _default_parser = MessageParser(channel_id=CHANNEL_VOLSM)
        return _default_parser
    # For other channels, create new instance
    return MessageParser(channel_id=channel_id)


def get_registry() -> ParserRegistry:
    """Get the singleton parser registry instance."""
    global _parser_registry
    if _parser_registry is None:
        _parser_registry = ParserRegistry()
    return _parser_registry
