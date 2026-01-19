"""
Trading execution interface for GMGN bot integration.

This module provides a clean abstraction over the GMGN Telegram bot,
handling command formatting, retries, and error recovery.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, Protocol

from telethon import TelegramClient
from telethon.tl.types import User

from src.constants import GMGN_BOT_USERNAME, RETRY_ATTEMPTS, RETRY_BACKOFF_FACTOR
from src.exceptions import BotNotFoundError, TradeExecutionError
from src.models import TradeResult

logger = logging.getLogger(__name__)


class TraderProtocol(Protocol):
    """Protocol defining the trader interface."""
    
    async def initialize(self) -> None:
        """Initialize the trader connection."""
        ...
    
    async def buy_token(
        self,
        token_address: str,
        amount_sol: float,
        symbol: str
    ) -> TradeResult:
        """Execute a buy order."""
        ...
    
    async def sell_token(
        self,
        token_address: str,
        percentage: int,
        symbol: str
    ) -> TradeResult:
        """Execute a sell order."""
        ...
    
    @property
    def is_initialized(self) -> bool:
        """Check if trader is initialized and ready."""
        ...


class BaseTrader(ABC):
    """Abstract base class for trade execution."""
    
    def __init__(self, dry_run: bool = True) -> None:
        self._dry_run = dry_run
        self._initialized = False
    
    @property
    def dry_run(self) -> bool:
        """Check if running in dry run mode."""
        return self._dry_run
    
    @property
    def is_initialized(self) -> bool:
        """Check if trader is initialized."""
        return self._initialized
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the trader connection."""
        pass
    
    @abstractmethod
    async def buy_token(
        self,
        token_address: str,
        amount_sol: float,
        symbol: str
    ) -> TradeResult:
        """Execute a buy order."""
        pass
    
    @abstractmethod
    async def sell_token(
        self,
        token_address: str,
        percentage: int,
        symbol: str
    ) -> TradeResult:
        """Execute a sell order."""
        pass


