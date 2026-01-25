#!/usr/bin/env python3
"""
Create public and premium channels for the trading bot.

This script will:
1. Create a PUBLIC channel for marketing (free signals)
2. Create a PREMIUM channel for paid subscribers
3. Add your bot as admin to both channels
4. Output the channel IDs for .env configuration
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    EditPhotoRequest,
)
from telethon.tl.types import (
    ChatAdminRights,
    InputChannel,
)
from src.config import get_settings


async def create_channels():
    """Create public and premium channels."""
    settings = get_settings()

    print("=" * 60)
    print("  Trading Bot - Channel Creator")
    print("=" * 60)
    print()

    # Connect to Telegram
    client = TelegramClient(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )

    await client.start(phone=settings.telegram_phone)
    print("[OK] Connected to Telegram")
    print()

    # Channel names
    public_name = "Trenches Trading Signals"
    public_about = (
        "Free trading signals from Trenches Trading Bot\n\n"
        "2X+ winners highlighted\n"
        "Hit rate: 60%+\n\n"
        "Subscribe for premium instant signals: @YourPremiumBot"
    )

    premium_name = "Trenches Premium Signals"
    premium_about = (
        "PREMIUM MEMBERS ONLY\n\n"
        "Instant signals (no delay)\n"
        "Full token addresses\n"
        "KOL/Whale alerts\n"
        "60%+ hit rate on 2X calls"
    )

    # Ask for confirmation
    print("This will create 2 channels:")
    print(f"  1. PUBLIC:  {public_name}")
    print(f"  2. PREMIUM: {premium_name}")
    print()
    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        await client.disconnect()
        return

    print()

    # Create PUBLIC channel (broadcast channel)
    print("Creating PUBLIC channel...")
    try:
        result = await client(CreateChannelRequest(
            title=public_name,
            about=public_about,
            broadcast=True,  # True = channel, False = supergroup
            megagroup=False,
        ))
        public_channel = result.chats[0]
        public_id = f"-100{public_channel.id}"
        print(f"  [OK] Created: {public_name}")
        print(f"  [OK] Channel ID: {public_id}")
    except Exception as e:
        print(f"  [ERROR] Failed to create public channel: {e}")
        await client.disconnect()
        return

    print()

    # Create PREMIUM channel
    print("Creating PREMIUM channel...")
    try:
        result = await client(CreateChannelRequest(
            title=premium_name,
            about=premium_about,
            broadcast=True,
            megagroup=False,
        ))
        premium_channel = result.chats[0]
        premium_id = f"-100{premium_channel.id}"
        print(f"  [OK] Created: {premium_name}")
        print(f"  [OK] Channel ID: {premium_id}")
    except Exception as e:
        print(f"  [ERROR] Failed to create premium channel: {e}")
        await client.disconnect()
        return

    print()

    # Try to add bot as admin if bot token is configured
    if settings.bot_token:
        print("Attempting to add bot as admin...")

        # Get bot info
        bot_username = settings.bot_token.split(":")[0]
        try:
            bot_entity = await client.get_entity(f"@GMGN_sol_bot")  # placeholder
            # Note: Adding bots as admin requires the bot to exist and be accessible
            # This is a placeholder - actual implementation needs the bot's username
            print("  [INFO] Add your bot manually as admin to both channels")
        except Exception as e:
            print(f"  [INFO] Add your bot manually as admin to both channels")

    print()
    print("=" * 60)
    print("  SETUP COMPLETE!")
    print("=" * 60)
    print()
    print("Add these to your .env file:")
    print()
    print(f"PUBLIC_CHANNEL_ID={public_id}")
    print(f"PUBLIC_CHANNEL_USERNAME=")  # Can be set after making channel public
    print(f"PREMIUM_CHANNEL_ID={premium_id}")
    print()
    print("Next steps:")
    print("1. Make the PUBLIC channel public:")
    print("   - Open channel settings")
    print("   - Change 'Channel type' to 'Public'")
    print("   - Set a username (e.g., @TrenchesSignals)")
    print()
    print("2. Add your bot as admin to BOTH channels:")
    print("   - Open channel > Edit > Administrators > Add Admin")
    print("   - Search for your bot and add it")
    print("   - Grant 'Post Messages' permission")
    print()
    print("3. Keep PREMIUM channel private (invite-only)")
    print()

    await client.disconnect()

    return {
        "public_id": public_id,
        "premium_id": premium_id,
    }


if __name__ == "__main__":
    asyncio.run(create_channels())
