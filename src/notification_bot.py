"""
Telegram Bot for notifications and remote control.

This module provides a proper Telegram Bot (via BotFather) for:
- Sending notifications to channels/groups
- Remote control commands from admin
- Wallet setup and configuration
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat

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
    
    Commands (admin only):
        /start - Welcome and wallet setup
        /status - Bot status
        /positions - Open positions  
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
        
        self._initialized = True
        
        # Send startup message
        await self._send_startup_message()
    
    async def stop(self) -> None:
        """Stop the bot client."""
        if self._client:
            await self._client.disconnect()
            self._initialized = False
    
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
    
    async def _handle_command(self, text: str) -> None:
        """Handle bot commands."""
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # Remove bot username if present
        args = parts[1] if len(parts) > 1 else ""
        
        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/positions": self._cmd_positions,
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
                "Use /help to see all commands."
            )
    
    async def _cmd_help(self, args: str) -> None:
        """Show help."""
        help_text = (
            "📚 *AVAILABLE COMMANDS*\n\n"
            "*Status & Monitoring:*\n"
            "• /status - Bot status\n"
            "• /positions - Open positions\n"
            "• /settings - Current settings\n"
            "• /stats - Trading statistics\n\n"
            "*Control:*\n"
            "• /pause - Pause trading\n"
            "• /resume - Resume trading\n\n"
            "*Configuration:*\n"
            "• /setsize `<SOL>` - Buy amount\n"
            "• /setsell `<percent>` - Sell percentage\n"
            "• /setmultiplier `<X>` - Min sell multiplier\n"
            "• /setmax `<count>` - Max positions\n"
            "• /setwallet `<address>` - GMGN wallet\n\n"
            "_Example: /setsize 0.2_"
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
