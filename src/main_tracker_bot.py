"""
MAIN Channel Signal Tracker Bot.

A simplified Telegram bot that monitors the "From The Trenches - MAIN" channel
(@fttrenches_sol) for signals and provides PnL tracking. This bot does NOT trade,
it only tracks signals and calculates theoretical PnL.

Commands:
    /start - Welcome message
    /menu - Show interactive button menu
    /syncsignals - Sync new signals from channel
    /bootstrap - One-time full history sync
    /signalpnl [days] [size] - Signal PnL statistics
    /realpnl [days] [size] - Real-time PnL from DexScreener
    /help - Show commands
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
from telethon.tl.custom import Button
from telethon.errors import MessageIdInvalidError

from src.signal_database import SignalDatabase
from src.constants import (
    TRENCHES_MAIN_CHANNEL_NAME,
    TRENCHES_MAIN_CHANNEL_USERNAME,
    MAIN_BUY_SIGNAL_INDICATORS,
    MAIN_PROFIT_ALERT_INDICATORS,
    MULTIPLIER_PATTERN,
    TOKEN_ADDRESS_PATTERN,
)

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)

# Telegram patterns
SOLANA_ADDRESS_PATTERN = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


class MainTrackerBot:
    """
    Telegram Bot for MAIN channel signal tracking only.
    
    This is a simplified version of NotificationBot that:
    - Monitors @fttrenches_sol channel (MAIN)
    - Tracks signals and profit alerts
    - Calculates PnL statistics
    - Does NOT execute trades
    - Does NOT have commercial features
    
    Commands (admin only):
        /start - Welcome message
        /menu - Show interactive button menu
        /syncsignals - Sync new signals from channel
        /bootstrap - One-time full history sync  
        /signalpnl [days] [size] - Signal PnL statistics
        /realpnl [days] [size] - Real-time PnL from DexScreener
        /help - Show commands
    """
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        settings: "Settings",
        admin_user_id: int,
    ) -> None:
        """
        Initialize the MAIN tracker bot.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            bot_token: Bot token from BotFather
            settings: Application settings
            admin_user_id: Telegram user ID of admin
        """
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._settings = settings
        self._admin_user_id = admin_user_id
        
        self._client: Optional[TelegramClient] = None
        self._initialized = False
        
        # User client for channel access (set externally)
        self._user_client: Optional[TelegramClient] = None
        
        # Signal database for historical PnL from PostgreSQL
        # Uses 'main' channel_id to filter queries
        self._signal_db: Optional[SignalDatabase] = None
        db_dsn = self._build_database_dsn()
        if db_dsn:
            self._signal_db = SignalDatabase(db_dsn, channel_id="main")
        
        # Cache for deleted message status (msg_id -> is_deleted)
        self._deleted_msg_cache: dict[int, bool] = {}
        
        # Admin chat ID (will be set on first message)
        self._admin_chat_id: Optional[int] = None
    
    def _build_database_dsn(self) -> Optional[str]:
        """Build PostgreSQL DSN from environment variables."""
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "")
        database = os.getenv("POSTGRES_DATABASE", "wallet_tracker")
        
        if not password:
            logger.warning("POSTGRES_PASSWORD not set, signal database disabled")
            return None
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    @property
    def signal_db(self) -> Optional[SignalDatabase]:
        """Get signal database."""
        return self._signal_db
    
    def set_user_client(self, client: TelegramClient) -> None:
        """
        Set the user client for channel access.
        
        The user client is needed to read messages from the MAIN channel
        (bots can't read channel messages directly).
        """
        self._user_client = client
    
    async def start(self) -> None:
        """Start the bot."""
        if self._initialized:
            return
        
        # Connect to database
        if self._signal_db:
            connected = await self._signal_db.connect()
            if connected:
                logger.info("✅ Connected to signal database (MAIN channel)")
            else:
                logger.warning("❌ Failed to connect to signal database")
        
        # Create bot client
        self._client = TelegramClient(
            StringSession(),
            self._api_id,
            self._api_hash,
        )
        
        await self._client.start(bot_token=self._bot_token)
        
        # Get bot info
        me = await self._client.get_me()
        logger.info(f"✅ MAIN Tracker Bot started as @{me.username}")
        
        # Register handlers
        self._register_handlers()
        
        self._initialized = True
    
    async def stop(self) -> None:
        """Stop the bot."""
        if self._signal_db:
            await self._signal_db.disconnect()
        
        if self._client:
            await self._client.disconnect()
        
        self._initialized = False
    
    async def run_until_disconnected(self) -> None:
        """Run the bot until disconnected."""
        if self._client:
            await self._client.run_until_disconnected()
    
    def _register_handlers(self) -> None:
        """Register command and callback handlers."""
        if not self._client:
            return

        logger.info("Registering command handlers...")

        # Command handler
        @self._client.on(events.NewMessage(pattern=r'^/'))
        async def handle_command(event):
            logger.info(f"Received command from {event.sender_id}: {event.text}")
            await self._handle_command(event)
        
        # Callback handler (button presses)
        @self._client.on(events.CallbackQuery)
        async def handle_callback(event):
            logger.info(f"Received callback from {event.sender_id}: {event.data}")
            await self._handle_callback(event)

        logger.info("✅ Command handlers registered")
    
    async def _handle_command(self, event) -> None:
        """Handle text commands."""
        sender = await event.get_sender()
        
        # Admin check
        if sender.id != self._admin_user_id:
            await event.respond("❌ Unauthorized")
            return
        
        # Store admin chat ID
        self._admin_chat_id = event.chat_id
        
        # Parse command
        text = event.text.strip()
        parts = text.split(maxsplit=1)
        command = parts[0].lower().replace("@", " ").split()[0]  # Remove @botusername
        args = parts[1] if len(parts) > 1 else ""
        
        # Route command
        command_map = {
            "/start": self._cmd_start,
            "/menu": self._cmd_menu,
            "/help": self._cmd_help,
            "/syncsignals": self._cmd_sync_signals,
            "/bootstrap": self._cmd_bootstrap_signals,
            "/signalpnl": self._cmd_signal_pnl,
            "/realpnl": self._cmd_real_pnl,
        }
        
        handler = command_map.get(command)
        if handler:
            await handler(args)
        else:
            await event.respond(
                f"❓ Unknown command: `{command}`\n\n"
                "Use /help to see available commands."
            )
    
    async def _handle_callback(self, event) -> None:
        """Handle button callbacks."""
        sender = await event.get_sender()
        
        # Admin check
        if sender.id != self._admin_user_id:
            await event.answer("❌ Unauthorized", alert=True)
            return
        
        data = event.data.decode('utf-8')
        
        # Route callback
        if data == "main_menu":
            await self._show_menu(event)
        elif data == "sync_signals":
            await event.answer("Syncing signals...")
            await self._cmd_sync_signals("")
        elif data == "bootstrap_signals":
            await event.answer("Starting bootstrap...")
            await self._cmd_bootstrap_signals("")
        elif data.startswith("signalpnl_"):
            period = data.replace("signalpnl_", "")
            await event.answer(f"Loading {period} PnL...")
            await self._cmd_signal_pnl(period)
        elif data.startswith("realpnl_"):
            period = data.replace("realpnl_", "")
            await event.answer(f"Loading {period} real PnL...")
            await self._cmd_real_pnl(period)
        elif data == "help":
            await event.answer()
            await self._cmd_help("")
        else:
            await event.answer("Unknown action")
    
    async def _send_to_admin(self, message: str, buttons=None) -> Optional[any]:
        """Send message to admin."""
        if not self._client or not self._admin_chat_id:
            return None
        
        try:
            return await self._client.send_message(
                self._admin_chat_id,
                message,
                parse_mode='md',
                buttons=buttons,
            )
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
            return None
    
    # =========================================================================
    # Commands
    # =========================================================================
    
    async def _cmd_start(self, args: str) -> None:
        """Handle /start command."""
        await self._send_to_admin(
            "🔔 *MAIN Channel Signal Tracker*\n\n"
            f"Tracking: `{TRENCHES_MAIN_CHANNEL_NAME}`\n"
            f"Channel: @{TRENCHES_MAIN_CHANNEL_USERNAME}\n\n"
            "This bot tracks signals from the MAIN channel and "
            "calculates theoretical PnL statistics.\n\n"
            "Use /menu to see available actions."
        )
    
    async def _cmd_menu(self, args: str) -> None:
        """Show interactive menu."""
        buttons = [
            [Button.inline("🔄 Sync Signals", b"sync_signals")],
            [Button.inline("🔧 Bootstrap (First Time)", b"bootstrap_signals")],
            [
                Button.inline("📊 PnL 7d", b"signalpnl_7"),
                Button.inline("📊 PnL 30d", b"signalpnl_30"),
            ],
            [
                Button.inline("💰 Real PnL 7d", b"realpnl_7"),
                Button.inline("💰 Real PnL 30d", b"realpnl_30"),
            ],
            [Button.inline("❓ Help", b"help")],
        ]
        
        await self._send_to_admin(
            "📋 *MAIN Channel Tracker Menu*\n\n"
            "Select an action:",
            buttons=buttons
        )
    
    async def _show_menu(self, event) -> None:
        """Show menu in callback context."""
        buttons = [
            [Button.inline("🔄 Sync Signals", b"sync_signals")],
            [Button.inline("🔧 Bootstrap (First Time)", b"bootstrap_signals")],
            [
                Button.inline("📊 PnL 7d", b"signalpnl_7"),
                Button.inline("📊 PnL 30d", b"signalpnl_30"),
            ],
            [
                Button.inline("💰 Real PnL 7d", b"realpnl_7"),
                Button.inline("💰 Real PnL 30d", b"realpnl_30"),
            ],
            [Button.inline("❓ Help", b"help")],
        ]
        
        await event.edit(
            "📋 *MAIN Channel Tracker Menu*\n\n"
            "Select an action:",
            buttons=buttons
        )
    
    async def _cmd_help(self, args: str) -> None:
        """Show help message."""
        await self._send_to_admin(
            "📖 *MAIN Channel Tracker Commands*\n\n"
            "**Signal Management**\n"
            "• `/syncsignals` - Sync new signals from channel\n"
            "• `/bootstrap` - One-time full history sync\n\n"
            "**PnL Statistics**\n"
            "• `/signalpnl [days] [size]` - Signal PnL (from alerts)\n"
            "• `/realpnl [days] [size]` - Real-time PnL (from DexScreener)\n\n"
            "**Examples**\n"
            "• `/signalpnl 7` - Last 7 days, 1 SOL/trade\n"
            "• `/signalpnl 7 0.5` - Last 7 days, 0.5 SOL/trade\n"
            "• `/realpnl all` - All time real prices\n"
        )
    
    async def _ensure_user_client_connected(self) -> bool:
        """Ensure user client is connected."""
        if not self._user_client:
            return False
        
        if not self._user_client.is_connected():
            try:
                await self._user_client.connect()
                return True
            except Exception as e:
                logger.error(f"Failed to reconnect user client: {e}")
                return False
        
        return True
    
    async def _check_deleted_messages(self, message_ids: list[int]) -> dict[int, bool]:
        """
        Check if messages have been deleted from the channel.
        
        Args:
            message_ids: List of message IDs to check
            
        Returns:
            Dict mapping message_id -> is_deleted
        """
        if not self._user_client:
            return {mid: False for mid in message_ids}
        
        # Check cache first
        result = {}
        uncached = []
        
        for mid in message_ids:
            if mid in self._deleted_msg_cache:
                result[mid] = self._deleted_msg_cache[mid]
            else:
                uncached.append(mid)
        
        if not uncached:
            return result
        
        # Fetch uncached messages
        try:
            channel = await self._user_client.get_entity(TRENCHES_MAIN_CHANNEL_USERNAME)
            messages = await self._user_client.get_messages(channel, ids=uncached)
            
            for mid, msg in zip(uncached, messages):
                is_deleted = msg is None
                result[mid] = is_deleted
                self._deleted_msg_cache[mid] = is_deleted
                
        except Exception as e:
            logger.warning(f"Failed to check deleted messages: {e}")
            for mid in uncached:
                result[mid] = False
        
        return result
    
    async def _cmd_sync_signals(self, args: str) -> None:
        """
        Sync NEW signals from the MAIN channel to database.
        
        This is the INCREMENTAL sync - only fetches messages AFTER the last cursor.
        """
        if not self._signal_db:
            await self._send_to_admin("❌ Database not configured")
            return
        
        if not await self._ensure_user_client_connected():
            await self._send_to_admin(
                "❌ *User client not connected*\n\n"
                "The Telegram client is disconnected and could not be reconnected.\n"
                "Please restart the bot or check network connectivity."
            )
            return
        
        try:
            # Ensure channel state table exists
            await self._signal_db.ensure_channel_state_table()
            
            # Get the channel entity
            channel = await self._user_client.get_entity(TRENCHES_MAIN_CHANNEL_USERNAME)
            channel_id = channel.id
            
            # Get current cursor state
            state = await self._signal_db.get_channel_state(channel_id)
            last_message_id = state.get("last_message_id", 0)
            bootstrap_completed = state.get("bootstrap_completed", False)
            
            # If bootstrap not completed, prompt user
            if not bootstrap_completed:
                await self._send_to_admin(
                    "⚠️ *Bootstrap Required*\n\n"
                    "No previous sync found. You need to run a one-time bootstrap "
                    "to fetch historical data first.\n\n"
                    "Use the `/bootstrap` command or 🔧 Bootstrap button."
                )
                return
            
            await self._send_to_admin(
                f"🔄 *Syncing NEW signals (MAIN)...*\n\n"
                f"• Last synced message ID: `{last_message_id}`\n"
                f"• Fetching messages after this ID..."
            )
            
            # Signal detection patterns for MAIN channel
            SIGNAL_PATTERN = re.compile(
                r'|'.join(re.escape(ind) for ind in MAIN_BUY_SIGNAL_INDICATORS),
                re.IGNORECASE
            )
            TOKEN_PATTERN = re.compile(r'\$([A-Z0-9]{2,10})')
            ADDRESS_PATTERN = re.compile(TOKEN_ADDRESS_PATTERN)
            MULT_PATTERN = re.compile(MULTIPLIER_PATTERN, re.IGNORECASE)
            PROFIT_PATTERN = re.compile(
                r'|'.join(re.escape(ind) for ind in MAIN_PROFIT_ALERT_INDICATORS),
                re.IGNORECASE
            )
            
            # Fetch ONLY messages AFTER the cursor (incremental)
            messages_to_process = []
            total_fetched = 0
            max_message_id = last_message_id
            
            async for message in self._user_client.iter_messages(
                channel, min_id=last_message_id, limit=None
            ):
                if not message.text:
                    continue
                
                if message.id <= last_message_id:
                    continue
                
                total_fetched += 1
                messages_to_process.append(message)
                max_message_id = max(max_message_id, message.id)
            
            if total_fetched == 0:
                await self._send_to_admin(
                    "✅ *Already up to date!*\n\n"
                    f"No new messages since last sync (ID: `{last_message_id}`)"
                )
                return
            
            # Process messages in chronological order
            messages_to_process.reverse()
            
            new_signals = 0
            new_alerts = 0
            
            for message in messages_to_process:
                text = message.text
                msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                
                # Check if it's a signal (NEW-LAUNCH or MID-SIZED)
                if SIGNAL_PATTERN.search(text):
                    symbol_match = TOKEN_PATTERN.search(text)
                    address_match = ADDRESS_PATTERN.search(text)
                    
                    if address_match:
                        symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
                        address = address_match.group(0)
                        
                        inserted = await self._signal_db.insert_signal(
                            message_id=message.id,
                            token_symbol=symbol,
                            token_address=address,
                            signal_time=msg_time,
                            raw_text=text,
                            channel_name="main",
                        )
                        if inserted:
                            new_signals += 1
                
                # Check if it's a profit alert
                elif PROFIT_PATTERN.search(text) and message.reply_to:
                    reply_to_id = message.reply_to.reply_to_msg_id
                    mult_match = MULT_PATTERN.search(text)
                    
                    if mult_match and reply_to_id:
                        multiplier = float(mult_match.group(1))
                        
                        inserted = await self._signal_db.insert_profit_alert(
                            message_id=message.id,
                            reply_to_msg_id=reply_to_id,
                            multiplier=multiplier,
                            alert_time=msg_time,
                            raw_text=text,
                        )
                        if inserted:
                            new_alerts += 1
            
            # Update cursor
            await self._signal_db.update_channel_cursor(
                channel_id=channel_id,
                channel_name=TRENCHES_MAIN_CHANNEL_NAME,
                last_message_id=max_message_id,
            )
            
            # Get updated counts
            counts = await self._signal_db.get_signal_count()
            
            message = (
                "✅ *Sync Complete (MAIN)!*\n\n"
                f"• Messages Scanned: `{total_fetched}`\n"
                f"• New Signals: `{new_signals}`\n"
                f"• New Profit Alerts: `{new_alerts}`\n"
                f"• New Cursor: `{max_message_id}`\n\n"
                f"📊 *Database Totals (MAIN)*\n"
                f"• Total Signals: `{counts.get('total_signals', 0)}`\n"
                f"• Total Alerts: `{counts.get('total_profit_alerts', 0)}`"
            )
            
            await self._send_to_admin(message)
            logger.info(f"MAIN sync complete: {new_signals} signals, {new_alerts} alerts")
            
        except Exception as e:
            logger.error(f"MAIN sync failed: {e}")
            await self._send_to_admin(f"❌ *Sync failed*\n\n`{str(e)}`")
    
    async def _cmd_bootstrap_signals(self, args: str) -> None:
        """
        One-time FULL bootstrap of historical signals from the MAIN channel.
        
        This should only be run ONCE on first deployment.
        """
        if not self._signal_db:
            await self._send_to_admin("❌ Database not configured")
            return
        
        if not await self._ensure_user_client_connected():
            await self._send_to_admin(
                "❌ *User client not connected*\n\n"
                "Please restart the bot or check network connectivity."
            )
            return
        
        try:
            await self._signal_db.ensure_channel_state_table()
            
            channel = await self._user_client.get_entity(TRENCHES_MAIN_CHANNEL_USERNAME)
            channel_id = channel.id
            
            # Check if already bootstrapped
            state = await self._signal_db.get_channel_state(channel_id)
            if state.get("bootstrap_completed"):
                await self._send_to_admin(
                    "⚠️ *Already Bootstrapped*\n\n"
                    f"Bootstrap was already completed.\n"
                    f"Last message ID: `{state.get('last_message_id', 0)}`\n\n"
                    "Use `/syncsignals` for incremental updates.\n\n"
                    "⚠️ To force re-bootstrap, manually clear the channel_sync_state table."
                )
                return
            
            await self._send_to_admin(
                "🔧 *Starting Bootstrap (MAIN)...*\n\n"
                "⚠️ This may take several minutes for large channel history.\n"
                "Please wait..."
            )
            
            # Signal detection patterns
            SIGNAL_PATTERN = re.compile(
                r'|'.join(re.escape(ind) for ind in MAIN_BUY_SIGNAL_INDICATORS),
                re.IGNORECASE
            )
            TOKEN_PATTERN = re.compile(r'\$([A-Z0-9]{2,10})')
            ADDRESS_PATTERN = re.compile(TOKEN_ADDRESS_PATTERN)
            MULT_PATTERN = re.compile(MULTIPLIER_PATTERN, re.IGNORECASE)
            PROFIT_PATTERN = re.compile(
                r'|'.join(re.escape(ind) for ind in MAIN_PROFIT_ALERT_INDICATORS),
                re.IGNORECASE
            )
            
            # Fetch ALL messages
            messages_to_process = []
            total_fetched = 0
            max_message_id = 0
            
            progress_msg = await self._send_to_admin("🔄 Fetching messages: 0")
            
            async for message in self._user_client.iter_messages(channel, limit=None):
                if not message.text:
                    continue
                
                total_fetched += 1
                messages_to_process.append(message)
                max_message_id = max(max_message_id, message.id)
                
                # Progress update every 500 messages
                if total_fetched % 500 == 0:
                    try:
                        await self._client.edit_message(
                            self._admin_chat_id,
                            progress_msg.id,
                            f"🔄 Fetching messages: {total_fetched}"
                        )
                    except Exception:
                        pass
            
            await self._send_to_admin(
                f"📥 Fetched {total_fetched} messages\n"
                f"🔄 Processing signals..."
            )
            
            # Process in chronological order
            messages_to_process.reverse()
            
            new_signals = 0
            new_alerts = 0
            
            for i, message in enumerate(messages_to_process):
                text = message.text
                msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                
                # Check if it's a signal
                if SIGNAL_PATTERN.search(text):
                    symbol_match = TOKEN_PATTERN.search(text)
                    address_match = ADDRESS_PATTERN.search(text)
                    
                    if address_match:
                        symbol = symbol_match.group(1) if symbol_match else "UNKNOWN"
                        address = address_match.group(0)
                        
                        inserted = await self._signal_db.insert_signal(
                            message_id=message.id,
                            token_symbol=symbol,
                            token_address=address,
                            signal_time=msg_time,
                            raw_text=text,
                            channel_name="main",
                        )
                        if inserted:
                            new_signals += 1
                
                # Check if it's a profit alert
                elif PROFIT_PATTERN.search(text) and message.reply_to:
                    reply_to_id = message.reply_to.reply_to_msg_id
                    mult_match = MULT_PATTERN.search(text)
                    
                    if mult_match and reply_to_id:
                        multiplier = float(mult_match.group(1))
                        
                        inserted = await self._signal_db.insert_profit_alert(
                            message_id=message.id,
                            reply_to_msg_id=reply_to_id,
                            multiplier=multiplier,
                            alert_time=msg_time,
                            raw_text=text,
                        )
                        if inserted:
                            new_alerts += 1
            
            # Mark bootstrap complete
            await self._signal_db.update_channel_cursor(
                channel_id=channel_id,
                channel_name=TRENCHES_MAIN_CHANNEL_NAME,
                last_message_id=max_message_id,
                mark_bootstrap_complete=True,
            )
            
            message = (
                "✅ *Bootstrap Complete (MAIN)!*\n\n"
                f"• Messages Scanned: `{total_fetched}`\n"
                f"• Signals Found: `{new_signals}`\n"
                f"• Profit Alerts Found: `{new_alerts}`\n"
                f"• Max Message ID: `{max_message_id}`\n\n"
                "You can now use `/syncsignals` for incremental updates."
            )
            
            await self._send_to_admin(message)
            logger.info(f"MAIN bootstrap complete: {new_signals} signals, {new_alerts} alerts")
            
        except Exception as e:
            logger.error(f"MAIN bootstrap failed: {e}")
            await self._send_to_admin(f"❌ *Bootstrap failed*\n\n`{str(e)}`")
    
    async def _cmd_signal_pnl(self, args: str) -> None:
        """
        Show PnL statistics for signals (from database profit alerts).
        
        Usage: /signalpnl [days] [position_size]
        """
        # GMGN Fee structure
        BUY_FEE_PCT = 2.5
        SELL_FEE_PCT = 2.5
        DEFAULT_POSITION_SIZE = 1.0
        
        if not self._signal_db:
            await self._send_to_admin(
                "❌ *Signal database not configured*\n\n"
                "Set PostgreSQL environment variables."
            )
            return
        
        # Parse arguments
        parts = args.strip().split() if args else []
        days = None
        position_size = DEFAULT_POSITION_SIZE
        
        if len(parts) >= 1:
            arg = parts[0].lower()
            if arg in ("all", "lifetime"):
                days = None
            else:
                numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
                try:
                    days = int(numeric_arg)
                    if days <= 0:
                        await self._send_to_admin("❌ Invalid period. Use: `/signalpnl 7` or `/signalpnl all`")
                        return
                except ValueError:
                    await self._send_to_admin("❌ Invalid period. Use: `/signalpnl 7` or `/signalpnl all`")
                    return
        
        if len(parts) >= 2:
            try:
                position_size = float(parts[1])
                if position_size <= 0:
                    position_size = DEFAULT_POSITION_SIZE
            except ValueError:
                pass
        
        period_label = f"Last {days} Day{'s' if days != 1 else ''}" if days else "All Time"
        
        await self._send_to_admin(f"⏳ Querying MAIN channel signal database...")
        
        # Get signals with profit data
        signals = await self._signal_db.get_signals_in_period(days)
        
        if not signals:
            await self._send_to_admin(
                f"📭 *No signals found (MAIN)*\n\n"
                f"Period: {period_label}\n\n"
                "Make sure to run `/bootstrap` first."
            )
            return
        
        # Check for deleted messages
        await self._send_to_admin(f"🔍 Checking for deleted signals...")
        message_ids = [s.signal.telegram_msg_id for s in signals]
        deleted_status = await self._check_deleted_messages(message_ids)
        deleted_count = sum(1 for is_deleted in deleted_status.values() if is_deleted)
        
        # Calculate SOL profits
        token_results = []
        total_invested_sol = 0.0
        total_returned_sol = 0.0
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        
        for s in signals:
            mult = s.max_multiplier if s.has_profit else 0
            invested = position_size
            
            if mult == 0:
                returned = 0.0
                sol_profit = -position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                sell_fee = 0.0
            else:
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                tokens_value = position_size - buy_fee
                sell_value = tokens_value * mult
                sell_fee = sell_value * (SELL_FEE_PCT / 100)
                returned = sell_value - sell_fee
                sol_profit = returned - invested
            
            total_invested_sol += invested
            total_returned_sol += returned
            total_buy_fees += buy_fee
            total_sell_fees += sell_fee
            
            is_deleted = deleted_status.get(s.signal.telegram_msg_id, False)
            
            token_results.append({
                'signal': s,
                'multiplier': mult,
                'sol_profit': sol_profit,
                'invested': invested,
                'returned': returned,
                'is_deleted': is_deleted,
            })
        
        # Sort by profit
        token_results.sort(key=lambda x: x['sol_profit'], reverse=True)
        
        # Calculate totals
        total_sol_profit = total_returned_sol - total_invested_sol
        total_pnl_pct = (total_sol_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        total_fees = total_buy_fees + total_sell_fees
        fee_pct_of_invested = (total_fees / total_invested_sol * 100) if total_invested_sol > 0 else 0
        gross_profit = total_sol_profit + total_fees
        gross_pnl_pct = (gross_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        # Stats
        total = len(signals)
        with_profit = [s for s in signals if s.has_profit]
        losers = [s for s in signals if not s.has_profit]
        win_rate = (len(with_profit) / total * 100) if total > 0 else 0
        
        win_emoji = "🟢" if win_rate >= 50 else "🔴"
        pnl_emoji = "🟢" if total_sol_profit >= 0 else "🔴"
        
        # Date range
        timestamps = [s.signal.timestamp for s in signals]
        start_date = min(timestamps) if timestamps else None
        end_date = max(timestamps) if timestamps else None
        
        date_range = ""
        if start_date and end_date:
            date_range = f"📅 `{start_date.strftime('%Y-%m-%d')}` to `{end_date.strftime('%Y-%m-%d')}`\n\n"
        
        header_message = (
            f"📊 *Signal PnL (MAIN)* - {period_label}\n\n"
            f"{date_range}"
            f"💰 *SOL Performance ({position_size} SOL/trade)*\n"
            f"• Total Invested: `{total_invested_sol:.2f}` SOL\n"
            f"• Total Returned: `{total_returned_sol:.2f}` SOL\n"
            f"• {pnl_emoji} Net Profit: `{total_sol_profit:+.2f}` SOL ({total_pnl_pct:+.1f}%)\n\n"
            f"💸 *Fee Breakdown (GMGN)*\n"
            f"• Buy Fees (2.5%): `{total_buy_fees:.2f}` SOL\n"
            f"• Sell Fees (2.5%): `{total_sell_fees:.2f}` SOL\n"
            f"• Total Fees: `{total_fees:.2f}` SOL ({fee_pct_of_invested:.1f}% of invested)\n"
            f"• Gross Profit: `{gross_profit:+.2f}` SOL ({gross_pnl_pct:+.1f}%)\n\n"
            f"📈 *Overview*\n"
            f"• Total Signals: `{total}`\n"
            f"• With Profit Alert: `{len(with_profit)}`\n"
            f"• No Profit Alert: `{len(losers)}`\n"
            f"• 🗑️ Deleted by Channel: `{deleted_count}`\n\n"
            f"📊 *Win/Loss*\n"
            f"• {win_emoji} Win Rate: `{win_rate:.1f}%`\n"
            f"• Winners: `{len(with_profit)}`\n"
            f"• Losers: `{len(losers)}`\n"
        )
        
        await self._send_to_admin(header_message)
        
        # All winners (sorted by profit)
        all_winners = [tr for tr in token_results if tr['sol_profit'] > 0]
        if all_winners:
            winners_text = f"🏆 *All Winners ({len(all_winners)} tokens)*\n\n"
            for i, tr in enumerate(all_winners, 1):
                s = tr['signal']
                deleted_mark = "🗑️ " if tr['is_deleted'] else ""
                winners_text += (
                    f"{i}. {deleted_mark}${s.signal.token_symbol} - "
                    f"`{tr['multiplier']:.1f}x` = `{tr['sol_profit']:+.2f}` SOL\n"
                )
                # Split into multiple messages if too long (Telegram limit ~4096 chars)
                if len(winners_text) > 3500:
                    await self._send_to_admin(winners_text)
                    winners_text = ""
            if winners_text:
                await self._send_to_admin(winners_text)
        
        # Back to menu button
        await self._send_to_admin(
            "Use /menu to return to main menu.",
            buttons=[[Button.inline("📋 Back to Menu", b"main_menu")]]
        )
    
    async def _cmd_real_pnl(self, args: str) -> None:
        """
        Calculate REAL-TIME PnL by fetching current market cap from DexScreener.
        
        Usage: /realpnl [days] [position_size]
        """
        from src.signal_database import calculate_real_pnl
        
        BUY_FEE_PCT = 2.5
        SELL_FEE_PCT = 2.5
        DEFAULT_POSITION_SIZE = 1.0
        
        if not self._signal_db:
            await self._send_to_admin("❌ *Signal database not configured*")
            return
        
        # Parse arguments
        parts = args.strip().split() if args else []
        days = None
        position_size = DEFAULT_POSITION_SIZE
        
        if len(parts) >= 1:
            arg = parts[0].lower()
            if arg in ("all", "lifetime"):
                days = None
            else:
                numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
                try:
                    days = int(numeric_arg)
                    if days <= 0:
                        await self._send_to_admin("❌ Invalid period")
                        return
                except ValueError:
                    await self._send_to_admin("❌ Invalid period")
                    return
        
        if len(parts) >= 2:
            try:
                position_size = float(parts[1])
                if position_size <= 0:
                    position_size = DEFAULT_POSITION_SIZE
            except ValueError:
                pass
        
        period_label = f"Last {days} Days" if days else "All Time"
        
        await self._send_to_admin(f"⏳ Fetching MAIN channel signals from database...")
        signals = await self._signal_db.get_signals_for_real_pnl(days)
        
        if not signals:
            await self._send_to_admin(
                f"📭 *No signals found (MAIN)*\n\n"
                f"Period: {period_label}"
            )
            return
        
        # Check deleted messages
        await self._send_to_admin(f"🔍 Checking for deleted signals...")
        message_ids = [s.telegram_msg_id for s in signals]
        deleted_status = await self._check_deleted_messages(message_ids)
        deleted_count = sum(1 for is_deleted in deleted_status.values() if is_deleted)
        
        # Progress
        progress_msg = await self._send_to_admin(
            f"🔍 Fetching live prices from DexScreener...\n"
            f"Total signals: {len(signals)}\n"
            f"Progress: 0/{len(signals)}"
        )
        
        async def update_progress(current: int, total: int):
            try:
                await self._client.edit_message(
                    self._admin_chat_id,
                    progress_msg.id,
                    f"🔍 Fetching live prices from DexScreener...\n"
                    f"Total signals: {total}\n"
                    f"Progress: {current}/{total}"
                )
            except Exception:
                pass
        
        # Calculate real PnL
        stats = await calculate_real_pnl(signals, update_progress)
        stats.period_label = period_label
        
        # Calculate SOL profits
        token_results = []
        total_invested_sol = 0.0
        total_returned_sol = 0.0
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        
        for r in stats.results:
            if r.multiplier is None or r.is_rugged:
                invested = position_size
                returned = 0.0
                sol_profit = -position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                sell_fee = 0.0
            else:
                invested = position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                tokens_value = position_size - buy_fee
                sell_value = tokens_value * r.multiplier
                sell_fee = sell_value * (SELL_FEE_PCT / 100)
                returned = sell_value - sell_fee
                sol_profit = returned - invested
            
            total_invested_sol += invested
            total_returned_sol += returned
            total_buy_fees += buy_fee
            total_sell_fees += sell_fee
            
            is_deleted = deleted_status.get(r.signal.telegram_msg_id, False)
            
            token_results.append({
                'result': r,
                'sol_profit': sol_profit,
                'invested': invested,
                'returned': returned,
                'is_deleted': is_deleted,
            })
        
        token_results.sort(key=lambda x: x['sol_profit'], reverse=True)
        
        # Calculate totals
        total_sol_profit = total_returned_sol - total_invested_sol
        total_pnl_pct = (total_sol_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        total_fees = total_buy_fees + total_sell_fees
        fee_pct_of_invested = (total_fees / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        win_rate = (stats.winners / stats.successful_fetches * 100) if stats.successful_fetches else 0
        win_emoji = "🟢" if win_rate >= 50 else "🔴"
        pnl_emoji = "🟢" if total_sol_profit >= 0 else "🔴"
        
        date_range = ""
        if stats.start_date and stats.end_date:
            date_range = f"📅 `{stats.start_date.strftime('%Y-%m-%d')}` to `{stats.end_date.strftime('%Y-%m-%d')}`\n\n"
        
        gross_profit = total_sol_profit + total_fees
        gross_pnl_pct = (gross_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        header_message = (
            f"📊 *Real-Time PnL (MAIN)* - {period_label}\n\n"
            f"{date_range}"
            f"💰 *SOL Performance ({position_size} SOL/trade)*\n"
            f"• Total Invested: `{total_invested_sol:.2f}` SOL\n"
            f"• Total Returned: `{total_returned_sol:.2f}` SOL\n"
            f"• {pnl_emoji} Net Profit: `{total_sol_profit:+.2f}` SOL ({total_pnl_pct:+.1f}%)\n\n"
            f"💸 *Fee Breakdown (GMGN)*\n"
            f"• Buy Fees (2.5%): `{total_buy_fees:.2f}` SOL\n"
            f"• Sell Fees (2.5%): `{total_sell_fees:.2f}` SOL\n"
            f"• Total Fees: `{total_fees:.2f}` SOL ({fee_pct_of_invested:.1f}% of invested)\n"
            f"• Gross Profit: `{gross_profit:+.2f}` SOL ({gross_pnl_pct:+.1f}%)\n\n"
            f"📈 *Overview*\n"
            f"• Total Signals: `{stats.total_signals}`\n"
            f"• Priced OK: `{stats.successful_fetches}`\n"
            f"• Rugged: `{stats.rugged_count}` 💀\n"
            f"• 🗑️ Deleted by Channel: `{deleted_count}`\n\n"
            f"📊 *Win/Loss*\n"
            f"• {win_emoji} Win Rate: `{win_rate:.1f}%`\n"
            f"• Winners (≥1X): `{stats.winners}`\n"
            f"• Losers (<1X): `{stats.losers}`\n"
        )
        
        await self._send_to_admin(header_message)
        
        # All winners (sorted by profit)
        all_winners = [tr for tr in token_results if tr['sol_profit'] > 0]
        if all_winners:
            winners_text = f"🏆 *All Winners ({len(all_winners)} tokens)*\n\n"
            for i, tr in enumerate(all_winners, 1):
                r = tr['result']
                deleted_mark = "🗑️ " if tr['is_deleted'] else ""
                mult = r.multiplier if r.multiplier else 0
                winners_text += (
                    f"{i}. {deleted_mark}${r.signal.token_symbol} - "
                    f"`{mult:.1f}x` = `{tr['sol_profit']:+.2f}` SOL\n"
                )
                # Split into multiple messages if too long (Telegram limit ~4096 chars)
                if len(winners_text) > 3500:
                    await self._send_to_admin(winners_text)
                    winners_text = ""
            if winners_text:
                await self._send_to_admin(winners_text)
        
        await self._send_to_admin(
            "Use /menu to return to main menu.",
            buttons=[[Button.inline("📋 Back to Menu", b"main_menu")]]
        )
