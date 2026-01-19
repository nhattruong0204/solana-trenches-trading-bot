"""
Logging configuration for the trading bot.

Provides structured logging with file rotation, colored console output,
and proper log level management.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.constants import (
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_MAX_BYTES,
    DEFAULT_LOG_FILE,
)


class ColoredFormatter(logging.Formatter):
    """
    Custom formatter with ANSI color codes for console output.
    
    Colors are applied based on log level:
    - DEBUG: Gray
    - INFO: Green
    - WARNING: Yellow
    - ERROR: Red
    - CRITICAL: Red background
    """
    
    # ANSI color codes
    COLORS = {
        logging.DEBUG: "\033[90m",      # Gray
        logging.INFO: "\033[92m",       # Green
        logging.WARNING: "\033[93m",    # Yellow
        logging.ERROR: "\033[91m",      # Red
        logging.CRITICAL: "\033[41m",   # Red background
    }
    RESET = "\033[0m"
    
    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None) -> None:
        super().__init__(fmt or LOG_FORMAT, datefmt or LOG_DATE_FORMAT)
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        color = self.COLORS.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{self.RESET}" if color else message


def setup_logging(
    log_file: Optional[Path] = None,
    log_level: int = logging.INFO,
    enable_console: bool = True,
    enable_colors: bool = True,
) -> logging.Logger:
    """
    Configure application logging.
    
    Args:
        log_file: Path to log file (None to disable file logging)
        log_level: Minimum log level to capture
        enable_console: Whether to log to console
        enable_colors: Whether to use colored console output
        
    Returns:
        Root logger instance
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter
    plain_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        if enable_colors and sys.stdout.isatty():
            console_handler.setFormatter(ColoredFormatter())
        else:
            console_handler.setFormatter(plain_formatter)
        
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(plain_formatter)
        root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding context to log messages.
    
    Usage:
        with LogContext(wallet="abc123", token="XYZ"):
            logger.info("Processing trade")  # Includes wallet and token context
    """
    
    def __init__(self, **context: str) -> None:
        self.context = context
        self._old_factory: Optional[logging.LogRecordFactory] = None
    
    def __enter__(self) -> "LogContext":
        self._old_factory = logging.getLogRecordFactory()
        context = self.context
        
        def record_factory(*args, **kwargs) -> logging.LogRecord:
            record = self._old_factory(*args, **kwargs)  # type: ignore
            for key, value in context.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)
