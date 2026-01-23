"""
Main trading bot orchestrator.

This module contains the core bot class that ties together all components:
- Telegram client management
- Signal parsing
- Trade execution
- State management
- Remote control via Telegram Bot
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.tl.types import Message, Channel

from src.config import Settings
from src.constants import (
    TRENCHES_CHANNEL_NAME,
)
from src.exceptions import (
    ChannelNotFoundError,
    DuplicatePositionError,
    MaxPositionsReachedError,
    TelegramAuthenticationError,
    TelegramConnectionError,
    TradingDisabledError,
)
from src.models import BuySignal, Position, PositionStatus, ProfitAlert
from src.parsers import MessageParser
from src.state import TradingState
from src.trader import GMGNTrader

if TYPE_CHECKING:
    from src.notification_bot import NotificationBot

logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main trading bot that monitors Telegram channel and executes trades.
    
    This class orchestrates all components of the trading system:
    - Connects to Telegram using an existing authenticated session
    - Monitors the signal channel for buy signals and profit alerts
    - Executes trades via the GMGN bot
    - Manages position state and persistence
    - Provides remote control via Telegram
    
    Usage:
        settings = Settings()
        async with TradingBot(settings) as bot:
            await bot.run()
    """
    
    def __init__(self, settings: Settings) -> None:
        """
        Initialize the trading bot.
        
        Args:
            settings: Application settings
        """
        self._settings = settings
        self._client: Optional[TelegramClient] = None
        self._trader: Optional[GMGNTrader] = None
        self._channel_entity: Optional[Channel] = None
        self._state: Optional[TradingState] = None
        self._notification_bot: Optional["NotificationBot"] = None
        self._parser = MessageParser()
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._start_time: Optional[datetime] = None
        self._messages_processed = 0
    
    @property
    def is_running(self) -> bool:
        """Check if bot is currently running."""
        return self._running
    
    @property
    def uptime(self) -> Optional[float]:
        """Get bot uptime in seconds."""
        if self._start_time:
            return (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return None
    
    @property
    def state(self) -> Optional[TradingState]:
        """Get current trading state."""
        return self._state
    
    async def __aenter__(self) -> "TradingBot":
        """Async context manager entry."""
        await self._initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self._shutdown()
    
    async def _initialize(self) -> None:
        """
        Initialize all bot components.
        
        Raises:
            TelegramConnectionError: If connection fails
            TelegramAuthenticationError: If session is not authorized
            ChannelNotFoundError: If signal channel not found
        """
        logger.info("Initializing trading bot...")
        
        # Initialize state manager
        self._state = TradingState(Path(self._settings.state_file))
        
        try:
            self._state.load()
        except Exception as e:
            logger.warning(f"Could not load existing state: {e}")
        
        # Initialize Telegram client
        await self._init_telegram()
        
        # Initialize trader
        await self._init_trader()
        
        # Get channel entity
        await self._init_channel()
        
        # Initialize notification bot for remote management
        await self._init_notification_bot()
        
        logger.info("✅ Trading bot initialized successfully")
    
    async def _init_telegram(self) -> None:
        """Initialize Telegram client connection."""
        telegram = self._settings.telegram
        
        # Determine session path
        # Priority: 1) Explicit SESSION_FILE env var, 2) /app/data/ for containers, 3) Parent dir, 4) Current dir
        import os
        session_file_env = os.getenv("SESSION_FILE")
        
        if session_file_env:
            # Use explicit path from environment variable
            session_path = Path(session_file_env)
            # Remove .session extension if provided
            if session_path.suffix == ".session":
                session_path = session_path.with_suffix("")
        elif Path("/app/data").exists():
            # Running in container - use writable data directory
            session_path = Path("/app/data") / telegram.session_name
        else:
            # Check parent directory first (for local Docker volume mount)
            session_path = Path(__file__).parent.parent / telegram.session_name
            if not session_path.with_suffix(".session").exists():
                session_path = Path(telegram.session_name)
        
        logger.debug(f"Using session path: {session_path}")
        
        self._client = TelegramClient(
            str(session_path),
            telegram.api_id,
            telegram.api_hash,
        )
        
        try:
            await self._client.connect()
        except Exception as e:
            raise TelegramConnectionError(
                "Failed to connect to Telegram", cause=e
            ) from e
        
        if not await self._client.is_user_authorized():
            raise TelegramAuthenticationError(
                "Telegram session not authorized. "
                "Please run the authentication script first."
            )
        
        logger.info("✅ Connected to Telegram")
    
    async def _init_trader(self) -> None:
        """Initialize the GMGN trader."""
        if not self._client:
            raise RuntimeError("Telegram client not initialized")
        
        self._trader = GMGNTrader(
            client=self._client,
            dry_run=self._settings.trading_dry_run,
            bot_username=self._settings.gmgn_bot,
        )
        
        await self._trader.initialize()
    
    async def _init_channel(self) -> None:
        """Initialize channel entity."""
        if not self._client:
            raise RuntimeError("Telegram client not initialized")
        
        try:
            self._channel_entity = await self._client.get_entity(
                self._settings.signal_channel
            )
            logger.info(f"✅ Monitoring channel: {self._channel_entity.title}")
        except Exception as e:
            raise ChannelNotFoundError(self._settings.signal_channel) from e
    
    async def _init_notification_bot(self) -> None:
        """Initialize Telegram notification bot for remote management."""
        if not self._settings.controller_enabled:
            logger.info("Controller disabled, skipping notification bot")
            return
        
        if not self._settings.admin_user_id:
            logger.warning(
                "⚠️ ADMIN_USER_ID not set - notifications disabled. "
                "Set ADMIN_USER_ID in .env to enable."
            )
            return
        
        if not self._settings.bot_token:
            logger.warning(
                "⚠️ BOT_TOKEN not set - notifications disabled. "
                "Create a bot via @BotFather and set BOT_TOKEN in .env"
            )
            return
        
        from src.notification_bot import NotificationBot
        
        self._notification_bot = NotificationBot(
            api_id=self._settings.telegram_api_id,
            api_hash=self._settings.telegram_api_hash,
            bot_token=self._settings.bot_token,
            settings=self._settings,
            admin_user_id=self._settings.admin_user_id,
            notification_channel=self._settings.notification_channel,
        )
        
        self._notification_bot.set_trading_bot(self)
        await self._notification_bot.start()
        logger.info("✅ Notification bot started")
    
    async def _shutdown(self) -> None:
        """Gracefully shutdown the bot."""
        logger.info("Shutting down trading bot...")
        
        self._running = False
        
        # Save state
        if self._state:
            try:
                self._state.save()
            except Exception as e:
                logger.error(f"Failed to save state on shutdown: {e}")
        
        # Stop notification bot
        if self._notification_bot:
            try:
                await self._notification_bot.stop()
            except Exception as e:
                logger.error(f"Error stopping notification bot: {e}")
        
        # Disconnect Telegram
        if self._client:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting Telegram: {e}")
        
        logger.info("🛑 Trading bot stopped")
    
    async def run(self) -> None:
        """
        Start the main bot loop.
        
        This method blocks until shutdown is requested.
        """
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        
        self._print_startup_banner()
        
        # Register event handler
        self._client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=[self._channel_entity])
        )
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("🚀 Bot is now running. Press Ctrl+C to stop.")
        
        try:
            # Keep running until shutdown requested
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        finally:
            self._running = False
    
    def _print_startup_banner(self) -> None:
        """Print startup information."""
        trading = self._settings.trading
        
        print()
        print("=" * 62)
        print("║" + " " * 14 + "SOLANA AUTO TRADING BOT" + " " * 23 + "║")
        print("=" * 62)
        print(f"  Channel:        {TRENCHES_CHANNEL_NAME}")
        print(f"  Buy Amount:     {trading.buy_amount_sol} SOL")
        print(f"  Sell At:        {trading.min_multiplier_to_sell}X ({trading.sell_percentage}%)")
        print(f"  Max Positions:  {trading.max_open_positions}")
        print(f"  Dry Run:        {'Yes' if trading.dry_run else 'No'}")
        print(f"  Open Positions: {self._state.open_position_count if self._state else 0}")
        print("=" * 62)
        
        if trading.dry_run:
            print("⚠️  DRY RUN MODE - No real trades will be executed")
        else:
            print("🔴 LIVE TRADING MODE - Real trades will be executed!")
        print()
    
    def _setup_signal_handlers(self) -> None:
        """Setup OS signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._request_shutdown)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    def _request_shutdown(self) -> None:
        """Request graceful shutdown."""
        logger.info("Shutdown requested...")
        self._shutdown_event.set()
    
    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """
        Handle new messages from the channel (LIVE MODE).
        
        This is the production-grade event-based listener pattern.
        Messages are processed as they arrive in real-time.
        
        Args:
            event: Telethon new message event
        """
        message: Message = event.message
        
        if not message.text:
            return
        
        self._messages_processed += 1
        
        # Get message metadata for database storage
        msg_time = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
        channel_id = self._channel_entity.id if self._channel_entity else None
        
        # Get reply information
        reply_to_msg_id = message.reply_to_msg_id if message.reply_to else None
        
        # Parse message
        result = self._parser.parse(
            message_id=message.id,
            text=message.text,
            reply_to_msg_id=reply_to_msg_id,
        )
        
        # Handle buy signal
        if result.buy_signal:
            await self._handle_buy_signal(result.buy_signal)
        
        # Handle profit alert
        if result.profit_alert:
            await self._handle_profit_alert(result.profit_alert)
    
    async def _handle_buy_signal(self, signal: BuySignal) -> None:
        """
        Handle a buy signal.
        
        Args:
            signal: Parsed buy signal
        """
        # Use notification bot settings if available, otherwise use static settings
        if self._notification_bot:
            buy_amount = self._notification_bot.buy_amount_sol
            max_positions = self._notification_bot.max_positions
            trading_paused = self._notification_bot.is_trading_paused
            wallet_configured = self._notification_bot.is_wallet_configured
        else:
            buy_amount = self._settings.trading_buy_amount_sol
            max_positions = self._settings.trading_max_positions
            trading_paused = False
            wallet_configured = True  # Assume configured if no notification bot
        
        trading = self._settings.trading
        
        logger.info(
            f"📨 Buy signal: ${signal.token_symbol} "
            f"({signal.token_address[:12]}...)"
        )
        
        # Notify about the signal and record for PnL tracking (LIVE MODE)
        if self._notification_bot:
            await self._notification_bot.notify_signal(
                token_symbol=signal.token_symbol,
                token_address=signal.token_address,
                signal_type="BUY",
            )
            # Record signal to database (live mode - updates cursor automatically)
            await self._notification_bot.record_signal(
                token_address=signal.token_address,
                token_symbol=signal.token_symbol,
                message_id=signal.message_id,
                signal_time=signal.timestamp,
                raw_text=signal.raw_text,
                channel_id=self._channel_entity.id if self._channel_entity else None,
            )
        
        # Check if wallet is configured
        if not wallet_configured:
            logger.info("Wallet not configured, skipping trade")
            return
        
        # Check if trading is paused
        if trading_paused:
            logger.info("Trading paused, skipping")
            return
        
        # Check if trading is enabled
        if not trading.enabled:
            logger.info("Trading disabled, skipping")
            return
        
        # Check for existing position
        if self._state and self._state.has_position(signal.token_address):
            existing = self._state.get_position(signal.token_address)
            if existing and existing.status != PositionStatus.CLOSED:
                logger.info(f"Already have position in ${signal.token_symbol}, skipping")
                return
        
        # Check max positions
        if self._state and self._state.open_position_count >= max_positions:
            logger.warning(
                f"Max positions ({max_positions}) reached, skipping"
            )
            return
        
        # Execute buy
        if not self._trader:
            logger.error("Trader not initialized")
            return
        
        result = await self._trader.buy_token(
            token_address=signal.token_address,
            amount_sol=buy_amount,
            symbol=signal.token_symbol,
        )
        
        # Notify about trade execution
        if self._notification_bot:
            await self._notification_bot.notify_trade(
                action="BUY",
                token_symbol=signal.token_symbol,
                amount_sol=buy_amount,
                success=result.success,
                error=result.error if not result.success else None,
            )
        
        if result.success and self._state:
            # Record position
            position = Position(
                token_address=signal.token_address,
                token_symbol=signal.token_symbol,
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=buy_amount,
                signal_msg_id=signal.message_id,
            )
            
            try:
                await self._state.add_position(
                    position,
                    max_positions=max_positions,
                )
                logger.info(f"✅ Position opened: ${signal.token_symbol}")
            except (DuplicatePositionError, MaxPositionsReachedError) as e:
                logger.warning(f"Could not add position: {e}")
    
    async def _handle_profit_alert(self, alert: ProfitAlert) -> None:
        """
        Handle a profit alert (potential sell signal).
        
        Args:
            alert: Parsed profit alert
        """
        # Use notification bot settings if available
        if self._notification_bot:
            min_multiplier = self._notification_bot.min_multiplier
            sell_percentage = self._notification_bot.sell_percentage
            trading_paused = self._notification_bot.is_trading_paused
        else:
            min_multiplier = self._settings.trading_min_multiplier
            sell_percentage = self._settings.trading_sell_percentage
            trading_paused = False
        
        trading = self._settings.trading
        
        logger.info(
            f"📨 Profit alert: {alert.multiplier}X "
            f"(reply to msg {alert.reply_to_msg_id})"
        )
        
        # Record profit alert to database (LIVE MODE)
        if self._notification_bot:
            await self._notification_bot.record_profit_alert(
                message_id=alert.message_id,
                reply_to_msg_id=alert.reply_to_msg_id,
                multiplier=alert.multiplier,
                alert_time=alert.timestamp if hasattr(alert, 'timestamp') else None,
                raw_text=alert.raw_text if hasattr(alert, 'raw_text') else None,
                channel_id=self._channel_entity.id if self._channel_entity else None,
            )
        
        # Find position
        if not self._state:
            return
        
        position = self._state.get_position_by_signal(alert.reply_to_msg_id)
        
        if not position:
            logger.debug(f"No position found for signal {alert.reply_to_msg_id}")
            return
        
        # Update multiplier
        position.last_multiplier = alert.multiplier
        
        # Determine if we should sell
        will_sell = (
            alert.multiplier >= min_multiplier and 
            position.status not in (PositionStatus.PARTIAL_SOLD, PositionStatus.CLOSED) and
            not trading_paused
        )
        
        # Notify about profit alert
        if self._notification_bot:
            await self._notification_bot.notify_profit_alert(
                token_symbol=position.token_symbol,
                multiplier=alert.multiplier,
                will_sell=will_sell,
            )
        
        # Check if we should sell
        if alert.multiplier < min_multiplier:
            logger.debug(
                f"Multiplier {alert.multiplier}X below threshold "
                f"{min_multiplier}X"
            )
            return
        
        # Check if trading is paused
        if trading_paused:
            logger.info("Trading paused, skipping sell")
            return
        
        # Check if already sold at this level
        if position.status == PositionStatus.PARTIAL_SOLD:
            logger.info(
                f"Already sold {position.sold_percentage}% of "
                f"${position.token_symbol}, skipping"
            )
            return
        
        if position.status == PositionStatus.CLOSED:
            logger.info(f"Position ${position.token_symbol} already closed")
            return
        
        # Execute sell
        if not self._trader:
            logger.error("Trader not initialized")
            return
        
        result = await self._trader.sell_token(
            token_address=position.token_address,
            percentage=sell_percentage,
            symbol=position.token_symbol,
        )
        
        # Notify about trade execution
        if self._notification_bot:
            await self._notification_bot.notify_trade(
                action="SELL",
                token_symbol=position.token_symbol,
                amount_sol=position.buy_amount_sol * (sell_percentage / 100),
                success=result.success,
                multiplier=alert.multiplier,
                error=result.error if not result.success else None,
            )
        
        if result.success:
            await self._state.mark_partial_sell(
                token_address=position.token_address,
                percentage=float(sell_percentage),
                multiplier=alert.multiplier,
            )
            logger.info(
                f"✅ Sold {sell_percentage}% of "
                f"${position.token_symbol} at {alert.multiplier}X"
            )
    
    def get_status(self) -> dict[str, Any]:
        """
        Get current bot status.
        
        Returns:
            Dictionary with status information
        """
        trading = self._settings.trading
        
        status = {
            "running": self._running,
            "uptime_seconds": self.uptime,
            "messages_processed": self._messages_processed,
            "dry_run": trading.dry_run,
            "trading_enabled": trading.enabled,
        }
        
        if self._state:
            status["positions"] = self._state.get_statistics()
        
        if self._trader:
            status["trades_executed"] = self._trader.trade_count
        
        return status


@asynccontextmanager
async def create_bot(settings: Settings) -> AsyncIterator[TradingBot]:
    """
    Create and initialize a trading bot.
    
    This is the preferred way to create a bot instance as it ensures
    proper initialization and cleanup.
    
    Args:
        settings: Application settings
        
    Yields:
        Initialized TradingBot instance
        
    Example:
        async with create_bot(settings) as bot:
            await bot.run()
    """
    bot = TradingBot(settings)
    try:
        await bot._initialize()
        yield bot
    finally:
        await bot._shutdown()
