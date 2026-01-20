"""
Telegram Bot for notifications and remote control.

This module provides a proper Telegram Bot (via BotFather) for:
- Sending notifications to channels/groups
- Remote control commands from admin
- Wallet setup and configuration
- PnL tracking and reporting (from PostgreSQL database)
- Interactive button menu
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat
from telethon.tl.custom import Button

from src.signal_history import SignalHistory
from src.signal_database import SignalDatabase

if TYPE_CHECKING:
    from src.bot import TradingBot
    from src.config import Settings

logger = logging.getLogger(__name__)

# Solana address pattern (base58, 32-44 chars)
SOLANA_ADDRESS_PATTERN = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


def is_valid_solana_address(address: str) -> bool:
    """Check if string is a valid Solana address."""
    return bool(SOLANA_ADDRESS_PATTERN.match(address))


class NotificationBot:
    """
    Telegram Bot for notifications and control.
    
    Uses a bot token from BotFather to:
    - Send notifications to a channel/group
    - Accept commands from admin users
    - Handle wallet setup on start
    - Track and report PnL statistics
    - Interactive button menu
    
    Commands (admin only):
        /start - Welcome and wallet setup
        /menu - Show interactive button menu
        /status - Bot status
        /positions - Open positions  
        /pnl - Current positions PnL
        /signalpnl [1d|7d|30d|all] - Signal PnL statistics
        /syncsignals - Sync latest signals from channel
        /settings - Current settings
        /setsize <SOL> - Set buy amount
        /setsell <percent> - Set sell percentage
        /setmultiplier <X> - Set min multiplier
        /setmax <count> - Set max positions
        /setwallet <address> - Set GMGN wallet
        /pause - Pause trading
        /resume - Resume trading
        /help - Show commands
    """
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        settings: "Settings",
        admin_user_id: int,
        notification_channel: Optional[str] = None,
    ) -> None:
        """
        Initialize the notification bot.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API hash
            bot_token: Bot token from BotFather
            settings: Application settings
            admin_user_id: Telegram user ID of admin
            notification_channel: Channel/group username or ID for notifications
        """
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._settings = settings
        self._admin_user_id = admin_user_id
        self._notification_channel = notification_channel
        
        self._client: Optional[TelegramClient] = None
        self._bot: Optional["TradingBot"] = None
        self._channel_entity: Optional[Channel | Chat] = None
        self._initialized = False
        
        # Dynamic settings
        self._buy_amount_sol: float = settings.trading_buy_amount_sol
        self._sell_percentage: int = settings.trading_sell_percentage
        self._min_multiplier: float = settings.trading_min_multiplier
        self._max_positions: int = settings.trading_max_positions
        self._gmgn_wallet: Optional[str] = settings.gmgn_wallet
        self._trading_paused = False
        
        # Pending wallet setup
        self._awaiting_wallet = False
        
        # Awaiting custom days input for signal PnL
        self._awaiting_custom_days = False
        
        # Signal history for PnL tracking (local file-based)
        self._signal_history = SignalHistory()
        self._signal_history.load()
        
        # Signal database for historical PnL from PostgreSQL
        self._signal_db: Optional[SignalDatabase] = None
        db_dsn = self._build_database_dsn()
        if db_dsn:
            self._signal_db = SignalDatabase(db_dsn)
    
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
    def signal_history(self) -> SignalHistory:
        """Get signal history tracker."""
        return self._signal_history
    
    @property
    def signal_db(self) -> Optional[SignalDatabase]:
        """Get signal database."""
        return self._signal_db
    
    def set_trading_bot(self, bot: "TradingBot") -> None:
        """Set the trading bot reference."""
        self._bot = bot
    
    @property
    def buy_amount_sol(self) -> float:
        return self._buy_amount_sol
    
    @property
    def sell_percentage(self) -> int:
        return self._sell_percentage
    
    @property
    def min_multiplier(self) -> float:
        return self._min_multiplier
    
    @property
    def max_positions(self) -> int:
        return self._max_positions
    
    @property
    def gmgn_wallet(self) -> Optional[str]:
        return self._gmgn_wallet
    
    @property
    def is_trading_paused(self) -> bool:
        return self._trading_paused
    
    @property
    def is_wallet_configured(self) -> bool:
        return self._gmgn_wallet is not None
    
    async def start(self) -> None:
        """Start the bot client."""
        if self._initialized:
            return
        
        # Create bot client
        self._client = TelegramClient(
            StringSession(),  # Use in-memory session for bot
            self._api_id,
            self._api_hash,
        )
        
        await self._client.start(bot_token=self._bot_token)
        
        # Get bot info
        me = await self._client.get_me()
        logger.info(f"✅ Notification bot started: @{me.username}")
        
        # Set up bot commands menu (persistent menu next to text input)
        await self._setup_bot_commands()
        
        # Connect to signal database
        if self._signal_db:
            if await self._signal_db.connect():
                counts = await self._signal_db.get_signal_count()
                logger.info(
                    f"✅ Signal database connected: "
                    f"{counts.get('total_signals', 0)} signals, "
                    f"{counts.get('total_profit_alerts', 0)} alerts"
                )
            else:
                logger.warning("Signal database connection failed, using local tracking only")
        
        # Resolve notification channel
        if self._notification_channel:
            try:
                # Convert to int if it looks like a numeric ID
                channel_id = self._notification_channel
                if isinstance(channel_id, str) and channel_id.lstrip('-').isdigit():
                    channel_id = int(channel_id)
                
                self._channel_entity = await self._client.get_entity(channel_id)
                logger.info(f"✅ Notifications will be sent to: {self._get_entity_name()}")
            except Exception as e:
                logger.warning(f"Could not resolve notification channel: {e}")
                logger.info("Notifications will be sent to admin DM instead")
        
        # Register handlers
        self._client.add_event_handler(
            self._handle_message,
            events.NewMessage()
        )
        
        # Register callback query handler for button clicks
        self._client.add_event_handler(
            self._handle_callback,
            events.CallbackQuery()
        )
        
        self._initialized = True
        
        # Send startup message
        await self._send_startup_message()
    
    async def _setup_bot_commands(self) -> None:
        """Set up the bot commands menu (shown next to text input)."""
        from telethon.tl.functions.bots import SetBotCommandsRequest
        from telethon.tl.types import BotCommand, BotCommandScopeDefault
        
        commands = [
            BotCommand(command="menu", description="📱 Show interactive menu"),
            BotCommand(command="status", description="📊 Bot status"),
            BotCommand(command="positions", description="📈 Open positions"),
            BotCommand(command="pnl", description="💰 Current PnL"),
            BotCommand(command="signalpnl", description="📉 Signal PnL (1d/3d/7d/30d/all)"),
            BotCommand(command="syncsignals", description="🔄 Sync signals from channel"),
            BotCommand(command="settings", description="⚙️ Current settings"),
            BotCommand(command="pause", description="⏸️ Pause trading"),
            BotCommand(command="resume", description="▶️ Resume trading"),
            BotCommand(command="help", description="❓ Show all commands"),
        ]
        
        try:
            await self._client(SetBotCommandsRequest(
                scope=BotCommandScopeDefault(),
                lang_code="",
                commands=commands,
            ))
            logger.info("✅ Bot commands menu set up")
        except Exception as e:
            logger.warning(f"Could not set bot commands: {e}")
    
    async def stop(self) -> None:
        """Stop the bot client."""
        if self._client:
            await self._client.disconnect()
            self._initialized = False
        
        # Close signal history HTTP client
        await self._signal_history.close()
        
        # Disconnect from signal database
        if self._signal_db:
            await self._signal_db.disconnect()
    
    def _get_entity_name(self) -> str:
        """Get display name of notification channel."""
        if not self._channel_entity:
            return "Unknown"
        if hasattr(self._channel_entity, 'title'):
            return self._channel_entity.title
        return str(self._notification_channel)
    
    async def _send_startup_message(self) -> None:
        """Send startup notification."""
        if not self._gmgn_wallet:
            # Send to channel that wallet is not configured
            await self._send_notification(
                "🤖 *Solana Trading Bot Started*\n\n"
                "⚠️ *Wallet not configured!*\n\n"
                "Admin: Please send your GMGN SOL wallet address via DM to the bot.\n\n"
                "Example: `HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH`"
            )
            self._awaiting_wallet = True
        else:
            await self._send_notification(
                "🤖 *Trading Bot Started*\n\n"
                f"• Wallet: `{self._gmgn_wallet[:8]}...{self._gmgn_wallet[-6:]}`\n"
                f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
                f"• Sell At: `{self._min_multiplier}X`\n"
                f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`\n\n"
                "Bot is ready for trading!"
            )
    
    async def _send_notification(self, message: str) -> None:
        """Send notification to channel or admin."""
        if not self._client:
            return
        
        try:
            target = self._channel_entity if self._channel_entity else self._admin_user_id
            await self._client.send_message(
                target,
                message,
                parse_mode="markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    async def _send_to_admin(self, message: str) -> None:
        """Send message directly to admin (for setup/private commands)."""
        if not self._client:
            return
        
        try:
            await self._client.send_message(
                self._admin_user_id,
                message,
                parse_mode="markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
    
    async def notify_signal(
        self,
        token_symbol: str,
        token_address: str,
        signal_type: str = "BUY",
    ) -> None:
        """Notify about a new signal."""
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        
        # Create clickable links
        dexscreener_link = f"https://dexscreener.com/solana/{token_address}"
        gmgn_link = f"https://gmgn.ai/sol/token/{token_address}"
        
        message = (
            f"{emoji} *NEW {signal_type} SIGNAL*\n\n"
            f"• Token: `${token_symbol}`\n"
            f"• CA: `{token_address}`\n"
            f"• Time: `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`\n\n"
            f"📊 [DexScreener]({dexscreener_link}) | 🔍 [GMGN]({gmgn_link})"
        )
        
        if self._trading_paused:
            message += "\n\n⚠️ _Trading PAUSED - no action taken_"
        elif not self._gmgn_wallet:
            message += "\n\n⚠️ _Wallet not configured - no action taken_"
        
        await self._send_notification(message)
    
    async def notify_trade(
        self,
        action: str,
        token_symbol: str,
        amount_sol: float,
        success: bool,
        multiplier: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Notify about trade execution."""
        if success:
            emoji = "✅" if action == "BUY" else "💰"
            status = "SUCCESS"
        else:
            emoji = "❌"
            status = "FAILED"
        
        dry_run = self._settings.trading_dry_run
        mode = "🔵 DRY RUN" if dry_run else "🔴 LIVE"
        
        message = (
            f"{emoji} *TRADE {action} - {status}*\n\n"
            f"• Token: `${token_symbol}`\n"
            f"• Amount: `{amount_sol} SOL`\n"
        )
        
        if multiplier:
            pnl_percent = (multiplier - 1) * 100
            message += f"• Multiplier: `{multiplier}X` (+{pnl_percent:.1f}%)\n"
        
        message += f"• Mode: {mode}"
        
        if error:
            message += f"\n• Error: `{error}`"
        
        await self._send_notification(message)
    
    async def notify_profit_alert(
        self,
        token_symbol: str,
        multiplier: float,
        will_sell: bool,
    ) -> None:
        """Notify about profit alert."""
        emoji = "📈" if will_sell else "📊"
        action = "SELLING" if will_sell else "HOLDING"
        pnl_percent = (multiplier - 1) * 100
        
        message = (
            f"{emoji} *PROFIT ALERT*\n\n"
            f"• Token: `${token_symbol}`\n"
            f"• Multiplier: `{multiplier}X` (+{pnl_percent:.1f}%)\n"
            f"• Threshold: `{self._min_multiplier}X`\n"
            f"• Action: `{action}`"
        )
        
        if self._trading_paused and will_sell:
            message += "\n\n⚠️ _Trading PAUSED - no sell executed_"
        
        await self._send_notification(message)
    
    async def _handle_message(self, event: events.NewMessage.Event) -> None:
        """Handle incoming messages."""
        message = event.message
        sender = await event.get_sender()
        
        # Only process messages from admin
        if not sender or sender.id != self._admin_user_id:
            return
        
        if not message.text:
            return
        
        text = message.text.strip()
        
        # Check if awaiting wallet
        if self._awaiting_wallet and not text.startswith("/"):
            await self._handle_wallet_input(text)
            return
        
        # Check if awaiting custom days input
        if self._awaiting_custom_days and not text.startswith("/"):
            await self._handle_custom_days_input(text)
            return
        
        # Handle commands
        if text.startswith("/"):
            await self._handle_command(text)
    
    async def _handle_wallet_input(self, text: str) -> None:
        """Handle wallet address input during setup."""
        address = text.strip()
        
        if not is_valid_solana_address(address):
            await self._send_to_admin(
                "❌ *Invalid wallet address*\n\n"
                "Please send a valid Solana wallet address (32-44 characters, base58).\n\n"
                "Example: `HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH`"
            )
            return
        
        self._gmgn_wallet = address
        self._awaiting_wallet = False
        
        await self._send_notification(
            "✅ *Wallet Configured!*\n\n"
            f"• Wallet: `{address[:8]}...{address[-6:]}`\n\n"
            "The bot is now ready to trade.\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Sell At: `{self._min_multiplier}X`\n"
            f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`\n\n"
            "Use /help to see all commands."
        )
        
        logger.info(f"✅ GMGN wallet configured: {address[:8]}...{address[-6:]}")
    
    async def _prompt_custom_days(self) -> None:
        """Prompt user to enter custom number of days for signal PnL."""
        self._awaiting_custom_days = True
        await self._send_to_admin(
            "📅 *Enter Custom Day Range*\n\n"
            "Please enter the number of days for signal PnL analysis:\n\n"
            "• Enter a number (e.g., `3`, `7`, `14`, `30`, `90`)\n"
            "• Or type `all` for lifetime\n\n"
            "_Send /menu to cancel_"
        )
    
    async def _handle_custom_days_input(self, text: str) -> None:
        """Handle custom days input for signal PnL."""
        self._awaiting_custom_days = False
        
        text = text.strip().lower()
        
        if text == "all" or text == "lifetime":
            await self._cmd_signal_pnl("all")
            return
        
        try:
            days = int(text)
            if days <= 0:
                await self._send_to_admin(
                    "❌ *Invalid input*\n\n"
                    "Please enter a positive number of days.\n"
                    "Use /menu to try again."
                )
                return
            
            if days > 3650:  # Max 10 years
                await self._send_to_admin(
                    "❌ *Too many days*\n\n"
                    "Maximum allowed is 3650 days (10 years).\n"
                    "Use /menu to try again."
                )
                return
            
            # Call signal PnL with custom days
            await self._cmd_signal_pnl(str(days))
            
        except ValueError:
            await self._send_to_admin(
                "❌ *Invalid input*\n\n"
                "Please enter a valid number or `all`.\n"
                "Use /menu to try again."
            )

    async def _handle_command(self, text: str) -> None:
        """Handle bot commands."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # Remove bot username if present
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/start": self._cmd_start,
            "/menu": self._cmd_menu,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/positions": self._cmd_positions,
            "/pnl": self._cmd_pnl,
            "/signalpnl": self._cmd_signal_pnl,
            "/syncsignals": self._cmd_sync_signals,
            "/settings": self._cmd_settings,
            "/setsize": self._cmd_set_size,
            "/setsell": self._cmd_set_sell,
            "/setmultiplier": self._cmd_set_multiplier,
            "/setmax": self._cmd_set_max,
            "/setwallet": self._cmd_set_wallet,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/stats": self._cmd_stats,
        }
        
        handler = handlers.get(command)
        if handler:
            await handler(args)
        else:
            await self._send_to_admin(
                f"❓ Unknown command: `{command}`\n\nUse /help for available commands."
            )
    
    async def _cmd_start(self, args: str) -> None:
        """Welcome message."""
        if not self._gmgn_wallet:
            await self._send_to_admin(
                "🤖 *Solana Trading Bot*\n\n"
                "Welcome! To start trading, please send your GMGN SOL wallet address.\n\n"
                "Example: `HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH`"
            )
            self._awaiting_wallet = True
        else:
            await self._send_to_admin(
                "🤖 *Solana Trading Bot*\n\n"
                f"• Wallet: `{self._gmgn_wallet[:8]}...{self._gmgn_wallet[-6:]}`\n"
                f"• Status: `{'Running' if self._bot and self._bot.is_running else 'Stopped'}`\n\n"
                "Use /menu to see interactive menu or /help for commands."
            )
    
    def _get_menu_buttons(self) -> list:
        """Get the main menu buttons."""
        return [
            [
                Button.inline("📊 Status", b"cmd_status"),
                Button.inline("📈 Positions", b"cmd_positions"),
            ],
            [
                Button.inline("💰 PnL", b"cmd_pnl"),
                Button.inline("⚙️ Settings", b"cmd_settings"),
            ],
            [
                Button.inline("📉 Signal PnL (All)", b"signalpnl_all"),
                Button.inline("📉 Signal PnL (Custom)", b"signalpnl_custom"),
            ],
            [
                Button.inline("🔄 Sync Signals", b"cmd_sync_signals"),
                Button.inline("📊 Stats", b"cmd_stats"),
            ],
            [
                Button.inline("⏸️ Pause", b"cmd_pause"),
                Button.inline("▶️ Resume", b"cmd_resume"),
            ],
            [
                Button.inline("❓ Help", b"cmd_help"),
            ],
        ]
    
    async def _cmd_menu(self, args: str) -> None:
        """Show interactive menu with buttons."""
        trading_status = "🟢 Running" if not self._trading_paused else "⏸️ Paused"
        wallet_status = f"`{self._gmgn_wallet[:8]}...`" if self._gmgn_wallet else "❌ Not set"
        
        message = (
            "🤖 *SOLANA TRADING BOT MENU*\n\n"
            f"• Status: {trading_status}\n"
            f"• Wallet: {wallet_status}\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Sell At: `{self._min_multiplier}X`\n"
            f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`\n\n"
            "_Select an option below:_"
        )
        
        await self._send_to_admin_with_buttons(message, self._get_menu_buttons())
    
    async def _send_to_admin_with_buttons(self, message: str, buttons: list) -> None:
        """Send message to admin with inline buttons."""
        if not self._client:
            return
        
        try:
            await self._client.send_message(
                self._admin_user_id,
                message,
                parse_mode="markdown",
                buttons=buttons,
            )
        except Exception as e:
            logger.error(f"Failed to send to admin with buttons: {e}")
    
    async def _handle_callback(self, event: events.CallbackQuery.Event) -> None:
        """Handle button callback queries."""
        sender = await event.get_sender()
        
        # Only process callbacks from admin
        if not sender or sender.id != self._admin_user_id:
            await event.answer("⚠️ You are not authorized", alert=True)
            return
        
        data = event.data.decode('utf-8')
        
        # Acknowledge the callback
        await event.answer()
        
        # Map callback data to handlers
        callback_handlers = {
            "cmd_status": lambda: self._cmd_status(""),
            "cmd_positions": lambda: self._cmd_positions(""),
            "cmd_pnl": lambda: self._cmd_pnl(""),
            "cmd_settings": lambda: self._cmd_settings(""),
            "cmd_stats": lambda: self._cmd_stats(""),
            "cmd_help": lambda: self._cmd_help(""),
            "cmd_pause": lambda: self._cmd_pause(""),
            "cmd_resume": lambda: self._cmd_resume(""),
            "cmd_sync_signals": lambda: self._cmd_sync_signals(""),
            "signalpnl_all": lambda: self._cmd_signal_pnl("all"),
            "signalpnl_custom": lambda: self._prompt_custom_days(),
            "back_to_menu": lambda: self._cmd_menu(""),
        }
        
        handler = callback_handlers.get(data)
        if handler:
            await handler()
        else:
            await self._send_to_admin(f"❓ Unknown action: {data}")
    
    async def _cmd_help(self, args: str) -> None:
        """Show help."""
        help_text = (
            "📚 *AVAILABLE COMMANDS*\n\n"
            "*Menu:*\n"
            "• /menu - Interactive button menu\n\n"
            "*Status & Monitoring:*\n"
            "• /status - Bot status\n"
            "• /positions - Open positions\n"
            "• /stats - Trading statistics\n\n"
            "*PnL Tracking:*\n"
            "• /pnl - Current positions PnL\n"
            "• /signalpnl `<days>` - Signal PnL for N days\n"
            "• /signalpnl `all` - Lifetime signals PnL\n"
            "• /syncsignals - Sync latest from channel\n\n"
            "*Control:*\n"
            "• /pause - Pause trading\n"
            "• /resume - Resume trading\n\n"
            "*Configuration:*\n"
            "• /setsize `<SOL>` - Buy amount\n"
            "• /setsell `<percent>` - Sell percentage\n"
            "• /setmultiplier `<X>` - Min sell multiplier\n"
            "• /setmax `<count>` - Max positions\n"
            "• /setwallet `<address>` - GMGN wallet\n\n"
            "_Tip: Use /menu for interactive buttons!_"
        )
        await self._send_to_admin(help_text)
    
    async def _cmd_status(self, args: str) -> None:
        """Show status."""
        if not self._bot:
            await self._send_to_admin("❌ Trading bot not connected")
            return
        
        status = self._bot.get_status()
        uptime_sec = status.get("uptime_seconds", 0)
        
        if uptime_sec:
            hours = int(uptime_sec // 3600)
            minutes = int((uptime_sec % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = "N/A"
        
        running = "🟢 Running" if status.get("running") else "🔴 Stopped"
        trading = "⏸️ Paused" if self._trading_paused else "▶️ Active"
        wallet = f"`{self._gmgn_wallet[:8]}...`" if self._gmgn_wallet else "❌ Not set"
        
        message = (
            f"📊 *BOT STATUS*\n\n"
            f"• Status: {running}\n"
            f"• Trading: {trading}\n"
            f"• Wallet: {wallet}\n"
            f"• Dry Run: `{'Yes' if status.get('dry_run') else 'No'}`\n"
            f"• Uptime: `{uptime_str}`\n"
            f"• Messages: `{status.get('messages_processed', 0)}`\n"
            f"• Trades: `{status.get('trades_executed', 0)}`"
        )
        
        await self._send_to_admin(message)
    
    async def _cmd_positions(self, args: str) -> None:
        """Show positions."""
        if not self._bot or not self._bot.state:
            await self._send_to_admin("❌ No position data available")
            return
        
        positions = self._bot.state.open_positions
        
        if not positions:
            await self._send_to_admin("📭 *No open positions*")
            return
        
        message = f"📈 *OPEN POSITIONS ({len(positions)})*\n\n"
        
        for addr, pos in positions.items():
            pnl_percent = (pos.last_multiplier - 1) * 100
            message += (
                f"• `${pos.token_symbol}`\n"
                f"  Buy: `{pos.buy_amount_sol} SOL`\n"
                f"  PnL: `{pos.last_multiplier}X` ({pnl_percent:+.1f}%)\n"
                f"  Holding: `{pos.holding_duration:.1f}h`\n\n"
            )
        
        await self._send_to_admin(message)
    
    async def _cmd_settings(self, args: str) -> None:
        """Show settings."""
        wallet = f"`{self._gmgn_wallet[:8]}...{self._gmgn_wallet[-6:]}`" if self._gmgn_wallet else "❌ Not set"
        
        message = (
            "⚙️ *TRADING SETTINGS*\n\n"
            f"• Wallet: {wallet}\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Sell %: `{self._sell_percentage}%`\n"
            f"• Min Multiplier: `{self._min_multiplier}X`\n"
            f"• Max Positions: `{self._max_positions}`\n"
            f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`\n"
            f"• Paused: `{'Yes' if self._trading_paused else 'No'}`"
        )
        
        await self._send_to_admin(message)
    
    async def _cmd_set_size(self, args: str) -> None:
        """Set buy amount."""
        if not args:
            await self._send_to_admin(
                f"❌ Usage: `/setsize <SOL>`\n\nCurrent: `{self._buy_amount_sol} SOL`"
            )
            return
        
        try:
            amount = float(args.strip())
            if amount < 0.001 or amount > 100:
                await self._send_to_admin("❌ Amount must be between `0.001` and `100` SOL")
                return
            
            old = self._buy_amount_sol
            self._buy_amount_sol = amount
            await self._send_notification(
                f"✅ *Buy amount updated*\n\n• `{old} SOL` → `{amount} SOL`"
            )
        except ValueError:
            await self._send_to_admin("❌ Invalid amount")
    
    async def _cmd_set_sell(self, args: str) -> None:
        """Set sell percentage."""
        if not args:
            await self._send_to_admin(
                f"❌ Usage: `/setsell <percent>`\n\nCurrent: `{self._sell_percentage}%`"
            )
            return
        
        try:
            percent = int(args.strip().rstrip("%"))
            if percent < 1 or percent > 100:
                await self._send_to_admin("❌ Percentage must be between `1` and `100`")
                return
            
            old = self._sell_percentage
            self._sell_percentage = percent
            await self._send_notification(
                f"✅ *Sell percentage updated*\n\n• `{old}%` → `{percent}%`"
            )
        except ValueError:
            await self._send_to_admin("❌ Invalid percentage")
    
    async def _cmd_set_multiplier(self, args: str) -> None:
        """Set min multiplier."""
        if not args:
            await self._send_to_admin(
                f"❌ Usage: `/setmultiplier <X>`\n\nCurrent: `{self._min_multiplier}X`"
            )
            return
        
        try:
            value = float(args.strip().rstrip("Xx"))
            if value < 1.1 or value > 100:
                await self._send_to_admin("❌ Multiplier must be between `1.1X` and `100X`")
                return
            
            old = self._min_multiplier
            self._min_multiplier = value
            await self._send_notification(
                f"✅ *Min multiplier updated*\n\n• `{old}X` → `{value}X`"
            )
        except ValueError:
            await self._send_to_admin("❌ Invalid multiplier")
    
    async def _cmd_set_max(self, args: str) -> None:
        """Set max positions."""
        if not args:
            await self._send_to_admin(
                f"❌ Usage: `/setmax <count>`\n\nCurrent: `{self._max_positions}`"
            )
            return
        
        try:
            count = int(args.strip())
            if count < 1 or count > 100:
                await self._send_to_admin("❌ Max positions must be between `1` and `100`")
                return
            
            old = self._max_positions
            self._max_positions = count
            await self._send_notification(
                f"✅ *Max positions updated*\n\n• `{old}` → `{count}`"
            )
        except ValueError:
            await self._send_to_admin("❌ Invalid count")
    
    async def _cmd_set_wallet(self, args: str) -> None:
        """Set GMGN wallet."""
        if not args:
            wallet = f"`{self._gmgn_wallet}`" if self._gmgn_wallet else "Not set"
            await self._send_to_admin(
                f"❌ Usage: `/setwallet <address>`\n\nCurrent: {wallet}"
            )
            return
        
        address = args.strip()
        if not is_valid_solana_address(address):
            await self._send_to_admin("❌ Invalid Solana wallet address")
            return
        
        old = self._gmgn_wallet
        self._gmgn_wallet = address
        self._awaiting_wallet = False
        
        old_display = f"`{old[:8]}...`" if old else "None"
        await self._send_notification(
            f"✅ *Wallet updated*\n\n"
            f"• Old: {old_display}\n"
            f"• New: `{address[:8]}...{address[-6:]}`"
        )
        
        logger.info(f"✅ GMGN wallet updated: {address[:8]}...{address[-6:]}")
    
    async def _cmd_pause(self, args: str) -> None:
        """Pause trading."""
        if self._trading_paused:
            await self._send_to_admin("⚠️ Trading is already paused")
            return
        
        self._trading_paused = True
        await self._send_notification(
            "⏸️ *TRADING PAUSED*\n\n"
            "The bot will monitor signals but won't execute trades.\n"
            "Use /resume to continue."
        )
    
    async def _cmd_resume(self, args: str) -> None:
        """Resume trading."""
        if not self._trading_paused:
            await self._send_to_admin("⚠️ Trading is not paused")
            return
        
        if not self._gmgn_wallet:
            await self._send_to_admin(
                "❌ Cannot resume - wallet not configured.\n\n"
                "Use /setwallet `<address>` first."
            )
            return
        
        self._trading_paused = False
        await self._send_notification(
            "▶️ *TRADING RESUMED*\n\n"
            f"• Wallet: `{self._gmgn_wallet[:8]}...`\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`"
        )
    
    async def _cmd_stats(self, args: str) -> None:
        """Show statistics."""
        if not self._bot or not self._bot.state:
            await self._send_to_admin("❌ No statistics available")
            return
        
        stats = self._bot.state.get_statistics()
        
        message = (
            "📊 *TRADING STATISTICS*\n\n"
            f"• Total Positions: `{stats.get('total_positions', 0)}`\n"
            f"• Open: `{stats.get('open_positions', 0)}`\n"
            f"• Closed: `{stats.get('closed_positions', 0)}`\n"
            f"• Partial Sold: `{stats.get('partial_sold_positions', 0)}`"
        )
        
        if "total_invested_sol" in stats:
            message += f"\n• Total Invested: `{stats['total_invested_sol']:.4f} SOL`"
        
        await self._send_to_admin(message)
    
    async def _cmd_pnl(self, args: str) -> None:
        """Show PnL for current open positions."""
        if not self._bot or not self._bot.state:
            await self._send_to_admin("❌ No position data available")
            return
        
        positions = self._bot.state.open_positions
        
        if not positions:
            await self._send_to_admin("📭 *No open positions*\n\nNo PnL to calculate.")
            return
        
        await self._send_to_admin("⏳ Fetching current prices...")
        
        # Update prices for all open positions
        addresses = list(positions.keys())
        await self._signal_history.update_prices(addresses)
        
        total_invested = 0.0
        total_current_value = 0.0
        position_lines = []
        
        for addr, pos in positions.items():
            signal = self._signal_history.signals.get(addr)
            
            total_invested += pos.buy_amount_sol
            
            if signal and signal.multiplier:
                mult = signal.multiplier
                pnl_pct = signal.pnl_percent or 0
                current_val = pos.buy_amount_sol * mult * (pos.remaining_percentage / 100)
                total_current_value += current_val
                
                emoji = "🟢" if mult >= 1 else "🔴"
                position_lines.append(
                    f"{emoji} `${pos.token_symbol}`\n"
                    f"   Entry: `{signal.entry_price_sol:.10f}` SOL\n"
                    f"   Current: `{signal.current_price_sol:.10f}` SOL\n"
                    f"   PnL: `{mult:.2f}X` ({pnl_pct:+.1f}%)\n"
                    f"   Value: `{current_val:.4f}` SOL"
                )
            else:
                # Use position's last multiplier if no signal history
                mult = pos.last_multiplier
                pnl_pct = (mult - 1) * 100
                current_val = pos.buy_amount_sol * mult * (pos.remaining_percentage / 100)
                total_current_value += current_val
                
                emoji = "🟢" if mult >= 1 else "🔴"
                position_lines.append(
                    f"{emoji} `${pos.token_symbol}`\n"
                    f"   PnL: `{mult:.2f}X` ({pnl_pct:+.1f}%)\n"
                    f"   Value: `{current_val:.4f}` SOL"
                )
        
        total_pnl_sol = total_current_value - total_invested
        total_pnl_pct = ((total_current_value / total_invested) - 1) * 100 if total_invested > 0 else 0
        
        overall_emoji = "🟢" if total_pnl_sol >= 0 else "🔴"
        
        message = (
            f"💰 *POSITIONS PnL ({len(positions)} open)*\n\n"
            + "\n\n".join(position_lines)
            + f"\n\n{'─' * 30}\n"
            f"{overall_emoji} *TOTAL*\n"
            f"   Invested: `{total_invested:.4f}` SOL\n"
            f"   Current: `{total_current_value:.4f}` SOL\n"
            f"   PnL: `{total_pnl_sol:+.4f}` SOL ({total_pnl_pct:+.1f}%)"
        )
        
        await self._send_to_admin(message)
    
    async def _cmd_signal_pnl(self, args: str) -> None:
        """Show PnL statistics for signals from the channel (from database)."""
        # Check if database is available
        if not self._signal_db:
            await self._send_to_admin(
                "❌ *Signal database not configured*\n\n"
                "Set these environment variables:\n"
                "• `POSTGRES_HOST`\n"
                "• `POSTGRES_PORT`\n"
                "• `POSTGRES_USER`\n"
                "• `POSTGRES_PASSWORD`\n"
                "• `POSTGRES_DATABASE`"
            )
            return
        
        # Parse period argument
        arg = args.strip().lower() if args else "all"
        
        # Handle "all" or "lifetime" for all-time stats
        if arg in ("all", "lifetime"):
            days = None
        else:
            # Try to parse as number of days
            # Support formats: "7", "7d", "7days"
            numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
            try:
                days = int(numeric_arg)
                if days <= 0:
                    await self._send_to_admin(
                        "❌ *Invalid period*\n\n"
                        "Please enter a positive number of days.\n\n"
                        "Examples: `/signalpnl 7`, `/signalpnl 30`, `/signalpnl all`"
                    )
                    return
            except ValueError:
                await self._send_to_admin(
                    "❌ *Invalid period*\n\n"
                    "Usage: /signalpnl `<days>` or `/signalpnl all`\n\n"
                    "Examples:\n"
                    "• `/signalpnl 7` - Last 7 days\n"
                    "• `/signalpnl 30` - Last 30 days\n"
                    "• `/signalpnl all` - All time"
                )
                return
        
        await self._send_to_admin(f"⏳ Querying signal database...")
        
        # Query database for PnL stats
        stats = await self._signal_db.calculate_pnl_stats(days)
        
        if stats.total_signals == 0:
            await self._send_to_admin(
                f"📭 *No signals found*\n\n"
                f"Period: {stats.period_label}\n\n"
                "Make sure the database has signal data."
            )
            return
        
        # Build message
        win_emoji = "🟢" if stats.win_rate >= 50 else "🔴"
        pnl_emoji = "🟢" if stats.total_pnl_percent >= 0 else "🔴"
        
        # Date range
        date_range = ""
        if stats.start_date and stats.end_date:
            date_range = f"📅 `{stats.start_date.strftime('%Y-%m-%d')}` to `{stats.end_date.strftime('%Y-%m-%d')}`\n\n"
        
        message = (
            f"📊 *SIGNAL PnL - {stats.period_label}*\n\n"
            f"{date_range}"
            f"📈 *Overview*\n"
            f"• Total Signals: `{stats.total_signals}`\n"
            f"• With Profit: `{stats.signals_with_profit}`\n"
            f"• Reached 2X: `{stats.signals_reached_2x}`\n"
            f"• Losers: `{stats.losing_signals}`\n"
            f"• {win_emoji} Win Rate: `{stats.win_rate:.1f}%`\n"
            f"• Win Rate (2X+): `{stats.win_rate_2x:.1f}%`\n\n"
            f"💰 *Performance*\n"
            f"• {pnl_emoji} Avg PnL: `{stats.total_pnl_percent:+.1f}%`\n"
            f"• Avg Mult: `{stats.avg_multiplier:.2f}X`\n"
            f"• Best: `{stats.best_multiplier:.2f}X`\n"
            f"• Worst: `{stats.worst_multiplier:.2f}X`\n"
        )
        
        # Add top performers
        if stats.top_performers:
            message += "\n🏆 *Top Performers*\n"
            for i, s in enumerate(stats.top_performers, 1):
                mult = s.max_multiplier
                pnl = s.pnl_percent
                message += f"{i}. `${s.signal.token_symbol}` - `{mult:.2f}X` ({pnl:+.1f}%)\n"
        
        # Add worst performers (from winners only)
        if stats.worst_performers:
            message += "\n📉 *Smallest Wins*\n"
            for i, s in enumerate(stats.worst_performers, 1):
                mult = s.max_multiplier
                pnl = s.pnl_percent
                message += f"{i}. `${s.signal.token_symbol}` - `{mult:.2f}X` ({pnl:+.1f}%)\n"
        
        await self._send_to_admin(message)
    
    async def _cmd_sync_signals(self, args: str) -> None:
        """Sync latest signals from the Trenches channel to database."""
        if not self._signal_db:
            await self._send_to_admin("❌ Database not configured")
            return
        
        if not self._bot or not self._bot._client:
            await self._send_to_admin("❌ Trading bot not connected")
            return
        
        await self._send_to_admin("🔄 *Syncing signals from channel...*\n\nThis may take a moment...")
        
        try:
            # Use the trading bot's Telegram client to fetch messages
            client = self._bot._client
            
            # Get the channel entity
            from src.constants import TRENCHES_CHANNEL_NAME
            channel = None
            async for dialog in client.iter_dialogs():
                if dialog.name == TRENCHES_CHANNEL_NAME:
                    channel = dialog.entity
                    break
            
            if not channel:
                await self._send_to_admin(f"❌ Channel not found: {TRENCHES_CHANNEL_NAME}")
                return
            
            # Fetch messages from the channel
            new_signals = 0
            new_alerts = 0
            total_fetched = 0
            
            # Signal detection patterns (from parsers)
            import re
            SIGNAL_PATTERN = re.compile(r'VOLUME \+ SM APE SIGNAL DETECTED|APE SIGNAL DETECTED', re.IGNORECASE)
            TOKEN_PATTERN = re.compile(r'\$([A-Z0-9]{2,10})')
            ADDRESS_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')
            MULTIPLIER_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*[xX]', re.IGNORECASE)
            PROFIT_ALERT_PATTERN = re.compile(r'PROFIT ALERT|X PROFIT|hit \d+\.?\d*x', re.IGNORECASE)
            
            # Fetch ALL messages from channel history (no limit, no early stop)
            # Duplicates are handled by ON CONFLICT in database
            messages_to_process = []
            await self._send_to_admin("⏳ Fetching all channel history... This may take a while.")
            
            async for message in client.iter_messages(channel, limit=None):
                if not message.text:
                    continue
                
                total_fetched += 1
                messages_to_process.append(message)
                
                # Progress update every 1000 messages
                if total_fetched % 1000 == 0:
                    logger.info(f"Fetched {total_fetched} messages so far...")
                    await self._send_to_admin(f"📊 Progress: {total_fetched} messages fetched...")
            
            # Process messages in chronological order (oldest first)
            messages_to_process.reverse()
            
            for message in messages_to_process:
                text = message.text
                msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                
                # Check if it's a signal
                if SIGNAL_PATTERN.search(text):
                    # Extract token info
                    symbol_match = TOKEN_PATTERN.search(text)
                    address_match = ADDRESS_PATTERN.search(text)
                    
                    if symbol_match and address_match:
                        symbol = symbol_match.group(1)
                        address = address_match.group(0)
                        
                        # Insert signal into database
                        inserted = await self._signal_db.insert_signal(
                            message_id=message.id,
                            token_symbol=symbol,
                            token_address=address,
                            signal_time=msg_time,
                            raw_text=text,
                        )
                        if inserted:
                            new_signals += 1
                
                # Check if it's a profit alert
                elif PROFIT_ALERT_PATTERN.search(text) and message.reply_to:
                    reply_to_id = message.reply_to.reply_to_msg_id
                    
                    # Extract multiplier
                    mult_match = MULTIPLIER_PATTERN.search(text)
                    if mult_match and reply_to_id:
                        multiplier = float(mult_match.group(1))
                        
                        # Insert profit alert into database
                        inserted = await self._signal_db.insert_profit_alert(
                            message_id=message.id,
                            reply_to_msg_id=reply_to_id,
                            multiplier=multiplier,
                            alert_time=msg_time,
                            raw_text=text,
                        )
                        if inserted:
                            new_alerts += 1
            
            # Get updated counts
            counts = await self._signal_db.get_signal_count()
            
            message = (
                "✅ *Sync Complete!*\n\n"
                f"• Messages Scanned: `{total_fetched}`\n"
                f"• New Signals: `{new_signals}`\n"
                f"• New Profit Alerts: `{new_alerts}`\n\n"
                f"📊 *Database Totals*\n"
                f"• Total Signals: `{counts.get('total_signals', 0)}`\n"
                f"• Total Alerts: `{counts.get('total_profit_alerts', 0)}`"
            )
            
            await self._send_to_admin(message)
            logger.info(f"Sync complete: {new_signals} signals, {new_alerts} alerts")
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            await self._send_to_admin(f"❌ *Sync failed*\n\n`{str(e)}`")
    
    async def record_signal(
        self,
        token_address: str,
        token_symbol: str,
        message_id: int,
    ) -> None:
        """
        Record a signal for PnL tracking.
        
        Called by the trading bot when a new signal is detected.
        """
        await self._signal_history.add_signal(
            token_address=token_address,
            token_symbol=token_symbol,
            message_id=message_id,
        )
