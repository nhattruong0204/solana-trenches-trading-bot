"""
Telegram Bot Controller for remote management.

This module provides a Telegram bot interface for:
- Starting/stopping the trading bot
- Monitoring bot status and positions
- Receiving notifications for signals and trades
- Adjusting trading parameters on-the-fly
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.tl.types import User

if TYPE_CHECKING:
    from src.bot import TradingBot
    from src.config import Settings

logger = logging.getLogger(__name__)


class TelegramController:
    """
    Remote control interface via Telegram.
    
    Provides commands for monitoring and controlling the trading bot
    through a Telegram chat with the user.
    
    Commands:
        /start - Welcome message and help
        /status - Current bot status
        /positions - List open positions
        /settings - Current trading settings
        /setsize <amount> - Set buy amount in SOL
        /pause - Pause trading
        /resume - Resume trading
        /help - Show all commands
    """
    
    def __init__(
        self,
        client: TelegramClient,
        settings: "Settings",
        admin_user_id: int,
    ) -> None:
        """
        Initialize controller.
        
        Args:
            client: Authenticated Telegram client
            settings: Application settings
            admin_user_id: Telegram user ID allowed to control the bot
        """
        self._client = client
        self._settings = settings
        self._admin_user_id = admin_user_id
        self._bot: Optional["TradingBot"] = None
        self._trading_paused = False
        self._initialized = False
        
        # Dynamic settings that can be changed at runtime
        self._buy_amount_sol: float = settings.trading_buy_amount_sol
        self._sell_percentage: int = settings.trading_sell_percentage
        self._min_multiplier: float = settings.trading_min_multiplier
        self._max_positions: int = settings.trading_max_positions
    
    def set_bot(self, bot: "TradingBot") -> None:
        """Set the trading bot reference."""
        self._bot = bot
    
    @property
    def buy_amount_sol(self) -> float:
        """Get current buy amount."""
        return self._buy_amount_sol
    
    @property
    def sell_percentage(self) -> int:
        """Get current sell percentage."""
        return self._sell_percentage
    
    @property
    def min_multiplier(self) -> float:
        """Get minimum multiplier to trigger sell."""
        return self._min_multiplier
    
    @property
    def max_positions(self) -> int:
        """Get maximum open positions."""
        return self._max_positions
    
    @property
    def is_trading_paused(self) -> bool:
        """Check if trading is paused."""
        return self._trading_paused
    
    async def initialize(self) -> None:
        """Initialize the controller and register handlers."""
        if self._initialized:
            return
        
        # Register command handlers
        self._client.add_event_handler(
            self._handle_command,
            events.NewMessage(from_users=[self._admin_user_id])
        )
        
        self._initialized = True
        logger.info(f"✅ Controller initialized for admin user: {self._admin_user_id}")
        
        # Send startup notification
        await self.notify("🤖 *Trading Bot Controller Started*\n\nUse /help to see available commands.")
    
    async def notify(self, message: str) -> None:
        """
        Send notification to admin user.
        
        Args:
            message: Message text (supports Markdown)
        """
        try:
            await self._client.send_message(
                self._admin_user_id,
                message,
                parse_mode="markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    async def notify_signal(
        self,
        token_symbol: str,
        token_address: str,
        signal_type: str = "BUY",
    ) -> None:
        """
        Notify about a new signal from the channel.
        
        Args:
            token_symbol: Token symbol
            token_address: Token mint address
            signal_type: Type of signal (BUY/SELL)
        """
        emoji = "🟢" if signal_type == "BUY" else "🔴"
        
        message = (
            f"{emoji} *NEW SIGNAL DETECTED*\n\n"
            f"• Type: `{signal_type}`\n"
            f"• Token: `${token_symbol}`\n"
            f"• Address: `{token_address[:20]}...`\n"
            f"• Time: `{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}`"
        )
        
        if self._trading_paused:
            message += "\n\n⚠️ _Trading is PAUSED - no action taken_"
        
        await self.notify(message)
    
    async def notify_trade(
        self,
        action: str,
        token_symbol: str,
        amount_sol: float,
        success: bool,
        multiplier: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Notify about a trade execution.
        
        Args:
            action: BUY or SELL
            token_symbol: Token symbol
            amount_sol: Amount in SOL
            success: Whether trade succeeded
            multiplier: Price multiplier (for sells)
            error: Error message if failed
        """
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
            message += f"• Multiplier: `{multiplier}X`\n"
        
        message += f"• Mode: {mode}"
        
        if error:
            message += f"\n• Error: `{error}`"
        
        await self.notify(message)
    
    async def notify_profit_alert(
        self,
        token_symbol: str,
        multiplier: float,
        will_sell: bool,
    ) -> None:
        """
        Notify about a profit alert.
        
        Args:
            token_symbol: Token symbol
            multiplier: Current price multiplier
            will_sell: Whether bot will sell
        """
        emoji = "📈" if will_sell else "📊"
        action = "SELLING" if will_sell else "HOLDING"
        
        message = (
            f"{emoji} *PROFIT ALERT*\n\n"
            f"• Token: `${token_symbol}`\n"
            f"• Multiplier: `{multiplier}X`\n"
            f"• Threshold: `{self._min_multiplier}X`\n"
            f"• Action: `{action}`"
        )
        
        if self._trading_paused and will_sell:
            message += "\n\n⚠️ _Trading is PAUSED - no sell executed_"
        
        await self.notify(message)
    
    async def _handle_command(self, event: events.NewMessage.Event) -> None:
        """Handle incoming commands from admin user."""
        message = event.message
        if not message.text:
            return
        
        text = message.text.strip()
        
        # Only process commands
        if not text.startswith("/"):
            return
        
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Route to handler
        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/positions": self._cmd_positions,
            "/settings": self._cmd_settings,
            "/setsize": self._cmd_set_size,
            "/setsell": self._cmd_set_sell,
            "/setmultiplier": self._cmd_set_multiplier,
            "/setmax": self._cmd_set_max_positions,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/stats": self._cmd_stats,
        }
        
        handler = handlers.get(command)
        if handler:
            await handler(args)
        else:
            await self.notify(f"❓ Unknown command: `{command}`\n\nUse /help for available commands.")
    
    async def _cmd_start(self, args: str) -> None:
        """Welcome message."""
        await self.notify(
            "🤖 *Solana Trading Bot Controller*\n\n"
            "Welcome! This bot allows you to control and monitor your trading bot.\n\n"
            "Use /help to see all available commands."
        )
    
    async def _cmd_help(self, args: str) -> None:
        """Show help message."""
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
            "• /setmax `<count>` - Max positions\n\n"
            "_Example: /setsize 0.2_"
        )
        await self.notify(help_text)
    
    async def _cmd_status(self, args: str) -> None:
        """Show bot status."""
        if not self._bot:
            await self.notify("❌ Bot not connected")
            return
        
        status = self._bot.get_status()
        
        # Format uptime
        uptime_sec = status.get("uptime_seconds", 0)
        if uptime_sec:
            hours = int(uptime_sec // 3600)
            minutes = int((uptime_sec % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = "N/A"
        
        running_emoji = "🟢" if status.get("running") else "🔴"
        trading_emoji = "⏸️" if self._trading_paused else "▶️"
        dry_run = "Yes" if status.get("dry_run") else "No"
        
        message = (
            f"📊 *BOT STATUS*\n\n"
            f"• Running: {running_emoji} `{'Yes' if status.get('running') else 'No'}`\n"
            f"• Trading: {trading_emoji} `{'Paused' if self._trading_paused else 'Active'}`\n"
            f"• Dry Run: `{dry_run}`\n"
            f"• Uptime: `{uptime_str}`\n"
            f"• Messages: `{status.get('messages_processed', 0)}`\n"
            f"• Trades: `{status.get('trades_executed', 0)}`"
        )
        
        await self.notify(message)
    
    async def _cmd_positions(self, args: str) -> None:
        """Show open positions."""
        if not self._bot or not self._bot.state:
            await self.notify("❌ No positions data available")
            return
        
        positions = self._bot.state.open_positions
        
        if not positions:
            await self.notify("📭 *No open positions*")
            return
        
        message = f"📈 *OPEN POSITIONS ({len(positions)})*\n\n"
        
        for addr, pos in positions.items():
            holding_hours = pos.holding_duration
            est_value = pos.estimated_value_sol
            
            message += (
                f"• `${pos.token_symbol}`\n"
                f"  Bought: `{pos.buy_amount_sol} SOL`\n"
                f"  Multiplier: `{pos.last_multiplier}X`\n"
                f"  Est. Value: `{est_value:.4f} SOL`\n"
                f"  Holding: `{holding_hours:.1f}h`\n"
                f"  Sold: `{pos.sold_percentage}%`\n\n"
            )
        
        await self.notify(message)
    
    async def _cmd_settings(self, args: str) -> None:
        """Show current settings."""
        dry_run = "Yes" if self._settings.trading_dry_run else "No"
        paused = "Yes" if self._trading_paused else "No"
        
        message = (
            "⚙️ *TRADING SETTINGS*\n\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Sell Percentage: `{self._sell_percentage}%`\n"
            f"• Min Multiplier: `{self._min_multiplier}X`\n"
            f"• Max Positions: `{self._max_positions}`\n"
            f"• Dry Run: `{dry_run}`\n"
            f"• Paused: `{paused}`\n\n"
            f"_Use /set commands to modify_"
        )
        
        await self.notify(message)
    
    async def _cmd_set_size(self, args: str) -> None:
        """Set buy amount."""
        if not args:
            await self.notify(
                "❌ Usage: `/setsize <amount>`\n\n"
                f"Current: `{self._buy_amount_sol} SOL`\n"
                "Example: `/setsize 0.2`"
            )
            return
        
        try:
            amount = float(args.strip())
            if amount < 0.001:
                await self.notify("❌ Amount must be at least `0.001 SOL`")
                return
            if amount > 100:
                await self.notify("❌ Amount cannot exceed `100 SOL`")
                return
            
            old_amount = self._buy_amount_sol
            self._buy_amount_sol = amount
            
            await self.notify(
                f"✅ *Buy amount updated*\n\n"
                f"• Old: `{old_amount} SOL`\n"
                f"• New: `{self._buy_amount_sol} SOL`"
            )
        except ValueError:
            await self.notify("❌ Invalid amount. Use a number like `0.1`")
    
    async def _cmd_set_sell(self, args: str) -> None:
        """Set sell percentage."""
        if not args:
            await self.notify(
                "❌ Usage: `/setsell <percent>`\n\n"
                f"Current: `{self._sell_percentage}%`\n"
                "Example: `/setsell 50`"
            )
            return
        
        try:
            percent = int(args.strip())
            if percent < 1 or percent > 100:
                await self.notify("❌ Percentage must be between `1` and `100`")
                return
            
            old_percent = self._sell_percentage
            self._sell_percentage = percent
            
            await self.notify(
                f"✅ *Sell percentage updated*\n\n"
                f"• Old: `{old_percent}%`\n"
                f"• New: `{self._sell_percentage}%`"
            )
        except ValueError:
            await self.notify("❌ Invalid percentage. Use a number like `50`")
    
    async def _cmd_set_multiplier(self, args: str) -> None:
        """Set minimum multiplier to trigger sell."""
        if not args:
            await self.notify(
                "❌ Usage: `/setmultiplier <X>`\n\n"
                f"Current: `{self._min_multiplier}X`\n"
                "Example: `/setmultiplier 2.5`"
            )
            return
        
        try:
            # Remove 'X' suffix if present
            value = args.strip().rstrip("Xx")
            multiplier = float(value)
            
            if multiplier < 1.1:
                await self.notify("❌ Multiplier must be at least `1.1X`")
                return
            if multiplier > 100:
                await self.notify("❌ Multiplier cannot exceed `100X`")
                return
            
            old_mult = self._min_multiplier
            self._min_multiplier = multiplier
            
            await self.notify(
                f"✅ *Min multiplier updated*\n\n"
                f"• Old: `{old_mult}X`\n"
                f"• New: `{self._min_multiplier}X`"
            )
        except ValueError:
            await self.notify("❌ Invalid multiplier. Use a number like `2.5`")
    
    async def _cmd_set_max_positions(self, args: str) -> None:
        """Set maximum open positions."""
        if not args:
            await self.notify(
                "❌ Usage: `/setmax <count>`\n\n"
                f"Current: `{self._max_positions}`\n"
                "Example: `/setmax 5`"
            )
            return
        
        try:
            count = int(args.strip())
            if count < 1:
                await self.notify("❌ Max positions must be at least `1`")
                return
            if count > 100:
                await self.notify("❌ Max positions cannot exceed `100`")
                return
            
            old_max = self._max_positions
            self._max_positions = count
            
            await self.notify(
                f"✅ *Max positions updated*\n\n"
                f"• Old: `{old_max}`\n"
                f"• New: `{self._max_positions}`"
            )
        except ValueError:
            await self.notify("❌ Invalid count. Use a number like `5`")
    
    async def _cmd_pause(self, args: str) -> None:
        """Pause trading."""
        if self._trading_paused:
            await self.notify("⚠️ Trading is already paused")
            return
        
        self._trading_paused = True
        await self.notify(
            "⏸️ *TRADING PAUSED*\n\n"
            "The bot will continue monitoring signals but will not execute trades.\n\n"
            "Use /resume to resume trading."
        )
    
    async def _cmd_resume(self, args: str) -> None:
        """Resume trading."""
        if not self._trading_paused:
            await self.notify("⚠️ Trading is not paused")
            return
        
        self._trading_paused = False
        await self.notify(
            "▶️ *TRADING RESUMED*\n\n"
            "The bot will now execute trades on signals.\n\n"
            f"• Buy Amount: `{self._buy_amount_sol} SOL`\n"
            f"• Dry Run: `{'Yes' if self._settings.trading_dry_run else 'No'}`"
        )
    
    async def _cmd_stats(self, args: str) -> None:
        """Show trading statistics."""
        if not self._bot or not self._bot.state:
            await self.notify("❌ No statistics available")
            return
        
        stats = self._bot.state.get_statistics()
        
        message = (
            "📊 *TRADING STATISTICS*\n\n"
            f"• Total Positions: `{stats.get('total_positions', 0)}`\n"
            f"• Open Positions: `{stats.get('open_positions', 0)}`\n"
            f"• Closed Positions: `{stats.get('closed_positions', 0)}`\n"
            f"• Partial Sold: `{stats.get('partial_sold_positions', 0)}`\n"
        )
        
        if "total_invested_sol" in stats:
            message += f"• Total Invested: `{stats['total_invested_sol']:.4f} SOL`\n"
        
        await self.notify(message)
