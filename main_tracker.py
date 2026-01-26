#!/usr/bin/env python3
"""
Main entry point for the MAIN Channel Signal Tracker Bot.

This bot monitors the "From The Trenches - MAIN" channel (@fttrenches_sol)
for signals and provides PnL tracking. It does NOT execute trades.

Usage:
    python main_tracker.py           # Start the tracker
    python main_tracker.py --verbose # Enable debug logging
    python main_tracker.py validate  # Validate configuration
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure src package is importable
sys.path.insert(0, str(Path(__file__).parent))

from src import __version__
from src.config import Settings, validate_environment, clear_settings_cache
from src.logging_config import setup_logging


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="main-tracker",
        description="MAIN Channel Signal Tracker - Monitor signals from @fttrenches_sol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Start the tracker
  %(prog)s --verbose          Enable debug logging
  %(prog)s validate           Validate configuration

Environment Variables:
  TELEGRAM_API_ID         Telegram API ID (required)
  TELEGRAM_API_HASH       Telegram API hash (required)
  MAIN_BOT_TOKEN          Bot token for MAIN tracker (required)
  ADMIN_USER_ID           Admin Telegram user ID (required)
  POSTGRES_HOST           PostgreSQL host
  POSTGRES_PORT           PostgreSQL port
  POSTGRES_USER           PostgreSQL user  
  POSTGRES_PASSWORD       PostgreSQL password
  POSTGRES_DATABASE       PostgreSQL database
        """,
    )
    
    # Version
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    # Logging options
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    log_group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )
    log_group.add_argument(
        "--log-file",
        type=Path,
        metavar="FILE",
        help="Log file path (default: main_tracker.log)",
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Validate command
    subparsers.add_parser(
        "validate",
        help="Validate configuration without starting",
    )
    
    return parser


def validate_config() -> bool:
    """
    Validate configuration and environment.
    
    Returns:
        True if configuration is valid
    """
    print("Validating MAIN tracker configuration...")
    
    # Check required env vars
    required_vars = [
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "MAIN_BOT_TOKEN",
        "ADMIN_USER_ID",
    ]
    
    errors = []
    for var in required_vars:
        if not os.getenv(var):
            errors.append(f"Missing required environment variable: {var}")
    
    if errors:
        print("\n❌ Configuration errors:")
        for error in errors:
            print(f"   - {error}")
        return False
    
    # Check database config
    db_configured = bool(os.getenv("POSTGRES_PASSWORD"))
    
    print("\n✅ Configuration is valid:")
    print(f"   - Telegram API ID: {os.getenv('TELEGRAM_API_ID')}")
    print(f"   - Bot Token: {'*' * 10}...{os.getenv('MAIN_BOT_TOKEN', '')[-6:]}")
    print(f"   - Admin User ID: {os.getenv('ADMIN_USER_ID')}")
    print(f"   - Database: {'Configured' if db_configured else 'Not configured'}")
    return True


async def run_tracker(args: argparse.Namespace) -> int:
    """
    Run the MAIN tracker bot.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success)
    """
    # Setup logging
    log_level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    
    # Determine log file path
    if args.log_file:
        log_file = args.log_file
    else:
        log_file_env = os.getenv("MAIN_LOG_FILE")
        if log_file_env:
            log_file = Path(log_file_env)
        elif Path("/app/data").exists() and os.access("/app/data", os.W_OK):
            log_file = Path("/app/data/main_tracker.log")
        elif os.access(".", os.W_OK):
            log_file = Path("main_tracker.log")
        else:
            log_file = None
    
    setup_logging(log_file=log_file, log_level=log_level)
    
    logger = logging.getLogger(__name__)
    
    # Check required env vars
    required_vars = [
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "MAIN_BOT_TOKEN",
        "ADMIN_USER_ID",
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            logger.error(f"Missing required environment variable: {var}")
            print(f"\n❌ Missing {var}. See --help for details.")
            return 1
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return 1
    
    # Import tracker bot
    from src.main_tracker_bot import MainTrackerBot
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    
    # Get config
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    bot_token = os.getenv("MAIN_BOT_TOKEN", "")
    admin_user_id = int(os.getenv("ADMIN_USER_ID", "0"))
    
    # Session for user client (to read channel messages)
    # Can be:
    # 1. MAIN_SESSION_STRING env var (string session)
    # 2. MAIN_SESSION_FILE env var (file path)
    # 3. Same as trading bot session
    session_string = os.getenv("MAIN_SESSION_STRING", os.getenv("TELEGRAM_SESSION_STRING", ""))
    session_file = os.getenv("MAIN_SESSION_FILE", os.getenv("SESSION_FILE", "/app/data/vps_session.session"))
    
    # Create user client for channel access
    if session_string:
        user_client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        user_client = TelegramClient(session_file, api_id, api_hash)
    
    logger.info("Starting MAIN Channel Tracker Bot...")
    logger.info(f"Bot token: ...{bot_token[-6:]}")
    logger.info(f"Admin user ID: {admin_user_id}")
    
    # Create and start tracker bot
    tracker = MainTrackerBot(
        api_id=api_id,
        api_hash=api_hash,
        bot_token=bot_token,
        settings=settings,
        admin_user_id=admin_user_id,
    )
    
    try:
        # Connect user client first
        await user_client.connect()
        if not await user_client.is_user_authorized():
            logger.error("User client not authorized. Please set up session first.")
            print("\n❌ Telegram session not authorized. Set MAIN_SESSION_STRING or MAIN_SESSION_FILE.")
            return 1
        
        logger.info("✅ User client connected (for channel access)")
        
        # Set user client on tracker
        tracker.set_user_client(user_client)
        
        # Start tracker bot
        await tracker.start()
        
        print("\n" + "=" * 60)
        print("🔔 MAIN CHANNEL SIGNAL TRACKER")
        print("=" * 60)
        print(f"Channel: @fttrenches_sol (MAIN)")
        print(f"Admin:   {admin_user_id}")
        print("=" * 60)
        print("\nBot is running. Press Ctrl+C to stop.\n")
        
        # Run until disconnected
        await tracker.run_until_disconnected()
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        print("\n\nShutdown requested by user")
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        # Cleanup
        await tracker.stop()
        await user_client.disconnect()


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point.
    
    Args:
        argv: Command line arguments (defaults to sys.argv)
        
    Returns:
        Exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # Handle subcommands
    if args.command == "validate":
        return 0 if validate_config() else 1
    
    # Run the tracker
    try:
        return asyncio.run(run_tracker(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
