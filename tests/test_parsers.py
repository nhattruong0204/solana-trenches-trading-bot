"""
Tests for the message parser module.
"""

import pytest
from datetime import datetime, timezone

from src.parsers import (
    BuySignalParser,
    ProfitAlertParser,
    MessageParser,
    get_parser,
)
from src.models import BuySignal, ProfitAlert


class TestBuySignalParser:
    """Tests for BuySignalParser."""
    
    def setup_method(self):
        self.parser = BuySignalParser()
    
    def test_can_parse_detects_buy_signal(self, sample_buy_message):
        """Test that can_parse correctly identifies buy signals."""
        assert self.parser.can_parse(sample_buy_message) is True
    
    def test_can_parse_rejects_non_signals(self):
        """Test that can_parse rejects non-signal messages."""
        assert self.parser.can_parse("Hello world") is False
        assert self.parser.can_parse("PROFIT ALERT") is False
    
    def test_parse_extracts_signal_data(self, sample_buy_message):
        """Test that parse correctly extracts signal data."""
        result = self.parser.parse(12345, sample_buy_message)
        
        assert result is not None
        assert isinstance(result, BuySignal)
        assert result.message_id == 12345
        assert result.token_symbol == "TRUMP"
        assert result.token_address == "6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump"
    
    def test_parse_returns_none_for_invalid_message(self):
        """Test that parse returns None for invalid messages."""
        result = self.parser.parse(12345, "Not a signal")
        assert result is None
    
    def test_parse_handles_missing_address(self):
        """Test parsing message with missing token address."""
        message = """
        `// VOLUME + SM APE SIGNAL DETECTED` 🧪
        Token: $TEST
        No address here
        """
        result = self.parser.parse(12345, message)
        assert result is None
    
    def test_parse_extracts_unknown_symbol(self):
        """Test parsing when symbol pattern doesn't match."""
        message = """
        `// VOLUME + SM APE SIGNAL DETECTED` 🧪
        └ `6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump`
        """
        result = self.parser.parse(12345, message)
        
        assert result is not None
        assert result.token_symbol == "UNKNOWN"
    
    def test_validates_solana_address(self):
        """Test that invalid addresses are rejected."""
        # Address with invalid characters (contains 0, O, I, l)
        message = """
        `// VOLUME + SM APE SIGNAL DETECTED` 🧪
        Token: $TEST
        └ `0OIlxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
        """
        result = self.parser.parse(12345, message)
        assert result is None


class TestProfitAlertParser:
    """Tests for ProfitAlertParser."""
    
    def setup_method(self):
        self.parser = ProfitAlertParser()
    
    def test_can_parse_detects_profit_alert(self, sample_profit_message):
        """Test that can_parse correctly identifies profit alerts."""
        assert self.parser.can_parse(sample_profit_message) is True
    
    def test_can_parse_rejects_non_alerts(self):
        """Test that can_parse rejects non-alert messages."""
        assert self.parser.can_parse("Hello world") is False
        assert self.parser.can_parse("VOLUME + SM APE SIGNAL") is False
    
    def test_parse_extracts_alert_data(self, sample_profit_message):
        """Test that parse correctly extracts alert data."""
        result = self.parser.parse(12346, sample_profit_message, reply_to_msg_id=12345)
        
        assert result is not None
        assert isinstance(result, ProfitAlert)
        assert result.message_id == 12346
        assert result.reply_to_msg_id == 12345
        assert result.multiplier == 2.5
    
    def test_parse_requires_reply_to(self, sample_profit_message):
        """Test that parse requires reply_to_msg_id."""
        result = self.parser.parse(12346, sample_profit_message)
        assert result is None
    
    def test_parse_handles_various_multiplier_formats(self):
        """Test parsing different multiplier formats."""
        test_cases = [
            ("PROFIT ALERT - 2X gain!", 2.0),
            ("PROFIT ALERT - **3.5X**", 3.5),
            ("PROFIT ALERT 10.5 X", 10.5),
        ]
        
        for message, expected in test_cases:
            result = self.parser.parse(1, message, reply_to_msg_id=100)
            assert result is not None, f"Failed to parse: {message}"
            assert result.multiplier == expected, f"Wrong multiplier for: {message}"
    
    def test_rejects_unrealistic_multipliers(self):
        """Test that unrealistic multipliers are rejected."""
        message = "PROFIT ALERT - 5000X"
        result = self.parser.parse(1, message, reply_to_msg_id=100)
        assert result is None


class TestMessageParser:
    """Tests for the unified MessageParser."""
    
    def setup_method(self):
        self.parser = MessageParser()
    
    def test_parse_buy_signal(self, sample_buy_message):
        """Test parsing a buy signal through the unified parser."""
        result = self.parser.parse(12345, sample_buy_message)
        
        assert result.has_signal is True
        assert result.buy_signal is not None
        assert result.profit_alert is None
    
    def test_parse_profit_alert(self, sample_profit_message):
        """Test parsing a profit alert through the unified parser."""
        result = self.parser.parse(12346, sample_profit_message, reply_to_msg_id=12345)
        
        assert result.has_signal is True
        assert result.buy_signal is None
        assert result.profit_alert is not None
    
    def test_parse_returns_empty_for_unknown(self):
        """Test that unknown messages return empty result."""
        result = self.parser.parse(1, "Hello world")
        
        assert result.has_signal is False
        assert result.buy_signal is None
        assert result.profit_alert is None
    
    def test_get_parser_returns_singleton(self):
        """Test that get_parser returns the same instance."""
        parser1 = get_parser()
        parser2 = get_parser()
        assert parser1 is parser2
