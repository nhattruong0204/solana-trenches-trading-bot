"""
Domain models and entities.

This module defines the core data structures used throughout
the trading bot application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class PositionStatus(str, Enum):
    """Status of a trading position."""
    
    OPEN = "open"
    PARTIAL_SOLD = "partial_sold"
    CLOSED = "closed"
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=False, slots=True)
class Position:
    """
    Represents a trading position in a token.
    
    Attributes:
        token_address: Solana token mint address (base58)
        token_symbol: Human-readable token symbol (e.g., "TRUMP")
        buy_time: UTC timestamp when position was opened
        buy_amount_sol: Amount of SOL used to buy
        signal_msg_id: Telegram message ID that triggered the buy
        status: Current position status
        sold_percentage: Percentage of position already sold
        last_multiplier: Most recent price multiplier seen
    """
    
    token_address: str
    token_symbol: str
    buy_time: datetime
    buy_amount_sol: float
    signal_msg_id: int
    status: PositionStatus = PositionStatus.OPEN
    sold_percentage: float = 0.0
    last_multiplier: float = 1.0
    
    def __post_init__(self) -> None:
        """Validate position data after initialization."""
        if not self.token_address:
            raise ValueError("Token address cannot be empty")
        if self.buy_amount_sol <= 0:
            raise ValueError("Buy amount must be positive")
        if not 0 <= self.sold_percentage <= 100:
            raise ValueError("Sold percentage must be between 0 and 100")
    
    @property
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.status == PositionStatus.OPEN
    
    @property
    def is_partially_sold(self) -> bool:
        """Check if position is partially sold."""
        return self.status == PositionStatus.PARTIAL_SOLD
    
    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.status == PositionStatus.CLOSED
    
    @property
    def remaining_percentage(self) -> float:
        """Calculate remaining position percentage."""
        return 100.0 - self.sold_percentage
    
    @property
    def estimated_value_sol(self) -> float:
        """Estimate current value based on multiplier."""
        remaining_fraction = self.remaining_percentage / 100.0
        return self.buy_amount_sol * remaining_fraction * self.last_multiplier
    
    @property
    def holding_duration(self) -> float:
        """Get holding duration in hours."""
        now = datetime.now(timezone.utc)
        delta = now - self.buy_time
        return delta.total_seconds() / 3600
    
    def to_dict(self) -> dict[str, Any]:
        """
        Serialize position to dictionary.
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        return {
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "buy_time": self.buy_time.isoformat(),
            "buy_amount_sol": self.buy_amount_sol,
            "signal_msg_id": self.signal_msg_id,
            "status": self.status.value,
            "sold_percentage": self.sold_percentage,
            "last_multiplier": self.last_multiplier,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        """
        Deserialize position from dictionary.
        
        Args:
            data: Dictionary containing position data
            
        Returns:
            Position instance
            
        Raises:
            KeyError: If required fields are missing
            ValueError: If data is invalid
        """
        return cls(
            token_address=data["token_address"],
            token_symbol=data["token_symbol"],
            buy_time=datetime.fromisoformat(data["buy_time"]),
            buy_amount_sol=float(data["buy_amount_sol"]),
            signal_msg_id=int(data["signal_msg_id"]),
            status=PositionStatus(data.get("status", "open")),
            sold_percentage=float(data.get("sold_percentage", 0.0)),
            last_multiplier=float(data.get("last_multiplier", 1.0)),
        )
    
    def mark_partial_sell(self, percentage: float, multiplier: float) -> None:
        """
        Mark position as partially sold.
        
        Args:
            percentage: Percentage sold in this transaction
            multiplier: Price multiplier at time of sale
        """
        self.sold_percentage += percentage
        self.last_multiplier = multiplier
        
        if self.sold_percentage >= 100.0:
            self.status = PositionStatus.CLOSED
        else:
            self.status = PositionStatus.PARTIAL_SOLD
    
    def mark_closed(self, multiplier: Optional[float] = None) -> None:
        """
        Mark position as fully closed.
        
        Args:
            multiplier: Final price multiplier (optional)
        """
        self.status = PositionStatus.CLOSED
        self.sold_percentage = 100.0
        if multiplier is not None:
            self.last_multiplier = multiplier


@dataclass(frozen=True, slots=True)
class BuySignal:
    """
    Represents a parsed buy signal from the channel.
    
    Attributes:
        message_id: Telegram message ID
        token_symbol: Token symbol (e.g., "TRUMP")
        token_address: Solana token mint address
        timestamp: When the signal was received
        raw_text: Original message text for DB storage
    """
    
    message_id: int
    token_symbol: str
    token_address: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_text: str = ""
    
    def __post_init__(self) -> None:
        """Validate signal data."""
        if not self.token_address:
            raise ValueError("Token address cannot be empty")
        if len(self.token_address) < 32:
            raise ValueError("Invalid Solana address format")


@dataclass(frozen=True, slots=True)
class ProfitAlert:
    """
    Represents a parsed profit alert from the channel.
    
    Attributes:
        message_id: Telegram message ID of the alert
        reply_to_msg_id: Message ID this alert is replying to
        multiplier: Price multiplier (e.g., 2.0 for 2X)
        timestamp: When the alert was received
    """
    
    message_id: int
    reply_to_msg_id: int
    multiplier: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self) -> None:
        """Validate alert data."""
        if self.multiplier <= 0:
            raise ValueError("Multiplier must be positive")


@dataclass(frozen=True, slots=True)
class TradeResult:
    """
    Result of a trade execution attempt.
    
    Attributes:
        success: Whether the trade was executed successfully
        token_address: Token involved in the trade
        token_symbol: Token symbol
        action: Type of trade ("buy" or "sell")
        amount: Amount traded (SOL for buy, percentage for sell)
        message: Human-readable result message
        timestamp: When the trade was executed
        dry_run: Whether this was a simulated trade
    """
    
    success: bool
    token_address: str
    token_symbol: str
    action: str
    amount: float
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    dry_run: bool = False
    
    @property
    def is_buy(self) -> bool:
        """Check if this was a buy trade."""
        return self.action.lower() == "buy"
    
    @property
    def is_sell(self) -> bool:
        """Check if this was a sell trade."""
        return self.action.lower() == "sell"
