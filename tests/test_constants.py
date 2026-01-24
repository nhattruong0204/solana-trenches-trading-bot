"""
Tests for the constants module.
"""

import pytest
from src.constants import (
    TRENCHES_CHANNEL_USERNAME,
    TRENCHES_CHANNEL_NAME,
    GMGN_BOT_USERNAME,
    BUY_SIGNAL_INDICATORS,
    PROFIT_ALERT_INDICATORS,
    TOKEN_SYMBOL_PATTERN,
    TOKEN_ADDRESS_PATTERN,
    MULTIPLIER_PATTERN,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT,
    DEFAULT_LOG_FILE,
)
import re


class TestTelegramConstants:
    """Tests for Telegram-related constants."""
    
    def test_channel_username_is_string(self):
        """Test channel username is a string."""
        assert isinstance(TRENCHES_CHANNEL_USERNAME, str)
        assert len(TRENCHES_CHANNEL_USERNAME) > 0
    
    def test_channel_name_is_string(self):
        """Test channel name is a string."""
        assert isinstance(TRENCHES_CHANNEL_NAME, str)
        assert len(TRENCHES_CHANNEL_NAME) > 0
    
    def test_gmgn_bot_username(self):
        """Test GMGN bot username."""
        assert isinstance(GMGN_BOT_USERNAME, str)
        assert "GMGN" in GMGN_BOT_USERNAME


class TestSignalIndicators:
    """Tests for signal detection indicators."""
    
    def test_buy_signal_indicators_is_tuple(self):
        """Test buy signal indicators is a tuple."""
        assert isinstance(BUY_SIGNAL_INDICATORS, tuple)
        assert len(BUY_SIGNAL_INDICATORS) > 0
    
    def test_buy_signal_indicators_contain_signal(self):
        """Test buy signal indicators contain expected text."""
        for indicator in BUY_SIGNAL_INDICATORS:
            assert "SIGNAL" in indicator.upper()
    
    def test_profit_alert_indicators_is_tuple(self):
        """Test profit alert indicators is a tuple."""
        assert isinstance(PROFIT_ALERT_INDICATORS, tuple)
        assert len(PROFIT_ALERT_INDICATORS) > 0
    
    def test_profit_alert_indicators_contain_alert(self):
        """Test profit alert indicators contain expected text."""
        for indicator in PROFIT_ALERT_INDICATORS:
            assert "PROFIT" in indicator.upper() or "ALERT" in indicator.upper()


class TestRegexPatterns:
    """Tests for regex patterns."""
    
    def test_token_symbol_pattern_valid(self):
        """Test token symbol pattern is valid regex."""
        pattern = re.compile(TOKEN_SYMBOL_PATTERN)
        assert pattern is not None
    
    def test_token_symbol_pattern_matches(self):
        """Test token symbol pattern matches expected formats."""
        pattern = re.compile(TOKEN_SYMBOL_PATTERN)
        
        # Should match
        assert pattern.search("Token: - $TRUMP")
        assert pattern.search("Token: $MEMECOIN")
        assert pattern.search("Token:$TEST")
        
        # Extract group
        match = pattern.search("Token: - $SOLANA")
        assert match.group(1) == "SOLANA"
    
    def test_token_address_pattern_valid(self):
        """Test token address pattern is valid regex."""
        pattern = re.compile(TOKEN_ADDRESS_PATTERN)
        assert pattern is not None
    
    def test_token_address_pattern_matches(self):
        """Test token address pattern matches Solana addresses."""
        pattern = re.compile(TOKEN_ADDRESS_PATTERN)
        
        # Valid Solana-like addresses with prefix
        assert pattern.search("`7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr")
        assert pattern.search("└ 6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump")
        assert pattern.search("├ 9ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjk")
    
    def test_multiplier_pattern_valid(self):
        """Test multiplier pattern is valid regex."""
        pattern = re.compile(MULTIPLIER_PATTERN)
        assert pattern is not None
    
    def test_multiplier_pattern_matches(self):
        """Test multiplier pattern matches expected formats."""
        pattern = re.compile(MULTIPLIER_PATTERN)
        
        # Various formats
        assert pattern.search("**2.5X**")
        assert pattern.search("*3X*")
        assert pattern.search("10X")
        assert pattern.search("1.5X gain")
        
        # Extract value
        match = pattern.search("**5.5X**")
        assert float(match.group(1)) == 5.5


class TestLoggingConstants:
    """Tests for logging-related constants."""
    
    def test_log_format_is_string(self):
        """Test log format is a string."""
        assert isinstance(LOG_FORMAT, str)
        # Should contain standard format specifiers
        assert "%(levelname)" in LOG_FORMAT or "levelname" in LOG_FORMAT
    
    def test_log_date_format_is_string(self):
        """Test log date format is a string."""
        assert isinstance(LOG_DATE_FORMAT, str)
    
    def test_log_max_bytes_is_positive(self):
        """Test log max bytes is positive."""
        assert isinstance(LOG_MAX_BYTES, int)
        assert LOG_MAX_BYTES > 0
    
    def test_log_backup_count_is_non_negative(self):
        """Test log backup count is non-negative."""
        assert isinstance(LOG_BACKUP_COUNT, int)
        assert LOG_BACKUP_COUNT >= 0
    
    def test_default_log_file_is_string(self):
        """Test default log file is a string."""
        assert isinstance(DEFAULT_LOG_FILE, str)
        assert len(DEFAULT_LOG_FILE) > 0
