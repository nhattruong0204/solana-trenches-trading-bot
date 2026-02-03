"""Logging configuration."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    debug: bool = False,
) -> None:
    """Configure application logging."""
    # Determine log level
    if debug:
        level = "DEBUG"

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatters
    console_format = "%(message)s"
    file_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler with Rich
    console = Console(stderr=True)
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=debug,
    )
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        # Ensure log directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(file_format))
        root_logger.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("web3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={level}, file={log_file}")
