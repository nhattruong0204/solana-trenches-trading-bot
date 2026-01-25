#!/usr/bin/env python3
"""
Quick script to check a sample of signal message IDs from database.
Doesn't actually verify in Telegram - just shows you the message IDs to manually check.
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.constants import TRENCHES_CHANNEL_USERNAME
from src.signal_database import SignalDatabase


def build_database_dsn() -> str:
    """Build PostgreSQL DSN from environment variables."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DATABASE", "wallet_tracker")
    
    if not password:
        raise ValueError("POSTGRES_PASSWORD environment variable is required")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def check_messages():
    """Get a sample of signal message IDs to check."""
    
    # Build DSN and load signals from database
    db_dsn = build_database_dsn()
    signal_db = SignalDatabase(db_dsn)
    await signal_db.connect()
    
    try:
        # Get recent signals
        signals = await signal_db.get_signals_in_period(days=30)
        print(f"Found {len(signals)} signals in last 30 days\n")
        
        # Take first 20 for sample
        sample = signals[:20] if len(signals) > 20 else signals
        
        print("=" * 80)
        print(f"Sample of recent signal message IDs from database:")
        print("=" * 80)
        print()
        
        for i, signal in enumerate(sample, 1):
            msg_id = signal.signal.telegram_msg_id
            symbol = signal.signal.token_symbol
            timestamp = signal.signal.timestamp.strftime("%Y-%m-%d %H:%M")
            
            # Generate the link
            link = f"https://t.me/{TRENCHES_CHANNEL_USERNAME}/{msg_id}"
            
            print(f"{i:2}. ${symbol:<10} | MSG ID: {msg_id} | {timestamp}")
            print(f"    {link}")
            print()
        
        print("=" * 80)
        print("\n📝 How to check if messages are deleted:")
        print("   1. Copy any of the above links")
        print("   2. Open in Telegram (web or app)")
        print("   3. If you see 'Message does not exist', that message was deleted")
        print()
        print("💡 Telegram channels can delete old messages to stay within limits")
        print("   or clean up old content. This is normal.")
        print()
        print(f"🔗 You can also manually browse: https://t.me/{TRENCHES_CHANNEL_USERNAME}")
        print()
        
    finally:
        await signal_db.disconnect()


if __name__ == "__main__":
    asyncio.run(check_messages())
