"""Command-line interface for the token analysis bot."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.config import get_settings
from src.orchestrator import TokenAnalysisOrchestrator
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Token Analysis Bot - Automated token research for Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run the full bot
  token-analyzer

  # Run with debug logging
  token-analyzer --debug

  # Analyze a specific token
  token-analyzer --analyze 0x1234...

  # Check configuration
  token-analyzer --check-config
        """,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Set log level",
    )

    parser.add_argument(
        "--analyze",
        metavar="ADDRESS",
        help="Analyze a specific token address and exit",
    )

    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Check configuration and exit",
    )

    parser.add_argument(
        "--no-chain",
        action="store_true",
        help="Disable chain event detection",
    )

    parser.add_argument(
        "--no-moltbook",
        action="store_true",
        help="Disable Moltbook polling",
    )

    parser.add_argument(
        "--no-twitter",
        action="store_true",
        help="Disable Twitter monitoring",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually post to Telegram",
    )

    return parser.parse_args()


def check_config() -> bool:
    """Check configuration and print status."""
    settings = get_settings()

    print("Configuration Check")
    print("=" * 50)

    # Database
    db_status = "OK" if settings.database.url else "Missing"
    print(f"Database URL: {db_status}")

    # Telegram
    tg_bot_status = "OK" if settings.telegram.bot_token else "Missing"
    tg_channel_status = "OK" if settings.telegram.target_channel else "Missing"
    print(f"Telegram Bot Token: {tg_bot_status}")
    print(f"Telegram Target Channel: {tg_channel_status}")

    # LLM
    if settings.llm.provider == "anthropic":
        llm_status = "OK" if settings.llm.anthropic_api_key else "Missing"
    else:
        llm_status = "OK" if settings.llm.openai_api_key else "Missing"
    print(f"LLM API Key ({settings.llm.provider}): {llm_status}")

    # Chain
    chain_status = "OK" if settings.chain.rpc_url else "Missing"
    print(f"Base RPC URL: {chain_status}")

    # Twitter (optional)
    twitter_status = "OK" if settings.twitter.bearer_token else "Not configured"
    print(f"Twitter API: {twitter_status}")

    # Moltbook
    moltbook_status = "OK" if settings.moltbook.api_url else "Missing"
    print(f"Moltbook API URL: {moltbook_status}")

    print("=" * 50)

    # Check critical components
    critical_ok = all([
        settings.telegram.bot_token,
        settings.telegram.target_channel,
        settings.llm.anthropic_api_key or settings.llm.openai_api_key,
        settings.chain.rpc_url,
    ])

    if critical_ok:
        print("All critical components configured!")
        return True
    else:
        print("Missing critical configuration. Check .env file.")
        return False


async def analyze_single_token(address: str, dry_run: bool = False) -> None:
    """Analyze a single token and print results."""
    settings = get_settings()
    orchestrator = TokenAnalysisOrchestrator(settings)

    try:
        # Initialize components (but not full startup)
        await orchestrator.enrichment.initialize()
        await orchestrator.synthesizer.initialize()
        await orchestrator.repository.initialize()

        # Create a manual event
        from src.models import EventSource, TokenEvent
        from datetime import datetime

        event = TokenEvent(
            token_address=address,
            pair_address=None,
            source=EventSource.MANUAL,
            detected_at=datetime.utcnow(),
            chain_id=settings.chain.chain_id,
        )

        # Run enrichment
        print(f"\nAnalyzing token: {address}")
        print("-" * 50)

        contract, dev_profile, metrics = await orchestrator.enrichment.enrich(event)

        print(f"\nToken: {contract.symbol or 'UNKNOWN'} ({contract.name or 'Unknown'})")
        print(f"Deployer: {contract.deployer_address or 'Unknown'}")
        print(f"Honeypot: {contract.is_honeypot}")
        print(f"Renounced: {contract.is_renounced}")

        print(f"\nDev Twitter: {dev_profile.twitter_handle or 'Anonymous'}")
        print(f"Followers: {dev_profile.twitter_followers}")
        print(f"Red Flags: {', '.join(dev_profile.red_flags) or 'None'}")

        print(f"\nFDV: ${metrics.fdv_usd:,.2f}")
        print(f"Liquidity: ${metrics.liquidity_usd:,.2f}")
        print(f"Holders: {metrics.holder_count}")
        print(f"Top 10 %: {metrics.top_10_holder_pct:.1f}%")

        # Synthesize
        breakdown = await orchestrator.synthesizer.synthesize(
            contract, dev_profile, metrics
        )

        print(f"\n{'=' * 50}")
        print(f"Risk Rating: {breakdown.risk_rating.emoji} {breakdown.risk_rating.value.upper()}")
        print(f"Confidence: {breakdown.overall_confidence:.0%}")

        print("\nPros:")
        for pro in breakdown.pros:
            print(f"  + {pro.text}")

        print("\nCons:")
        for con in breakdown.cons:
            print(f"  - {con.text}")

        print(f"\nDexScreener: {breakdown.dexscreener_url}")

        if not dry_run:
            # Format the message
            from src.delivery.formatter import MessageFormatter
            message = MessageFormatter.format_breakdown(breakdown)
            print(f"\n{'=' * 50}")
            print("Telegram Message Preview:")
            print(message)

    except Exception as e:
        print(f"\nError analyzing token: {e}")
        raise

    finally:
        await orchestrator.enrichment.close()
        await orchestrator.synthesizer.close()
        await orchestrator.repository.close()


async def run_bot(args: argparse.Namespace) -> None:
    """Run the full bot."""
    settings = get_settings()

    # Override settings based on args
    if args.dry_run:
        settings.analysis.enable_human_approval = True

    orchestrator = TokenAnalysisOrchestrator(settings)

    try:
        await orchestrator.start()

        # Keep running
        print("\nToken Analysis Bot running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await orchestrator.stop()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Get settings
    settings = get_settings()

    # Setup logging
    log_level = args.log_level or settings.log_level
    setup_logging(
        level=log_level,
        log_file=settings.paths.log_file,
        debug=args.debug,
    )

    # Handle different modes
    if args.check_config:
        success = check_config()
        return 0 if success else 1

    if args.analyze:
        asyncio.run(analyze_single_token(args.analyze, dry_run=args.dry_run))
        return 0

    # Run full bot
    asyncio.run(run_bot(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
