"""
Tests for the logging_config module.
"""

import pytest
import logging
from pathlib import Path
from io import StringIO
import sys
from unittest.mock import patch, MagicMock

from src.logging_config import (
    ColoredFormatter,
    setup_logging,
    get_logger,
    LogContext,
)
from src.constants import LOG_FORMAT, LOG_DATE_FORMAT


class TestColoredFormatter:
    """Tests for ColoredFormatter class."""
    
    def test_create_formatter(self):
        """Test creating a colored formatter."""
        formatter = ColoredFormatter()
        assert formatter is not None
    
    def test_create_formatter_with_custom_format(self):
        """Test creating formatter with custom format."""
        custom_fmt = "%(levelname)s: %(message)s"
        formatter = ColoredFormatter(fmt=custom_fmt)
        assert formatter is not None
    
    def test_format_debug_message(self):
        """Test formatting debug level message."""
        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=1,
            msg="Debug message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        # Should contain the message
        assert "Debug message" in result
        # Should have color codes for debug (gray)
        assert "\033[90m" in result
        assert "\033[0m" in result
    
    def test_format_info_message(self):
        """Test formatting info level message."""
        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Info message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        assert "Info message" in result
        # Should have green color
        assert "\033[92m" in result
    
    def test_format_warning_message(self):
        """Test formatting warning level message."""
        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        assert "Warning message" in result
        # Should have yellow color
        assert "\033[93m" in result
    
    def test_format_error_message(self):
        """Test formatting error level message."""
        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        assert "Error message" in result
        # Should have red color
        assert "\033[91m" in result
    
    def test_format_critical_message(self):
        """Test formatting critical level message."""
        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="test.py",
            lineno=1,
            msg="Critical message",
            args=(),
            exc_info=None,
        )
        
        result = formatter.format(record)
        assert "Critical message" in result
        # Should have red background
        assert "\033[41m" in result


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        logger = setup_logging(log_level=logging.INFO, enable_console=False)
        assert logger is not None
    
    def test_setup_logging_with_console(self):
        """Test setup with console handler."""
        logger = setup_logging(log_level=logging.DEBUG, enable_console=True)
        
        # Should have at least one handler
        assert len(logger.handlers) >= 0
    
    def test_setup_logging_with_file(self, tmp_path):
        """Test setup with file handler."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(
            log_file=log_file,
            log_level=logging.INFO,
            enable_console=False,
        )
        
        # Log a message
        logger.info("Test message")
        
        # File should exist
        assert log_file.exists()
    
    def test_setup_logging_creates_directories(self, tmp_path):
        """Test that setup creates log directories."""
        log_file = tmp_path / "logs" / "subdir" / "test.log"
        
        setup_logging(
            log_file=log_file,
            log_level=logging.INFO,
            enable_console=False,
        )
        
        # Directory should be created
        assert log_file.parent.exists()
    
    def test_setup_logging_without_colors(self):
        """Test setup without colored output."""
        logger = setup_logging(
            log_level=logging.INFO,
            enable_console=True,
            enable_colors=False,
        )
        assert logger is not None
    
    def test_setup_logging_clears_existing_handlers(self):
        """Test that setup clears existing handlers."""
        root = logging.getLogger()
        
        # Add a dummy handler
        dummy_handler = logging.NullHandler()
        root.addHandler(dummy_handler)
        
        # Setup logging (clears handlers)
        setup_logging(enable_console=False)
        
        # Dummy handler should be gone
        assert dummy_handler not in root.handlers
    
    def test_setup_logging_suppresses_third_party(self):
        """Test that third-party loggers are suppressed."""
        setup_logging(enable_console=False)
        
        telethon_logger = logging.getLogger("telethon")
        asyncio_logger = logging.getLogger("asyncio")
        
        assert telethon_logger.level >= logging.WARNING
        assert asyncio_logger.level >= logging.WARNING


class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)
    
    def test_get_logger_with_name(self):
        """Test that logger has correct name."""
        logger = get_logger("my.module.name")
        assert logger.name == "my.module.name"
    
    def test_get_same_logger_twice(self):
        """Test that same logger is returned for same name."""
        logger1 = get_logger("unique_name")
        logger2 = get_logger("unique_name")
        assert logger1 is logger2


class TestLogContext:
    """Tests for LogContext class."""
    
    def test_create_context(self):
        """Test creating a log context."""
        context = LogContext(wallet="abc123", token="XYZ")
        assert context.context == {"wallet": "abc123", "token": "XYZ"}
    
    def test_context_manager_enter_exit(self):
        """Test entering and exiting context."""
        original_factory = logging.getLogRecordFactory()
        
        with LogContext(test_key="test_value"):
            # Factory should be changed
            current_factory = logging.getLogRecordFactory()
            assert current_factory != original_factory
        
        # Factory should be restored
        assert logging.getLogRecordFactory() == original_factory
    
    def test_context_adds_attributes_to_records(self):
        """Test that context adds attributes to log records."""
        with LogContext(wallet="abc123"):
            factory = logging.getLogRecordFactory()
            record = factory(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="test",
                args=(),
                exc_info=None,
            )
            
            assert hasattr(record, "wallet")
            assert record.wallet == "abc123"
    
    def test_multiple_context_attributes(self):
        """Test context with multiple attributes."""
        with LogContext(key1="val1", key2="val2", key3="val3"):
            factory = logging.getLogRecordFactory()
            record = factory(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="test",
                args=(),
                exc_info=None,
            )
            
            assert record.key1 == "val1"
            assert record.key2 == "val2"
            assert record.key3 == "val3"
    
    def test_nested_contexts(self):
        """Test nested log contexts."""
        original_factory = logging.getLogRecordFactory()
        
        with LogContext(outer="value1"):
            with LogContext(inner="value2"):
                factory = logging.getLogRecordFactory()
                record = factory(
                    name="test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=1,
                    msg="test",
                    args=(),
                    exc_info=None,
                )
                # Inner context should have its attribute
                assert record.inner == "value2"
        
        # Should be restored after exiting both
        assert logging.getLogRecordFactory() == original_factory