class GMGNTrader(BaseTrader):
    """
    Trade executor using GMGN Telegram bot.
    
    GMGN bot accepts commands in the following formats:
    - Buy: /buy <token_address> <amount_sol>
    - Sell: /sell <token_address> <percentage>%
    
    This class handles command formatting, sending, and error recovery.
    """
    
    def __init__(
        self,
        client: TelegramClient,
        dry_run: bool = True,
        bot_username: str = GMGN_BOT_USERNAME,
    ) -> None:
        """
        Initialize GMGN trader.
        
        Args:
            client: Authenticated Telegram client
            dry_run: If True, don't execute real trades
            bot_username: GMGN bot username
        """
        super().__init__(dry_run)
        self._client = client
        self._bot_username = bot_username
        self._bot_entity: Optional[User] = None
        self._trade_count = 0
    
    async def initialize(self) -> None:
        """
        Initialize connection to GMGN bot.
        
        Raises:
            BotNotFoundError: If GMGN bot cannot be found
        """
        try:
            self._bot_entity = await self._client.get_entity(self._bot_username)
            self._initialized = True
            logger.info(f"✅ Connected to GMGN bot: @{self._bot_username}")
        except Exception as e:
            logger.error(f"Failed to connect to GMGN bot: {e}")
            raise BotNotFoundError(self._bot_username) from e
    
    async def buy_token(
        self,
        token_address: str,
        amount_sol: float,
        symbol: str
    ) -> TradeResult:
        """
        Execute a buy order via GMGN bot.
        
        Args:
            token_address: Solana token mint address
            amount_sol: Amount of SOL to spend
            symbol: Token symbol for logging
            
        Returns:
            TradeResult with execution status
            
        Raises:
            TradeExecutionError: If trade execution fails
        """
        logger.info(f"🟢 BUY: ${symbol} ({token_address[:12]}...) - {amount_sol} SOL")
        
        if self._dry_run:
            logger.info(f"[DRY RUN] Would buy {amount_sol} SOL of ${symbol}")
            return TradeResult(
                success=True,
                token_address=token_address,
                token_symbol=symbol,
                action="buy",
                amount=amount_sol,
                message=f"[DRY RUN] Buy simulated: {amount_sol} SOL",
                dry_run=True,
            )
        
        command = f"/buy {token_address} {amount_sol}"
        return await self._execute_trade(
            command=command,
            token_address=token_address,
            symbol=symbol,
            action="buy",
            amount=amount_sol,
        )
    
    async def sell_token(
        self,
        token_address: str,
        percentage: int,
        symbol: str
    ) -> TradeResult:
        """
        Execute a sell order via GMGN bot.
        
        Args:
            token_address: Solana token mint address
            percentage: Percentage of position to sell
            symbol: Token symbol for logging
            
        Returns:
            TradeResult with execution status
            
        Raises:
            TradeExecutionError: If trade execution fails
        """
        logger.info(f"🔴 SELL: ${symbol} ({token_address[:12]}...) - {percentage}%")
        
        if self._dry_run:
            logger.info(f"[DRY RUN] Would sell {percentage}% of ${symbol}")
            return TradeResult(
                success=True,
                token_address=token_address,
                token_symbol=symbol,
                action="sell",
                amount=float(percentage),
                message=f"[DRY RUN] Sell simulated: {percentage}%",
                dry_run=True,
            )
        
        command = f"/sell {token_address} {percentage}%"
        return await self._execute_trade(
            command=command,
            token_address=token_address,
            symbol=symbol,
            action="sell",
            amount=float(percentage),
        )
    
    async def _execute_trade(
        self,
        command: str,
        token_address: str,
        symbol: str,
        action: str,
        amount: float,
    ) -> TradeResult:
        """
        Execute a trade command with retry logic.
        
        Args:
            command: Command to send to GMGN bot
            token_address: Token address for the trade
            symbol: Token symbol
            action: Trade action (buy/sell)
            amount: Trade amount
            
        Returns:
            TradeResult with execution status
        """
        if not self._initialized or self._bot_entity is None:
            raise TradeExecutionError(
                action=action,
                token_address=token_address,
                token_symbol=symbol,
                cause=RuntimeError("Trader not initialized"),
            )
        
        last_error: Optional[Exception] = None
        
        for attempt in range(RETRY_ATTEMPTS):
            try:
                await self._client.send_message(self._bot_entity, command)
                self._trade_count += 1
                
                logger.info(f"✅ {action.upper()} order sent for ${symbol}")
                
                return TradeResult(
                    success=True,
                    token_address=token_address,
                    token_symbol=symbol,
                    action=action,
                    amount=amount,
                    message=f"Order sent successfully: {command}",
                )
                
            except Exception as e:
                last_error = e
                wait_time = RETRY_BACKOFF_FACTOR ** attempt
                logger.warning(
                    f"Trade attempt {attempt + 1}/{RETRY_ATTEMPTS} failed: {e}. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
        
        # All retries exhausted
        logger.error(f"❌ {action.upper()} order failed for ${symbol} after {RETRY_ATTEMPTS} attempts")
        
        return TradeResult(
            success=False,
            token_address=token_address,
            token_symbol=symbol,
            action=action,
            amount=amount,
            message=f"Order failed after {RETRY_ATTEMPTS} attempts: {last_error}",
        )
    
    @property
    def trade_count(self) -> int:
        """Get total number of trades executed."""
        return self._trade_count


class MockTrader(BaseTrader):
    """
    Mock trader for testing purposes.
    
    Records all trade attempts without executing them.
    """
    
    def __init__(self) -> None:
        super().__init__(dry_run=True)
        self.trades: list[TradeResult] = []
    
    async def initialize(self) -> None:
        """Initialize mock trader."""
        self._initialized = True
        logger.info("Mock trader initialized")
    
    async def buy_token(
        self,
        token_address: str,
        amount_sol: float,
        symbol: str
    ) -> TradeResult:
        """Record a mock buy."""
        result = TradeResult(
            success=True,
            token_address=token_address,
            token_symbol=symbol,
            action="buy",
            amount=amount_sol,
            message="Mock buy executed",
            dry_run=True,
        )
        self.trades.append(result)
        return result
    
    async def sell_token(
        self,
        token_address: str,
        percentage: int,
        symbol: str
    ) -> TradeResult:
        """Record a mock sell."""
        result = TradeResult(
            success=True,
            token_address=token_address,
            token_symbol=symbol,
            action="sell",
            amount=float(percentage),
            message="Mock sell executed",
            dry_run=True,
        )
        self.trades.append(result)
        return result
