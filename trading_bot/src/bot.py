"""
Main trading bot orchestrator.

This module contains the core bot class that ties together all components:
- Telegram client management
- Signal parsing
- Trade execution
- State management
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

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

logger = logging.getLogger(__name__)


class TradingBot:
    """
    Main trading bot that monitors Telegram channel and executes trades.
    
    This class orchestrates all components of the trading system:
    - Connects to Telegram using an existing authenticated session
    - Monitors the signal channel for buy signals and profit alerts
    - Executes trades via the GMGN bot
    - Manages position state and persistence
    
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
        
        logger.info("✅ Trading bot initialized successfully")
    
    async def _init_telegram(self) -> None:
        """Initialize Telegram client connection."""
        telegram = self._settings.telegram
        
        # Determine session path - check parent directory first (for Docker volume mount)
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
        Handle new messages from the channel.
        
        Args:
            event: Telethon new message event
        """
        message: Message = event.message
        
        if not message.text:
            return
        
        self._messages_processed += 1
        
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
        trading = self._settings.trading
        
        logger.info(
            f"📨 Buy signal: ${signal.token_symbol} "
            f"({signal.token_address[:12]}...)"
        )
        
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
        if self._state and self._state.open_position_count >= trading.max_open_positions:
            logger.warning(
                f"Max positions ({trading.max_open_positions}) reached, skipping"
            )
            return
        
        # Execute buy
        if not self._trader:
            logger.error("Trader not initialized")
            return
        
        result = await self._trader.buy_token(
            token_address=signal.token_address,
            amount_sol=trading.buy_amount_sol,
            symbol=signal.token_symbol,
        )
        
        if result.success and self._state:
            # Record position
            position = Position(
                token_address=signal.token_address,
                token_symbol=signal.token_symbol,
                buy_time=datetime.now(timezone.utc),
                buy_amount_sol=trading.buy_amount_sol,
                signal_msg_id=signal.message_id,
            )
            
            try:
                await self._state.add_position(
                    position,
                    max_positions=trading.max_open_positions,
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
        trading = self._settings.trading
        
        logger.info(
            f"📨 Profit alert: {alert.multiplier}X "
            f"(reply to msg {alert.reply_to_msg_id})"
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
        
        # Check if we should sell
        if alert.multiplier < trading.min_multiplier_to_sell:
            logger.debug(
                f"Multiplier {alert.multiplier}X below threshold "
                f"{trading.min_multiplier_to_sell}X"
            )
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
            percentage=trading.sell_percentage,
            symbol=position.token_symbol,
        )
        
        if result.success:
            await self._state.mark_partial_sell(
                token_address=position.token_address,
                percentage=float(trading.sell_percentage),
                multiplier=alert.multiplier,
            )
            logger.info(
                f"✅ Sold {trading.sell_percentage}% of "
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
