#!/usr/bin/env python3
"""
Verify which signal messages still exist in the Telegram channel.
This helps identify deleted messages that are causing "Message does not exist" errors.
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

from telethon import TelegramClient
from telethon.errors import MessageIdInvalidError
from src.config import get_settings
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


async def verify_messages():
    """Check which messages exist in the Telegram channel."""
    
    # Load config
    settings = get_settings()
    
    # Build DSN and load signals from database
    db_dsn = build_database_dsn()
    signal_db = SignalDatabase(db_dsn)
    await signal_db.connect()
    
    # Get signals from last 30 days
    signals = await signal_db.get_signals_in_period(days=30)
    print(f"Found {len(signals)} signals in last 30 days\n")
    
    # Take most recent 30 signals for testing
    recent_signals = signals[:50] if len(signals) > 50 else signals
    
    # Connect to Telegram - use existing session
    session_name = settings.telegram.session_name or 'wallet_tracker_session'
    client = TelegramClient(
        session_name,
        settings.telegram.api_id,
        settings.telegram.api_hash
    )
    
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Session not authorized. Please run the main bot first to authenticate.")
    
    try:
        # Get channel entity
        channel = await client.get_entity(TRENCHES_CHANNEL_USERNAME)
        
        print(f"Checking messages in channel: {TRENCHES_CHANNEL_USERNAME}\n")
        print("-" * 80)
        
        deleted_count = 0
        existing_count = 0
        deleted_signals = []
        existing_signals = []
        
        for signal_with_pnl in recent_signals:
            # SignalWithPnL has a .signal attribute that contains the TokenSignal
            signal = signal_with_pnl.signal
            msg_id = signal.telegram_msg_id
            symbol = signal.token_symbol
            timestamp = signal.timestamp
            
            try:
                # Try to get the message
                message = await client.get_messages(channel, ids=msg_id)
                
                if message and not message.deleted:
                    existing_count += 1
                    existing_signals.append((msg_id, symbol, timestamp))
                    print(f"✅ Message {msg_id} EXISTS - ${symbol} ({timestamp})")
                else:
                    deleted_count += 1
                    deleted_signals.append((msg_id, symbol, timestamp))
                    print(f"❌ Message {msg_id} DELETED - ${symbol} ({timestamp})")
                    
            except MessageIdInvalidError:
                deleted_count += 1
                deleted_signals.append((msg_id, symbol, timestamp))
                print(f"❌ Message {msg_id} INVALID - ${symbol} ({timestamp})")
            except Exception as e:
                print(f"⚠️  Message {msg_id} ERROR - ${symbol} ({timestamp}): {e}")
            
            # Rate limit
            await asyncio.sleep(0.3)
        
        print("-" * 80)
        print(f"\nSummary:")
        print(f"  ✅ Existing: {existing_count}")
        print(f"  ❌ Deleted:  {deleted_count}")
        print(f"  Total:      {len(recent_signals)}")
        
        if deleted_count > 0:
            print(f"\n⚠️  Deletion rate: {deleted_count / len(recent_signals) * 100:.1f}%")
            print(f"\nThis means {deleted_count} messages have been deleted from the channel.")
            print("These will show 'Message does not exist' when clicked.")
            
            print(f"\n📋 Deleted Signal Message IDs:")
            for msg_id, symbol, ts in deleted_signals:
                print(f"   - {msg_id}: ${symbol} ({ts})")
        
    finally:
        await signal_db.disconnect()
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(verify_messages())
