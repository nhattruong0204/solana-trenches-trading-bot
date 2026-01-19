"""
State management for trading positions.

This module handles persistence and retrieval of trading state,
including open positions and signal-to-position mappings.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.constants import DEFAULT_STATE_FILE
from src.exceptions import (
    DuplicatePositionError,
    MaxPositionsReachedError,
    PositionNotFoundError,
    StateCorruptionError,
    StatePersistenceError,
)
from src.models import Position, PositionStatus

logger = logging.getLogger(__name__)


class TradingState:
    """
    Manages trading state including positions and mappings.
    
    This class is responsible for:
    - Tracking all open, partial, and closed positions
    - Mapping signal message IDs to positions
    - Persisting state to disk for recovery
    - Providing thread-safe access to state
    
    Attributes:
        positions: Dictionary of token_address -> Position
        signal_to_token: Dictionary of signal_msg_id -> token_address
    """
    
    def __init__(self, state_file: Optional[Path] = None) -> None:
        """
        Initialize trading state.
        
        Args:
            state_file: Path to state persistence file
        """
        self._state_file = state_file or Path(DEFAULT_STATE_FILE)
        self._positions: dict[str, Position] = {}
        self._signal_to_token: dict[int, str] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
    
    @property
    def positions(self) -> dict[str, Position]:
        """Get all positions (read-only view)."""
        return dict(self._positions)
    
    @property
    def open_positions(self) -> dict[str, Position]:
        """Get only open positions."""
        return {
            addr: pos for addr, pos in self._positions.items()
            if pos.status != PositionStatus.CLOSED
        }
    
    @property
    def open_position_count(self) -> int:
        """Count of non-closed positions."""
        return sum(
            1 for p in self._positions.values()
            if p.status != PositionStatus.CLOSED
        )
    
    @property
    def total_position_count(self) -> int:
        """Total count of all positions (including closed)."""
        return len(self._positions)
    
    def has_position(self, token_address: str) -> bool:
        """Check if a position exists for the given token."""
        return token_address in self._positions
    
    def get_position(self, token_address: str) -> Optional[Position]:
        """
        Get position by token address.
        
        Args:
            token_address: Solana token mint address
            
        Returns:
            Position if found, None otherwise
        """
        return self._positions.get(token_address)
    
    def get_position_by_signal(self, signal_msg_id: int) -> Optional[Position]:
        """
        Get position by the original signal message ID.
        
        Args:
            signal_msg_id: Telegram message ID of the buy signal
            
        Returns:
            Position if found, None otherwise
        """
        token_address = self._signal_to_token.get(signal_msg_id)
        if token_address:
            return self._positions.get(token_address)
        return None
    
    async def add_position(
        self,
        position: Position,
        max_positions: int = 0,
    ) -> None:
        """
        Add a new position.
        
        Args:
            position: Position to add
            max_positions: Maximum allowed open positions (0 = unlimited)
            
        Raises:
            DuplicatePositionError: If position already exists
            MaxPositionsReachedError: If max positions limit reached
        """
        async with self._lock:
            # Check for duplicate
            if position.token_address in self._positions:
                existing = self._positions[position.token_address]
                if existing.status != PositionStatus.CLOSED:
                    raise DuplicatePositionError(
                        position.token_address,
                        position.token_symbol,
                    )
            
            # Check max positions limit
            if max_positions > 0 and self.open_position_count >= max_positions:
                raise MaxPositionsReachedError(
                    max_positions,
                    self.open_position_count,
                )
            
            # Add position
            self._positions[position.token_address] = position
            self._signal_to_token[position.signal_msg_id] = position.token_address
            self._dirty = True
            
            logger.info(
                f"Position added: ${position.token_symbol} "
                f"({position.token_address[:12]}...) - {position.buy_amount_sol} SOL"
            )
    
    async def update_position(self, position: Position) -> None:
        """
        Update an existing position.
        
        Args:
            position: Position with updated values
            
        Raises:
            PositionNotFoundError: If position doesn't exist
        """
        async with self._lock:
            if position.token_address not in self._positions:
                raise PositionNotFoundError(position.token_address)
            
            self._positions[position.token_address] = position
            self._dirty = True
            
            logger.debug(f"Position updated: ${position.token_symbol}")
    
    async def mark_partial_sell(
        self,
        token_address: str,
        percentage: float,
        multiplier: float,
    ) -> Position:
        """
        Mark a position as partially sold.
        
        Args:
            token_address: Token address
            percentage: Percentage sold
            multiplier: Price multiplier at sale
            
        Returns:
            Updated position
            
        Raises:
            PositionNotFoundError: If position doesn't exist
        """
        async with self._lock:
            position = self._positions.get(token_address)
            if not position:
                raise PositionNotFoundError(token_address)
            
            position.mark_partial_sell(percentage, multiplier)
            self._dirty = True
            
            logger.info(
                f"Position partially sold: ${position.token_symbol} "
                f"- {percentage}% at {multiplier}X"
            )
            
            return position
    
    async def close_position(
        self,
        token_address: str,
        multiplier: Optional[float] = None,
    ) -> Position:
        """
        Close a position.
        
        Args:
            token_address: Token address
            multiplier: Final price multiplier
            
        Returns:
            Closed position
            
        Raises:
            PositionNotFoundError: If position doesn't exist
        """
        async with self._lock:
            position = self._positions.get(token_address)
            if not position:
                raise PositionNotFoundError(token_address)
            
            position.mark_closed(multiplier)
            self._dirty = True
            
            logger.info(f"Position closed: ${position.token_symbol}")
            
            return position
    
    def save(self, filepath: Optional[Path] = None) -> None:
        """
        Persist state to file.
        
        Args:
            filepath: Override default state file path
            
        Raises:
            StatePersistenceError: If save fails
        """
        save_path = filepath or self._state_file
        
        try:
            data = {
                "version": 1,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "positions": {
                    addr: pos.to_dict()
                    for addr, pos in self._positions.items()
                },
                "signal_to_token": {
                    str(k): v for k, v in self._signal_to_token.items()
                },
            }
            
            # Write atomically using temp file
            temp_path = save_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_path.replace(save_path)
            self._dirty = False
            
            logger.debug(f"State saved to {save_path}: {len(self._positions)} positions")
            
        except Exception as e:
            raise StatePersistenceError("save", str(save_path), e) from e
    
    def load(self, filepath: Optional[Path] = None) -> bool:
        """
        Load state from file.
        
        Args:
            filepath: Override default state file path
            
        Returns:
            True if state was loaded, False if file doesn't exist
            
        Raises:
            StateCorruptionError: If state file is corrupted
        """
        load_path = filepath or self._state_file
        
        if not load_path.exists():
            logger.info("No existing state file found, starting fresh")
            return False
        
        try:
            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Load positions
            self._positions = {
                addr: Position.from_dict(pos_data)
                for addr, pos_data in data.get("positions", {}).items()
            }
            
            # Load signal mapping (convert string keys back to int)
            self._signal_to_token = {
                int(k): v for k, v in data.get("signal_to_token", {}).items()
            }
            
            self._dirty = False
            
            logger.info(
                f"State loaded from {load_path}: "
                f"{len(self._positions)} positions, "
                f"{self.open_position_count} open"
            )
            return True
            
        except json.JSONDecodeError as e:
            raise StateCorruptionError(str(load_path), e) from e
        except KeyError as e:
            raise StateCorruptionError(str(load_path), e) from e
        except Exception as e:
            raise StatePersistenceError("load", str(load_path), e) from e
    
    async def auto_save(self) -> None:
        """Save state if there are unsaved changes."""
        if self._dirty:
            self.save()
    
    def get_statistics(self) -> dict[str, Any]:
        """
        Get trading statistics.
        
        Returns:
            Dictionary with statistics
        """
        open_positions = [p for p in self._positions.values() if p.is_open]
        partial_positions = [p for p in self._positions.values() if p.is_partially_sold]
        closed_positions = [p for p in self._positions.values() if p.is_closed]
        
        total_invested = sum(p.buy_amount_sol for p in self._positions.values())
        estimated_value = sum(p.estimated_value_sol for p in self._positions.values())
        
        return {
            "total_positions": len(self._positions),
            "open_positions": len(open_positions),
            "partial_positions": len(partial_positions),
            "closed_positions": len(closed_positions),
            "total_invested_sol": round(total_invested, 4),
            "estimated_value_sol": round(estimated_value, 4),
            "estimated_pnl_sol": round(estimated_value - total_invested, 4),
        }
    
    def __repr__(self) -> str:
        return (
            f"TradingState(positions={len(self._positions)}, "
            f"open={self.open_position_count})"
        )
