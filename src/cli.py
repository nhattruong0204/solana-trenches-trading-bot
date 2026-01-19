"""
Command-line interface for the trading bot.

Provides a clean CLI with proper argument parsing, help text,
and configuration options.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from src import __version__
from src.bot import TradingBot
from src.config import Settings, validate_environment, clear_settings_cache
from src.logging_config import setup_logging


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description="Solana Auto Trading Bot - Trade tokens based on Telegram signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    Start in dry run mode (default)
  %(prog)s --live             Start with live trading
  %(prog)s --buy-amount 0.5   Buy 0.5 SOL per signal
  %(prog)s --verbose          Enable debug logging

Environment Variables:
  TELEGRAM_API_ID       Telegram API ID (required)
  TELEGRAM_API_HASH     Telegram API hash (required)
  TRADING_DRY_RUN       Enable dry run mode (default: true)
  TRADING_BUY_AMOUNT_SOL Amount to buy per signal
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
        help="Log file path (default: trading_bot.log)",
    )
    
    # Trading options
    trading_group = parser.add_argument_group("Trading")
    trading_group.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading (disables dry run)",
    )
    trading_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in simulation mode without executing trades (default)",
    )
    trading_group.add_argument(
        "--buy-amount",
        type=float,
        metavar="SOL",
        help="Amount of SOL to buy per signal",
    )
    trading_group.add_argument(
        "--sell-percentage",
        type=int,
        metavar="PCT",
        choices=range(1, 101),
        help="Percentage to sell at target (1-100)",
    )
    trading_group.add_argument(
        "--min-multiplier",
        type=float,
        metavar="X",
        help="Minimum multiplier to trigger sell (e.g., 2.0 for 2X)",
    )
    trading_group.add_argument(
        "--max-positions",
        type=int,
        metavar="N",
        help="Maximum concurrent open positions",
    )
    trading_group.add_argument(
        "--disabled",
        action="store_true",
        help="Start with trading disabled (monitor only)",
    )
    
    # State management
    state_group = parser.add_argument_group("State Management")
    state_group.add_argument(
        "--state-file",
        type=Path,
        metavar="FILE",
        help="State file path (default: trading_state.json)",
    )
    state_group.add_argument(
        "--reset-state",
        action="store_true",
        help="Clear existing state and start fresh",
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show current bot status and positions",
    )
    
    # Validate command
    validate_parser = subparsers.add_parser(
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
    print("Validating configuration...")
    
    is_valid, errors = validate_environment()
    
    if errors:
        print("\n❌ Configuration errors:")
        for error in errors:
            print(f"   - {error}")
        return False
    
    try:
        settings = Settings()
        print("\n✅ Configuration is valid:")
        print(f"   - Telegram API ID: {settings.telegram_api_id}")
        print(f"   - Dry Run: {settings.trading_dry_run}")
        print(f"   - Buy Amount: {settings.trading_buy_amount_sol} SOL")
        print(f"   - Sell at: {settings.trading_min_multiplier}X ({settings.trading_sell_percentage}%)")
        return True
    except Exception as e:
        print(f"\n❌ Failed to load settings: {e}")
        return False


async def run_bot(args: argparse.Namespace) -> int:
    """
    Run the trading bot with the given arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success)
    """
    # Setup logging
    log_level = logging.DEBUG if args.verbose else (logging.WARNING if args.quiet else logging.INFO)
    
    # Determine log file path
    # Priority: CLI arg > LOG_FILE env var > default location
    if args.log_file:
        log_file = args.log_file
    else:
        import os
        log_file_env = os.getenv("LOG_FILE")
        if log_file_env:
            log_file = Path(log_file_env)
        elif Path("/app/data").exists() and os.access("/app/data", os.W_OK):
            # Running in container with writable data directory
            log_file = Path("/app/data/trading_bot.log")
        elif os.access(".", os.W_OK):
            # Current directory is writable
            log_file = Path("trading_bot.log")
        else:
            # No writable location found, disable file logging
            log_file = None
    
    setup_logging(log_file=log_file, log_level=log_level)
    
    logger = logging.getLogger(__name__)
    
    # Validate environment
    is_valid, errors = validate_environment()
    if not is_valid:
        for error in errors:
            logger.error(error)
        print("\n❌ Missing required environment variables. See --help for details.")
        return 1
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        return 1
    
    # Apply command line overrides
    if args.live:
        settings.trading_dry_run = False
    if args.buy_amount is not None:
        settings.trading_buy_amount_sol = args.buy_amount
    if args.sell_percentage is not None:
        settings.trading_sell_percentage = args.sell_percentage
    if args.min_multiplier is not None:
        settings.trading_min_multiplier = args.min_multiplier
    if args.max_positions is not None:
        settings.trading_max_positions = args.max_positions
    if args.disabled:
        settings.trading_enabled = False
    if args.state_file:
        settings.state_file = str(args.state_file)
    
    # Live trading confirmation
    if not settings.trading_dry_run:
        print("\n" + "=" * 60)
        print("🔴 LIVE TRADING MODE")
        print("=" * 60)
        print(f"Buy Amount:      {settings.trading_buy_amount_sol} SOL per signal")
        print(f"Max Positions:   {settings.trading_max_positions}")
        print(f"Sell At:         {settings.trading_min_multiplier}X ({settings.trading_sell_percentage}%)")
        print("=" * 60)
        print("\n⚠️  Real trades will be executed!")
        print("Make sure GMGN bot is configured with your wallet.\n")
        
        try:
            confirm = input("Type 'CONFIRM' to start live trading: ")
            if confirm.strip() != "CONFIRM":
                print("Cancelled.")
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 0
    
    # Handle state reset
    if args.reset_state:
        state_file = Path(settings.state_file)
        if state_file.exists():
            state_file.unlink()
            logger.info(f"Cleared state file: {state_file}")
    
    # Run the bot
    try:
        bot = TradingBot(settings)
        async with bot:
            await bot.run()
        return 0
    except KeyboardInterrupt:
        print("\n\nShutdown requested by user")
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


def main(argv: Optional[list[str]] = None) -> int:
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
    
    if args.command == "status":
        print("Status command not yet implemented")
        return 0
    
    # Run the bot
    try:
        return asyncio.run(run_bot(args))
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
