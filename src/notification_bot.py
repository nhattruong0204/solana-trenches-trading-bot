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
            BotCommand(command="simulate", description="🎯 Simulate trading strategies"),
            BotCommand(command="syncsignals", description="🔄 Sync NEW signals (incremental)"),
            BotCommand(command="bootstrap", description="🔧 One-time full history sync"),
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
            "/realpnl": self._cmd_real_pnl,
            "/compare": self._cmd_compare,
            "/syncsignals": self._cmd_sync_signals,
            "/bootstrap": self._cmd_bootstrap_signals,
            "/simulate": self._cmd_simulate,
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
                Button.inline("📊 Real PnL (All)", b"realpnl_all"),
                Button.inline("📈 Real PnL (Custom)", b"realpnl_custom"),
            ],
            [
                Button.inline("🆚 Compare PnL (All)", b"compare_all"),
                Button.inline("🆚 Compare PnL (Custom)", b"compare_custom"),
            ],
            [
                Button.inline("🎯 Simulate (30d)", b"simulate_30d"),
                Button.inline("🎯 Simulate (7d)", b"simulate_7d"),
            ],
            [
                Button.inline("🔄 Sync Signals", b"cmd_sync_signals"),
                Button.inline("📥 Bootstrap", b"cmd_bootstrap"),
            ],
            [
                Button.inline("⏸️ Pause", b"cmd_pause"),
                Button.inline("▶️ Resume", b"cmd_resume"),
            ],
            [
                Button.inline("📊 Stats", b"cmd_stats"),
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
            "cmd_bootstrap": lambda: self._cmd_bootstrap_signals(""),
            "signalpnl_all": lambda: self._cmd_signal_pnl("all"),
            "signalpnl_custom": lambda: self._prompt_custom_days(),
            "realpnl_all": lambda: self._cmd_real_pnl("all"),
            "realpnl_custom": lambda: self._prompt_custom_days_realpnl(),
            "compare_all": lambda: self._cmd_compare("all"),
            "compare_custom": lambda: self._prompt_custom_days_compare(),
            "simulate_30d": lambda: self._cmd_simulate("30"),
            "simulate_7d": lambda: self._cmd_simulate("7"),
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
            "• /realpnl `<days>` - Real-time PnL (live prices)\n"
            "• /realpnl `all` - All-time real-time PnL\n"
            "• /compare `<days>` - Compare signal vs real PnL\n"
            "• /compare `all` - All-time comparison\n\n"
            "*Signal Sync:*\n"
            "• /bootstrap - One-time full history sync\n"
            "• /syncsignals - Sync only NEW signals\n\n"
            "_Note: Run /bootstrap once first, then /syncsignals only fetches new messages._\n\n"
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
        """
        Show PnL statistics for signals from the channel (from database profit alerts).
        
        Usage: /signalpnl [days] [position_size]
        Examples:
            /signalpnl 7        - Last 7 days with 1 SOL per trade
            /signalpnl 7 0.5    - Last 7 days with 0.5 SOL per trade
            /signalpnl all 0.1  - All time with 0.1 SOL per trade
        """
        # GMGN Fee structure: 1% platform + 0.5% priority + 1% slippage = 2.5% each way
        BUY_FEE_PCT = 2.5
        SELL_FEE_PCT = 2.5
        DEFAULT_POSITION_SIZE = 1.0
        
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
        
        # Parse arguments: [days] [position_size]
        parts = args.strip().split() if args else []
        days = None
        position_size = DEFAULT_POSITION_SIZE
        
        # Parse first argument (days)
        if len(parts) >= 1:
            arg = parts[0].lower()
            if arg in ("all", "lifetime"):
                days = None
            else:
                numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
                try:
                    days = int(numeric_arg)
                    if days <= 0:
                        await self._send_to_admin(
                            "❌ *Invalid period*\n\n"
                            "Usage: `/signalpnl [days] [position_size]`\n\n"
                            "Examples:\n"
                            "• `/signalpnl 7` - Last 7 days, 1 SOL/trade\n"
                            "• `/signalpnl 7 0.5` - Last 7 days, 0.5 SOL/trade\n"
                            "• `/signalpnl all 0.1` - All time, 0.1 SOL/trade"
                        )
                        return
                except ValueError:
                    await self._send_to_admin(
                        "❌ *Invalid period*\n\n"
                        "Usage: `/signalpnl [days] [position_size]`\n\n"
                        "Examples:\n"
                        "• `/signalpnl 7` - Last 7 days, 1 SOL/trade\n"
                        "• `/signalpnl 7 0.5` - Last 7 days, 0.5 SOL/trade\n"
                        "• `/signalpnl all 0.1` - All time, 0.1 SOL/trade"
                    )
                    return
        
        # Parse second argument (position size)
        if len(parts) >= 2:
            try:
                position_size = float(parts[1])
                if position_size <= 0:
                    position_size = DEFAULT_POSITION_SIZE
            except ValueError:
                pass  # Use default
        
        period_label = f"Last {days} Day{'s' if days != 1 else ''}" if days else "All Time"
        
        await self._send_to_admin(f"⏳ Querying signal database...")
        
        # Get signals with profit data
        signals = await self._signal_db.get_signals_in_period(days)
        
        if not signals:
            await self._send_to_admin(
                f"📭 *No signals found*\n\n"
                f"Period: {period_label}\n\n"
                "Make sure the database has signal data."
            )
            return
        
        # Calculate SOL profits for each signal
        token_results = []
        total_invested_sol = 0.0
        total_returned_sol = 0.0
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        
        for s in signals:
            mult = s.max_multiplier if s.has_profit else 0
            
            # Calculate with fees
            invested = position_size
            if mult == 0:
                # No profit alert = assume total loss (lost all including buy fee)
                returned = 0.0
                sol_profit = -position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                sell_fee = 0.0  # Never sold
            else:
                # Buy: position - fee
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                tokens_value = position_size - buy_fee
                # Tokens grow by multiplier
                sell_value = tokens_value * mult
                # Sell: deduct fee
                sell_fee = sell_value * (SELL_FEE_PCT / 100)
                returned = sell_value - sell_fee
                sol_profit = returned - invested
            
            total_invested_sol += invested
            total_returned_sol += returned
            total_buy_fees += buy_fee
            total_sell_fees += sell_fee
            
            token_results.append({
                'signal': s,
                'multiplier': mult,
                'sol_profit': sol_profit,
                'invested': invested,
                'returned': returned,
            })
        
        # Sort by SOL profit (descending - best first)
        token_results.sort(key=lambda x: x['sol_profit'], reverse=True)
        
        # Calculate totals
        total_sol_profit = total_returned_sol - total_invested_sol
        total_pnl_pct = (total_sol_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        total_fees = total_buy_fees + total_sell_fees
        fee_pct_of_invested = (total_fees / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        # Profit before fees (gross profit)
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
            f"📊 *Signal PnL* - {period_label}\n\n"
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
            f"• No Profit Alert: `{len(losers)}`\n\n"
            f"📊 *Win/Loss*\n"
            f"• {win_emoji} Win Rate: `{win_rate:.1f}%`\n"
            f"• Winners: `{len(with_profit)}`\n"
            f"• Losers: `{len(losers)}`\n"
        )
        
        # Send header first
        await self._send_to_admin(header_message)
        
        # Build token list in chunks (Telegram limit is ~4096 chars)
        MAX_MESSAGE_LENGTH = 3800
        
        token_lines = []
        for i, tr in enumerate(token_results, 1):
            s = tr['signal']
            sol_profit = tr['sol_profit']
            mult = tr['multiplier']
            token_address = s.signal.token_address
            
            # Build links
            dex_link = f"https://dexscreener.com/solana/{token_address}"
            gmgn_link = f"https://gmgn.ai/sol/token/{token_address}"
            
            if mult == 0:
                emoji = "💀"
                mult_str = f"[N/A]({dex_link})"
            elif mult >= 10:
                emoji = "🚀"
                mult_str = f"[{mult:.2f}X]({dex_link})"
            elif mult >= 2:
                emoji = "🟢"
                mult_str = f"[{mult:.2f}X]({dex_link})"
            elif mult >= 1:
                emoji = "🟡"
                mult_str = f"[{mult:.2f}X]({dex_link})"
            else:
                emoji = "🔴"
                mult_str = f"[{mult:.2f}X]({dex_link})"
            
            profit_emoji = "🟢" if sol_profit >= 0 else "🔴"
            line = f"{i}. `${s.signal.token_symbol}` {emoji} {mult_str} | [G]({gmgn_link}) → {profit_emoji}`{sol_profit:+.3f}` SOL\n"
            token_lines.append(line)
        
        # Send token list in chunks
        current_message = "📋 *All Tokens (Best → Worst)*\n"
        for line in token_lines:
            if len(current_message) + len(line) > MAX_MESSAGE_LENGTH:
                await self._send_to_admin(current_message)
                current_message = ""
            current_message += line
        
        if current_message:
            await self._send_to_admin(current_message)
    
    async def _cmd_real_pnl(self, args: str) -> None:
        """
        Calculate REAL-TIME PnL by fetching current market cap from DexScreener.
        
        Shows all tokens sorted from best to worst profit with SOL calculations.
        
        Usage: /realpnl [days] [position_size]
        Examples:
            /realpnl 7        - Last 7 days with 1 SOL per trade
            /realpnl 7 0.5    - Last 7 days with 0.5 SOL per trade
            /realpnl all 0.1  - All time with 0.1 SOL per trade
        """
        from src.signal_database import calculate_real_pnl
        
        # GMGN Fee structure: 1% platform + 0.5% priority + 1% slippage = 2.5% each way
        BUY_FEE_PCT = 2.5
        SELL_FEE_PCT = 2.5
        DEFAULT_POSITION_SIZE = 1.0
        
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
        
        # Parse arguments: [days] [position_size]
        parts = args.strip().split() if args else []
        days = None
        position_size = DEFAULT_POSITION_SIZE
        
        # Parse first argument (days)
        if len(parts) >= 1:
            arg = parts[0].lower()
            if arg in ("all", "lifetime"):
                days = None
            else:
                numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
                try:
                    days = int(numeric_arg)
                    if days <= 0:
                        await self._send_to_admin(
                            "❌ *Invalid period*\n\n"
                            "Usage: `/realpnl [days] [position_size]`\n\n"
                            "Examples:\n"
                            "• `/realpnl 7` - Last 7 days, 1 SOL/trade\n"
                            "• `/realpnl 7 0.5` - Last 7 days, 0.5 SOL/trade\n"
                            "• `/realpnl all 0.1` - All time, 0.1 SOL/trade"
                        )
                        return
                except ValueError:
                    await self._send_to_admin(
                        "❌ *Invalid period*\n\n"
                        "Usage: `/realpnl [days] [position_size]`\n\n"
                        "Examples:\n"
                        "• `/realpnl 7` - Last 7 days, 1 SOL/trade\n"
                        "• `/realpnl 7 0.5` - Last 7 days, 0.5 SOL/trade\n"
                        "• `/realpnl all 0.1` - All time, 0.1 SOL/trade"
                    )
                    return
        
        # Parse second argument (position size)
        if len(parts) >= 2:
            try:
                position_size = float(parts[1])
                if position_size <= 0:
                    position_size = DEFAULT_POSITION_SIZE
            except ValueError:
                pass  # Use default
        
        period_label = f"Last {days} Days" if days else "All Time"
        
        # Get signals
        await self._send_to_admin(f"⏳ Fetching signals from database...")
        signals = await self._signal_db.get_signals_for_real_pnl(days)
        
        if not signals:
            await self._send_to_admin(
                f"📭 *No signals found*\n\n"
                f"Period: {period_label}\n\n"
                "Make sure the database has signal data."
            )
            return
        
        # Progress message
        progress_msg = await self._send_to_admin(
            f"🔍 Fetching live prices from DexScreener...\n"
            f"Total signals: {len(signals)}\n"
            f"Progress: 0/{len(signals)}"
        )
        
        # Progress callback
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
                pass  # Ignore edit errors
        
        # Calculate real PnL
        stats = await calculate_real_pnl(signals, update_progress)
        stats.period_label = period_label
        
        # Calculate SOL profits for each result
        token_results = []
        total_invested_sol = 0.0
        total_returned_sol = 0.0
        total_buy_fees = 0.0
        total_sell_fees = 0.0
        
        for r in stats.results:
            if r.multiplier is None or r.is_rugged:
                # Rugged or no price = total loss (lost all including buy fee)
                invested = position_size
                returned = 0.0
                sol_profit = -position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                sell_fee = 0.0  # Never sold
            else:
                # Calculate with fees
                invested = position_size
                buy_fee = position_size * (BUY_FEE_PCT / 100)
                tokens_value = position_size - buy_fee  # After buy fee
                
                # Tokens grow by multiplier
                sell_value = tokens_value * r.multiplier
                
                # Sell: deduct 2.5% fee
                sell_fee = sell_value * (SELL_FEE_PCT / 100)
                returned = sell_value - sell_fee
                sol_profit = returned - invested
            
            total_invested_sol += invested
            total_returned_sol += returned
            total_buy_fees += buy_fee
            total_sell_fees += sell_fee
            
            token_results.append({
                'result': r,
                'sol_profit': sol_profit,
                'invested': invested,
                'returned': returned,
            })
        
        # Sort by SOL profit (descending - best first)
        token_results.sort(key=lambda x: x['sol_profit'], reverse=True)
        
        # Calculate totals
        total_sol_profit = total_returned_sol - total_invested_sol
        total_pnl_pct = (total_sol_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        total_fees = total_buy_fees + total_sell_fees
        fee_pct_of_invested = (total_fees / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        # Build results message
        win_rate = (stats.winners / stats.successful_fetches * 100) if stats.successful_fetches else 0
        win_emoji = "🟢" if win_rate >= 50 else "🔴"
        pnl_emoji = "🟢" if total_sol_profit >= 0 else "🔴"
        
        # Date range
        date_range = ""
        if stats.start_date and stats.end_date:
            date_range = f"📅 `{stats.start_date.strftime('%Y-%m-%d')}` to `{stats.end_date.strftime('%Y-%m-%d')}`\n\n"
        
        # Profit before fees (gross profit)
        gross_profit = total_sol_profit + total_fees
        gross_pnl_pct = (gross_profit / total_invested_sol * 100) if total_invested_sol > 0 else 0
        
        header_message = (
            f"📊 *Real-Time PnL* - {period_label}\n\n"
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
            f"• Rugged: `{stats.rugged_count}` 💀\n\n"
            f"📊 *Win/Loss*\n"
            f"• {win_emoji} Win Rate: `{win_rate:.1f}%`\n"
            f"• Winners (≥1X): `{stats.winners}`\n"
            f"• Losers (<1X): `{stats.losers}`\n"
        )
        
        # Send header first
        await self._send_to_admin(header_message)
        
        # Build token list in chunks (Telegram limit is ~4096 chars)
        MAX_MESSAGE_LENGTH = 3800  # Leave some buffer
        
        token_lines = []
        for i, tr in enumerate(token_results, 1):
            r = tr['result']
            sol_profit = tr['sol_profit']
            mult = r.multiplier or 0
            token_address = r.signal.token_address
            
            # Build links
            dex_link = f"https://dexscreener.com/solana/{token_address}"
            gmgn_link = f"https://gmgn.ai/sol/token/{token_address}"
            
            if r.is_rugged:
                emoji = "💀"
                mult_str = f"[RUG]({dex_link})"
            elif mult == 0 or r.multiplier is None:
                emoji = "❓"
                mult_str = f"[N/A]({dex_link})"
            else:
                emoji = r.status_emoji
                mult_str = f"[{mult:.2f}X]({dex_link})"
            
            profit_emoji = "🟢" if sol_profit >= 0 else "🔴"
            line = f"{i}. `${r.signal.token_symbol}` {emoji} {mult_str} | [G]({gmgn_link}) → {profit_emoji}`{sol_profit:+.3f}` SOL\n"
            token_lines.append(line)
        
        # Send token list in chunks
        current_message = "📋 *All Tokens (Best → Worst)*\n"
        for line in token_lines:
            if len(current_message) + len(line) > MAX_MESSAGE_LENGTH:
                # Send current chunk
                await self._send_to_admin(current_message)
                current_message = ""  # Start new chunk without header
            current_message += line
        
        # Send remaining
        if current_message:
            await self._send_to_admin(current_message)
    
    async def _prompt_custom_days_realpnl(self) -> None:
        """Prompt user to enter custom days for real PnL calculation."""
        await self._send_to_admin(
            "📊 *Real-Time PnL - Custom Period*\n\n"
            "Enter the number of days to analyze:\n\n"
            "Examples:\n"
            "• `/realpnl 7` - Last 7 days\n"
            "• `/realpnl 14` - Last 14 days\n"
            "• `/realpnl 30` - Last 30 days\n\n"
            "⚠️ Note: This fetches live prices from DexScreener\n"
            "and may take a while for many signals."
        )
    
    async def _cmd_compare(self, args: str) -> None:
        """
        Compare signal PnL (from profit alerts) vs real PnL (live prices).
        Shows side-by-side table sorted from best to worst.
        """
        from src.signal_database import calculate_comparison
        
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
            period_label = "All Time"
        else:
            # Try to parse as number of days
            numeric_arg = arg.replace("d", "").replace("days", "").replace("day", "")
            try:
                days = int(numeric_arg)
                if days <= 0:
                    await self._send_to_admin(
                        "❌ *Invalid period*\n\n"
                        "Please enter a positive number of days.\n\n"
                        "Examples: `/compare 7`, `/compare 30`, `/compare all`"
                    )
                    return
                period_label = f"Last {days} Days"
            except ValueError:
                await self._send_to_admin(
                    "❌ *Invalid period*\n\n"
                    "Usage: /compare `<days>` or `/compare all`\n\n"
                    "Examples:\n"
                    "• `/compare 7` - Last 7 days\n"
                    "• `/compare 30` - Last 30 days\n"
                    "• `/compare all` - All time"
                )
                return
        
        # Get signals with profit alerts
        await self._send_to_admin(f"⏳ Fetching signals from database...")
        signals = await self._signal_db.get_signals_with_pnl_for_compare(days)
        
        if not signals:
            await self._send_to_admin(
                f"📭 *No signals found*\n\n"
                f"Period: {period_label}\n\n"
                "Make sure the database has signal data."
            )
            return
        
        # Progress message
        progress_msg = await self._send_to_admin(
            f"🔍 Fetching live prices from DexScreener...\n"
            f"Total signals: {len(signals)}\n"
            f"Progress: 0/{len(signals)}"
        )
        
        # Progress callback
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
                pass  # Ignore edit errors
        
        # Calculate comparison
        stats = await calculate_comparison(signals, update_progress)
        stats.period_label = period_label
        
        # Build header message
        date_range = ""
        if stats.start_date and stats.end_date:
            date_range = f"📅 `{stats.start_date.strftime('%Y-%m-%d')}` to `{stats.end_date.strftime('%Y-%m-%d')}`\n\n"
        
        header = (
            f"🆚 *PnL Comparison* - {period_label}\n\n"
            f"{date_range}"
            f"📊 *Summary*\n"
            f"• Total: `{stats.total_signals}` signals\n"
            f"• Rugged: `{stats.rugged_count}` 💀\n\n"
            f"📈 *Signal PnL* (Profit Alerts)\n"
            f"• Winners: `{stats.signal_winners}`\n"
            f"• Avg Mult: `{stats.signal_avg_mult:.2f}X`\n\n"
            f"📊 *Real PnL* (Live Prices)\n"
            f"• Winners: `{stats.real_winners}`\n"
            f"• Avg Mult: `{stats.real_avg_mult:.2f}X`\n"
        )
        
        await self._send_to_admin(header)
        
        # Build comparison table - sorted from best to worst
        # Split into chunks to avoid message length limits
        table_header = (
            "```\n"
            "# | Ticker    | Signal | Real\n"
            "--|-----------|--------|------\n"
        )
        
        results = stats.results
        chunk_size = 25
        
        for chunk_idx in range(0, len(results), chunk_size):
            chunk = results[chunk_idx:chunk_idx + chunk_size]
            
            table = table_header
            for i, r in enumerate(chunk, chunk_idx + 1):
                ticker = r.signal.token_symbol[:8]
                
                # Signal multiplier
                if r.has_profit_alert and r.signal_multiplier:
                    sig_str = f"{r.signal_emoji}{r.signal_multiplier:.1f}X"
                else:
                    sig_str = f"{r.signal_emoji} ---"
                
                # Real multiplier
                if r.real_multiplier is not None:
                    real_str = f"{r.real_emoji}{r.real_multiplier:.1f}X"
                elif r.is_rugged:
                    real_str = "💀 RUG"
                else:
                    real_str = "❓ ---"
                
                table += f"{i:2} | ${ticker:<8} | {sig_str:<6} | {real_str}\n"
            
            table += "```"
            
            # Add page indicator if multiple chunks
            if len(results) > chunk_size:
                page_num = chunk_idx // chunk_size + 1
                total_pages = (len(results) + chunk_size - 1) // chunk_size
                table += f"\n_Page {page_num}/{total_pages}_"
            
            await self._send_to_admin(table)
        
        # Save results to JSON file for AI analysis
        await self._save_compare_results_json(stats, days)
    
    async def _save_compare_results_json(self, stats, days: Optional[int]) -> None:
        """Save comparison results to JSON and send directly to Telegram channel."""
        import json
        import io
        from datetime import datetime
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        period_str = f"{days}d" if days else "all"
        filename = f"compare_{period_str}_{timestamp}.json"
        
        # Build JSON structure optimized for AI analysis
        json_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "period": stats.period_label,
                "days": days,
                "start_date": stats.start_date.isoformat() if stats.start_date else None,
                "end_date": stats.end_date.isoformat() if stats.end_date else None,
            },
            "summary": {
                "total_signals": stats.total_signals,
                "rugged_count": stats.rugged_count,
                "signal_pnl": {
                    "winners": stats.signal_winners,
                    "win_rate": round(stats.signal_winners / stats.total_signals * 100, 1) if stats.total_signals else 0,
                    "avg_multiplier": round(stats.signal_avg_mult, 2),
                },
                "real_pnl": {
                    "winners": stats.real_winners,
                    "win_rate": round(stats.real_winners / stats.total_signals * 100, 1) if stats.total_signals else 0,
                    "avg_multiplier": round(stats.real_avg_mult, 2),
                },
                "insight": self._generate_pnl_insight(stats),
            },
            "tokens": [
                {
                    "rank": i + 1,
                    "symbol": r.signal.token_symbol,
                    "address": r.signal.token_address,
                    "signal_timestamp": r.signal.timestamp.isoformat(),
                    "age_hours": round(r.signal.age_hours, 1),
                    "initial_fdv": r.signal.initial_fdv,
                    "signal": {
                        "has_profit_alert": r.has_profit_alert,
                        "multiplier": round(r.signal_multiplier, 2) if r.signal_multiplier else None,
                        "pnl_percent": round(r.signal_pnl_percent, 1) if r.signal_pnl_percent else None,
                        "status": "winner" if r.signal_multiplier and r.signal_multiplier >= 1 else "loser" if r.has_profit_alert else "no_alert",
                    },
                    "real": {
                        "multiplier": round(r.real_multiplier, 2) if r.real_multiplier else None,
                        "pnl_percent": round(r.real_pnl_percent, 1) if r.real_pnl_percent else None,
                        "is_rugged": r.is_rugged,
                        "status": "rugged" if r.is_rugged else "winner" if r.real_multiplier and r.real_multiplier >= 1 else "loser" if r.real_multiplier else "unknown",
                    },
                    "decay": {
                        "signal_to_real_ratio": round(r.real_multiplier / r.signal_multiplier, 2) if r.signal_multiplier and r.real_multiplier else None,
                        "lost_percentage": round((1 - r.real_multiplier / r.signal_multiplier) * 100, 1) if r.signal_multiplier and r.real_multiplier else None,
                    },
                }
                for i, r in enumerate(stats.results)
            ],
        }
        
        # Create in-memory file
        json_bytes = json.dumps(json_data, indent=2).encode('utf-8')
        file_buffer = io.BytesIO(json_bytes)
        file_buffer.name = filename
        
        # Send file to notification channel (use resolved entity, fallback to admin)
        caption = (
            f"📊 *Compare Results - {stats.period_label}*\n\n"
            f"• Signals: {stats.total_signals}\n"
            f"• Signal Win Rate: {round(stats.signal_winners / stats.total_signals * 100, 1) if stats.total_signals else 0}%\n"
            f"• Real Win Rate: {round(stats.real_winners / stats.total_signals * 100, 1) if stats.total_signals else 0}%\n"
            f"• Rugged: {stats.rugged_count}\n\n"
            f"_Download and analyze with AI_"
        )
        
        target = self._channel_entity if self._channel_entity else self._admin_user_id
        await self._client.send_file(
            target,
            file_buffer,
            caption=caption,
            parse_mode='markdown'
        )
    
    def _generate_pnl_insight(self, stats) -> str:
        """Generate AI-friendly insight from stats."""
        insights = []
        
        if stats.total_signals == 0:
            return "No data available"
        
        # Win rate comparison
        signal_wr = stats.signal_winners / stats.total_signals * 100 if stats.total_signals else 0
        real_wr = stats.real_winners / stats.total_signals * 100 if stats.total_signals else 0
        
        if signal_wr > 50:
            insights.append(f"Signal strategy has {signal_wr:.0f}% win rate (profit alerts)")
        
        if real_wr < signal_wr:
            decay = signal_wr - real_wr
            insights.append(f"Real PnL shows {decay:.0f}% decay from peak - suggests need for faster exits")
        
        # Multiplier analysis
        if stats.signal_avg_mult > 2:
            insights.append(f"Avg signal peak of {stats.signal_avg_mult:.1f}X indicates strong pumps")
        
        if stats.real_avg_mult < 1:
            insights.append(f"Current avg of {stats.real_avg_mult:.1f}X shows most gains lost - exit strategy critical")
        
        # Rug analysis
        rug_rate = stats.rugged_count / stats.total_signals * 100 if stats.total_signals else 0
        if rug_rate > 10:
            insights.append(f"{rug_rate:.0f}% rug rate - consider stop losses")
        
        return "; ".join(insights) if insights else "Data insufficient for insights"
    
    async def _cmd_simulate(self, args: str) -> None:
        """
        Simulate trading strategies on historical signal data.
        
        Usage: /simulate [days] [position_size]
        Examples:
            /simulate 30       - Simulate last 30 days with 0.1 SOL per trade
            /simulate 30 0.2   - Simulate with 0.2 SOL per trade
        """
        from src.accurate_backtester import run_accurate_backtest, BacktestConfig
        import io
        import json
        
        if not self._signal_db:
            await self._send_to_admin(
                "❌ *Signal database not configured*\n\n"
                "Configure database to use strategy simulation."
            )
            return
        
        # Parse arguments
        parts = args.strip().split() if args else []
        days = 30  # Default 30 days
        position_size = 0.1  # Default position size
        
        if len(parts) >= 1:
            try:
                days = int(parts[0].replace("d", "").replace("days", ""))
            except ValueError:
                pass
        
        if len(parts) >= 2:
            try:
                position_size = float(parts[1])
            except ValueError:
                pass
        
        period_label = f"Last {days} Days"
        
        progress_msg = await self._send_to_admin(
            f"🎯 *Running Accurate Backtest*\n\n"
            f"• Period: {period_label}\n"
            f"• Position Size: {position_size} SOL\n"
            f"• Capital: 10 SOL\n\n"
            f"⏳ Step 1/3: Fetching signals from database..."
        )
        
        try:
            # Get signals with profit alerts
            signals = await self._signal_db.get_signals_with_pnl_for_compare(days)
            
            if not signals:
                await self._send_to_admin(
                    "❌ *No signal data found*\n\n"
                    "Try syncing signals first with `/syncsignals` or `/bootstrap`"
                )
                return
            
            # Update progress
            try:
                await self._client.edit_message(
                    self._admin_chat_id,
                    progress_msg.id,
                    f"🎯 *Running Accurate Backtest*\n\n"
                    f"• Period: {period_label}\n"
                    f"• Signals: {len(signals)}\n\n"
                    f"⏳ Step 2/3: Fetching OHLCV candles from GeckoTerminal...\n"
                    f"(This may take a few minutes for many tokens)"
                )
            except:
                pass
            
            # Build signal list for backtester
            signal_list = [
                {
                    "symbol": swp.signal.token_symbol,
                    "address": swp.signal.token_address,
                    "signal_timestamp": swp.signal.timestamp.isoformat(),
                    "initial_fdv": swp.signal.initial_fdv,
                    "signal": {
                        "has_profit_alert": swp.has_profit,
                        "multiplier": swp.max_multiplier,
                    },
                    "real": {
                        "multiplier": None,  # Will be fetched
                        "is_rugged": False,
                    },
                }
                for swp in signals
            ]
            
            # Progress callback
            fetch_progress = [0]
            async def update_progress(msg: str):
                try:
                    await self._client.edit_message(
                        self._admin_chat_id,
                        progress_msg.id,
                        f"🎯 *Running Accurate Backtest*\n\n"
                        f"• Period: {period_label}\n"
                        f"• Signals: {len(signals)}\n\n"
                        f"⏳ {msg}"
                    )
                except:
                    pass
            
            # Run accurate backtest with real price history
            report, results = await run_accurate_backtest(
                signal_list,
                position_size=position_size,
                capital=10.0,
                progress_callback=update_progress
            )
            
            if not results:
                await self._send_to_admin(
                    "❌ *No valid results*\n\n"
                    "Could not fetch price data for any tokens."
                )
                return
            
            # Update to show completion
            try:
                await self._client.edit_message(
                    self._admin_chat_id,
                    progress_msg.id,
                    f"🎯 *Accurate Backtest Complete*\n\n"
                    f"• Period: {period_label}\n"
                    f"• Signals: {len(signals)}\n"
                    f"• Data Coverage: {results[0].data_coverage_pct:.1f}%\n\n"
                    f"✅ Sending report..."
                )
            except:
                pass
            
            # Send report in chunks
            max_len = 3800
            lines = report.split('\n')
            current_chunk = "```\n"
            
            for line in lines:
                if len(current_chunk) + len(line) + 10 > max_len:
                    current_chunk += "```"
                    await self._send_to_admin(current_chunk)
                    current_chunk = "```\n"
                current_chunk += line + "\n"
            
            if current_chunk.strip() != "```":
                current_chunk += "```"
                await self._send_to_admin(current_chunk)
            
            # Send best result as JSON
            if results:
                best = results[0]
                best_json = {
                    "strategy": best.strategy_name,
                    "roi": round(best.roi, 1),
                    "win_rate": round(best.win_rate, 1),
                    "total_pnl_sol": round(best.total_pnl_sol, 4),
                    "total_fees_sol": round(best.total_fees_sol, 4),
                    "avg_multiplier": round(best.avg_multiplier, 3),
                    "avg_hold_hours": round(best.avg_hold_time_hours, 1),
                    "data_coverage_pct": round(best.data_coverage_pct, 1),
                }
                
                json_bytes = json.dumps(best_json, indent=2).encode('utf-8')
                file_buffer = io.BytesIO(json_bytes)
                file_buffer.name = f"backtest_results_{days}d.json"
                
                target = self._channel_entity if self._channel_entity else self._admin_user_id
                await self._client.send_file(
                    target,
                    file_buffer,
                    caption=(
                        f"🏆 *Best Strategy (Accurate Backtest)*\n\n"
                        f"• Strategy: `{best.strategy_name}`\n"
                        f"• ROI: `{best.roi:+.1f}%`\n"
                        f"• Win Rate: `{best.win_rate:.1f}%`\n"
                        f"• Fees Paid: `{best.total_fees_sol:.4f} SOL`\n\n"
                        f"📊 Data Coverage: {best.data_coverage_pct:.1f}%\n"
                        f"(Real OHLCV candles from GeckoTerminal)"
                    ),
                    parse_mode='markdown'
                )
            
        except Exception as e:
            logger.error(f"Backtest error: {e}", exc_info=True)
            await self._send_to_admin(f"❌ *Backtest Error*\n\n`{str(e)}`")
    
    async def _prompt_custom_days_compare(self) -> None:
        """Prompt user to enter custom days for comparison."""
        await self._send_to_admin(
            "🆚 *Compare PnL - Custom Period*\n\n"
            "Enter the number of days to compare:\n\n"
            "Examples:\n"
            "• `/compare 7` - Last 7 days\n"
            "• `/compare 14` - Last 14 days\n"
            "• `/compare 30` - Last 30 days\n\n"
            "⚠️ Note: This fetches live prices from DexScreener\n"
            "and may take a while for many signals."
        )
    
    async def _cmd_sync_signals(self, args: str) -> None:
        """
        Sync NEW signals from the Trenches channel to database.
        
        This is the INCREMENTAL sync - only fetches messages AFTER the last cursor.
        For initial full sync, use /bootstrap command.
        
        Production-grade pattern:
        1. Get cursor (last_message_id) from DB
        2. Fetch only messages with id > cursor
        3. Process and insert (ON CONFLICT handles duplicates)
        4. Update cursor AFTER successful commit
        """
        if not self._signal_db:
            await self._send_to_admin("❌ Database not configured")
            return
        
        if not self._bot or not self._bot._client:
            await self._send_to_admin("❌ Trading bot not connected")
            return
        
        try:
            # Ensure channel state table exists (for upgrades)
            await self._signal_db.ensure_channel_state_table()
            
            # Use the trading bot's Telegram client to fetch messages
            client = self._bot._client
            
            # Get the channel entity
            from src.constants import TRENCHES_CHANNEL_NAME
            channel = None
            channel_id = 0
            async for dialog in client.iter_dialogs():
                if dialog.name == TRENCHES_CHANNEL_NAME:
                    channel = dialog.entity
                    channel_id = dialog.entity.id
                    break
            
            if not channel:
                await self._send_to_admin(f"❌ Channel not found: {TRENCHES_CHANNEL_NAME}")
                return
            
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
                    "Use the `/bootstrap` command or 🔧 Bootstrap button to fetch all history.\n\n"
                    "After bootstrap, sync will only fetch NEW messages."
                )
                return
            
            await self._send_to_admin(
                f"🔄 *Syncing NEW signals...*\n\n"
                f"• Last synced message ID: `{last_message_id}`\n"
                f"• Fetching messages after this ID..."
            )
            
            # Signal detection patterns (handle backticks and // prefix)
            import re
            SIGNAL_PATTERN = re.compile(r'VOLUME\s*\+\s*SM\s*APE\s*SIGNAL\s*DETECTED|APE\s*SIGNAL\s*DETECTED', re.IGNORECASE)
            TOKEN_PATTERN = re.compile(r'\$([A-Z0-9]{2,10})')
            ADDRESS_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')
            MULTIPLIER_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*[xX]', re.IGNORECASE)
            PROFIT_ALERT_PATTERN = re.compile(r'PROFIT\s*ALERT|X\s*PROFIT|hit\s+\d+\.?\d*x', re.IGNORECASE)
            
            # Fetch ONLY messages AFTER the cursor (incremental)
            messages_to_process = []
            total_fetched = 0
            max_message_id = last_message_id
            
            async for message in client.iter_messages(channel, min_id=last_message_id, limit=None):
                if not message.text:
                    continue
                
                # Skip if somehow we get old messages
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
            
            # Process messages in chronological order (oldest first)
            messages_to_process.reverse()
            
            new_signals = 0
            new_alerts = 0
            
            for message in messages_to_process:
                text = message.text
                msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                
                # Check if it's a signal
                if SIGNAL_PATTERN.search(text):
                    symbol_match = TOKEN_PATTERN.search(text)
                    address_match = ADDRESS_PATTERN.search(text)
                    
                    if symbol_match and address_match:
                        symbol = symbol_match.group(1)
                        address = address_match.group(0)
                        
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
                    mult_match = MULTIPLIER_PATTERN.search(text)
                    
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
            
            # Update cursor AFTER successful processing
            await self._signal_db.update_channel_cursor(
                channel_id=channel_id,
                channel_name=TRENCHES_CHANNEL_NAME,
                last_message_id=max_message_id,
            )
            
            # Get updated counts
            counts = await self._signal_db.get_signal_count()
            
            message = (
                "✅ *Sync Complete!*\n\n"
                f"• Messages Scanned: `{total_fetched}`\n"
                f"• New Signals: `{new_signals}`\n"
                f"• New Profit Alerts: `{new_alerts}`\n"
                f"• New Cursor: `{max_message_id}`\n\n"
                f"📊 *Database Totals*\n"
                f"• Total Signals: `{counts.get('total_signals', 0)}`\n"
                f"• Total Alerts: `{counts.get('total_profit_alerts', 0)}`"
            )
            
            await self._send_to_admin(message)
            logger.info(f"Sync complete: {new_signals} signals, {new_alerts} alerts, cursor={max_message_id}")
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            await self._send_to_admin(f"❌ *Sync failed*\n\n`{str(e)}`")

    async def _cmd_bootstrap_signals(self, args: str) -> None:
        """
        One-time FULL bootstrap of historical signals from the Trenches channel.
        
        This should only be run ONCE on first deployment or when adding a new channel.
        After bootstrap, use the regular sync (which is incremental).
        
        ⚠️ This fetches ALL messages - may take several minutes for large channels.
        """
        if not self._signal_db:
            await self._send_to_admin("❌ Database not configured")
            return
        
        if not self._bot or not self._bot._client:
            await self._send_to_admin("❌ Trading bot not connected")
            return
        
        try:
            # Ensure channel state table exists
            await self._signal_db.ensure_channel_state_table()
            
            client = self._bot._client
            
            # Get the channel entity
            from src.constants import TRENCHES_CHANNEL_NAME
            channel = None
            channel_id = 0
            async for dialog in client.iter_dialogs():
                if dialog.name == TRENCHES_CHANNEL_NAME:
                    channel = dialog.entity
                    channel_id = dialog.entity.id
                    break
            
            if not channel:
                await self._send_to_admin(f"❌ Channel not found: {TRENCHES_CHANNEL_NAME}")
                return
            
            # Check if bootstrap already completed
            state = await self._signal_db.get_channel_state(channel_id)
            if state.get("bootstrap_completed", False):
                await self._send_to_admin(
                    "⚠️ *Bootstrap Already Completed*\n\n"
                    f"Last message ID: `{state.get('last_message_id', 0)}`\n"
                    f"Completed at: `{state.get('last_processed_at', 'Unknown')}`\n\n"
                    "Use the regular **Sync Signals** button to fetch new messages.\n\n"
                    "_If you really need to re-bootstrap, clear the database first._"
                )
                return
            
            await self._send_to_admin(
                "🔧 *Starting Bootstrap...*\n\n"
                "⏳ Fetching ALL channel history. This may take several minutes...\n"
                "You'll receive progress updates every 1000 messages."
            )
            
            # Signal detection patterns (handle backticks and // prefix)
            import re
            SIGNAL_PATTERN = re.compile(r'VOLUME\s*\+\s*SM\s*APE\s*SIGNAL\s*DETECTED|APE\s*SIGNAL\s*DETECTED', re.IGNORECASE)
            TOKEN_PATTERN = re.compile(r'\$([A-Z0-9]{2,10})')
            ADDRESS_PATTERN = re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}')
            MULTIPLIER_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*[xX]', re.IGNORECASE)
            PROFIT_ALERT_PATTERN = re.compile(r'PROFIT\s*ALERT|X\s*PROFIT|hit\s+\d+\.?\d*x', re.IGNORECASE)
            
            # Fetch ALL messages from channel history
            messages_to_process = []
            total_fetched = 0
            max_message_id = 0
            
            async for message in client.iter_messages(channel, limit=None):
                if not message.text:
                    continue
                
                total_fetched += 1
                messages_to_process.append(message)
                max_message_id = max(max_message_id, message.id)
                
                # Progress update every 1000 messages
                if total_fetched % 1000 == 0:
                    logger.info(f"Bootstrap: fetched {total_fetched} messages...")
                    await self._send_to_admin(f"📊 Progress: `{total_fetched}` messages fetched...")
            
            await self._send_to_admin(f"📥 Processing `{total_fetched}` messages...")
            
            # Process messages in chronological order (oldest first)
            messages_to_process.reverse()
            
            new_signals = 0
            new_alerts = 0
            
            for message in messages_to_process:
                text = message.text
                msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                
                # Check if it's a signal
                if SIGNAL_PATTERN.search(text):
                    symbol_match = TOKEN_PATTERN.search(text)
                    address_match = ADDRESS_PATTERN.search(text)
                    
                    if symbol_match and address_match:
                        symbol = symbol_match.group(1)
                        address = address_match.group(0)
                        
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
                    mult_match = MULTIPLIER_PATTERN.search(text)
                    
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
            
            # Update cursor and mark bootstrap complete
            await self._signal_db.update_channel_cursor(
                channel_id=channel_id,
                channel_name=TRENCHES_CHANNEL_NAME,
                last_message_id=max_message_id,
                mark_bootstrap_complete=True,  # Important!
            )
            
            # Get updated counts
            counts = await self._signal_db.get_signal_count()
            
            message = (
                "✅ *Bootstrap Complete!*\n\n"
                f"• Total Messages Scanned: `{total_fetched}`\n"
                f"• Signals Found: `{new_signals}`\n"
                f"• Profit Alerts Found: `{new_alerts}`\n"
                f"• Cursor Set To: `{max_message_id}`\n\n"
                f"📊 *Database Totals*\n"
                f"• Total Signals: `{counts.get('total_signals', 0)}`\n"
                f"• Total Alerts: `{counts.get('total_profit_alerts', 0)}`\n\n"
                "✨ From now on, use **Sync Signals** to fetch only NEW messages."
            )
            
            await self._send_to_admin(message)
            logger.info(f"Bootstrap complete: {new_signals} signals, {new_alerts} alerts, cursor={max_message_id}")
            
        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            await self._send_to_admin(f"❌ *Bootstrap failed*\n\n`{str(e)}`")
    
    async def record_signal(
        self,
        token_address: str,
        token_symbol: str,
        message_id: int,
        signal_time: Optional[datetime] = None,
        raw_text: Optional[str] = None,
        channel_id: Optional[int] = None,
    ) -> None:
        """
        Record a signal for PnL tracking (LIVE MODE).
        
        Called by the trading bot when a new signal is detected via event handler.
        This is the production-grade live listener pattern - signals come in real-time.
        
        Args:
            token_address: Token contract address
            token_symbol: Token symbol
            message_id: Telegram message ID
            signal_time: Signal timestamp (defaults to now)
            raw_text: Raw message text (optional, for DB storage)
            channel_id: Channel ID (for cursor update)
        """
        # Record to in-memory history (for quick lookups)
        await self._signal_history.add_signal(
            token_address=token_address,
            token_symbol=token_symbol,
            message_id=message_id,
        )
        
        # Also insert into database if available (production persistence)
        if self._signal_db:
            if signal_time is None:
                signal_time = datetime.now(timezone.utc)
            
            # Require raw_text for proper DB storage - don't use placeholder
            if not raw_text:
                logger.warning(f"No raw_text provided for signal ${token_symbol}, skipping DB insert")
                return
            
            inserted = await self._signal_db.insert_signal(
                message_id=message_id,
                token_symbol=token_symbol,
                token_address=token_address,
                signal_time=signal_time,
                raw_text=raw_text,
            )
            
            if inserted:
                logger.debug(f"Signal inserted to DB: ${token_symbol} (msg_id={message_id})")
                
                # Update cursor if channel_id provided
                if channel_id:
                    from src.constants import TRENCHES_CHANNEL_NAME
                    await self._signal_db.update_channel_cursor(
                        channel_id=channel_id,
                        channel_name=TRENCHES_CHANNEL_NAME,
                        last_message_id=message_id,
                    )
    
    async def record_profit_alert(
        self,
        message_id: int,
        reply_to_msg_id: int,
        multiplier: float,
        alert_time: Optional[datetime] = None,
        raw_text: Optional[str] = None,
        channel_id: Optional[int] = None,
    ) -> None:
        """
        Record a profit alert (LIVE MODE).
        
        Called by the trading bot when a profit alert is detected via event handler.
        
        Args:
            message_id: Telegram message ID
            reply_to_msg_id: Original signal message ID
            multiplier: Profit multiplier (e.g., 2.0 for 2X)
            alert_time: Alert timestamp
            raw_text: Raw message text
            channel_id: Channel ID (for cursor update)
        """
        if self._signal_db:
            if alert_time is None:
                alert_time = datetime.now(timezone.utc)
            
            inserted = await self._signal_db.insert_profit_alert(
                message_id=message_id,
                reply_to_msg_id=reply_to_msg_id,
                multiplier=multiplier,
                alert_time=alert_time,
                raw_text=raw_text or f"{multiplier}X profit alert",
            )
            
            if inserted:
                logger.debug(f"Profit alert inserted to DB: {multiplier}X (msg_id={message_id})")
                
                # Update cursor if channel_id provided
                if channel_id:
                    from src.constants import TRENCHES_CHANNEL_NAME
                    await self._signal_db.update_channel_cursor(
                        channel_id=channel_id,
                        channel_name=TRENCHES_CHANNEL_NAME,
                        last_message_id=message_id,
                    )
