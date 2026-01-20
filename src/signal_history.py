"""
Signal history tracking for PnL calculations.

This module tracks all signals from the channel with their entry prices
to calculate historical PnL for different time periods.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SIGNAL_HISTORY_FILE = "signal_history.json"

# DexScreener API for price data
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens/{}"


@dataclass
class SignalRecord:
    """
    Record of a signal from the channel.
    
    Attributes:
        token_address: Solana token mint address
        token_symbol: Token symbol
        entry_price_sol: Price at signal time (in SOL)
        entry_price_usd: Price at signal time (in USD)
        signal_time: When the signal was received
        message_id: Telegram message ID
        current_price_sol: Latest fetched price (updated on demand)
        current_price_usd: Latest fetched price in USD
        last_price_update: When price was last updated
    """
    
    token_address: str
    token_symbol: str
    entry_price_sol: float
    entry_price_usd: float
    signal_time: datetime
    message_id: int
    current_price_sol: Optional[float] = None
    current_price_usd: Optional[float] = None
    last_price_update: Optional[datetime] = None
    
    @property
    def multiplier(self) -> Optional[float]:
        """Calculate current multiplier from entry."""
        if self.current_price_sol and self.entry_price_sol > 0:
            return self.current_price_sol / self.entry_price_sol
        return None
    
    @property
    def pnl_percent(self) -> Optional[float]:
        """Calculate PnL percentage."""
        mult = self.multiplier
        if mult is not None:
            return (mult - 1) * 100
        return None
    
    @property
    def age_hours(self) -> float:
        """Get signal age in hours."""
        delta = datetime.now(timezone.utc) - self.signal_time
        return delta.total_seconds() / 3600
    
    @property
    def age_days(self) -> float:
        """Get signal age in days."""
        return self.age_hours / 24
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "entry_price_sol": self.entry_price_sol,
            "entry_price_usd": self.entry_price_usd,
            "signal_time": self.signal_time.isoformat(),
            "message_id": self.message_id,
            "current_price_sol": self.current_price_sol,
            "current_price_usd": self.current_price_usd,
            "last_price_update": self.last_price_update.isoformat() if self.last_price_update else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalRecord":
        """Deserialize from dictionary."""
        return cls(
            token_address=data["token_address"],
            token_symbol=data["token_symbol"],
            entry_price_sol=float(data["entry_price_sol"]),
            entry_price_usd=float(data["entry_price_usd"]),
            signal_time=datetime.fromisoformat(data["signal_time"]),
            message_id=int(data["message_id"]),
            current_price_sol=float(data["current_price_sol"]) if data.get("current_price_sol") else None,
            current_price_usd=float(data["current_price_usd"]) if data.get("current_price_usd") else None,
            last_price_update=datetime.fromisoformat(data["last_price_update"]) if data.get("last_price_update") else None,
        )


class SignalHistory:
    """
    Manages signal history for PnL tracking.
    
    Tracks all signals from the channel and provides:
    - Signal recording with entry prices
    - Price updates from DexScreener
    - PnL calculations for different time periods
    """
    
    def __init__(self, history_file: Optional[Path] = None) -> None:
        """Initialize signal history."""
        self._history_file = history_file or Path(DEFAULT_SIGNAL_HISTORY_FILE)
        self._signals: dict[str, SignalRecord] = {}  # token_address -> SignalRecord
        self._lock = asyncio.Lock()
        self._http_client: Optional[httpx.AsyncClient] = None
    
    @property
    def signals(self) -> dict[str, SignalRecord]:
        """Get all signals."""
        return dict(self._signals)
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def fetch_token_price(self, token_address: str) -> tuple[Optional[float], Optional[float]]:
        """
        Fetch current token price from DexScreener.
        
        Args:
            token_address: Solana token mint address
            
        Returns:
            Tuple of (price_in_sol, price_in_usd) or (None, None) if failed
        """
        try:
            client = await self._get_http_client()
            url = DEXSCREENER_API.format(token_address)
            
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                logger.debug(f"No pairs found for {token_address[:12]}...")
                return None, None
            
            # Find SOL pair (preferably Raydium or highest liquidity)
            sol_pair = None
            for pair in pairs:
                if pair.get("quoteToken", {}).get("symbol") == "SOL":
                    if not sol_pair or pair.get("liquidity", {}).get("usd", 0) > sol_pair.get("liquidity", {}).get("usd", 0):
                        sol_pair = pair
            
            if sol_pair:
                price_sol = float(sol_pair.get("priceNative", 0))
                price_usd = float(sol_pair.get("priceUsd", 0))
                return price_sol, price_usd
            
            # Fallback to first pair and convert
            first_pair = pairs[0]
            price_usd = float(first_pair.get("priceUsd", 0))
            # Approximate SOL price (assume ~$200 SOL)
            price_sol = price_usd / 200 if price_usd else None
            return price_sol, price_usd
            
        except Exception as e:
            logger.debug(f"Failed to fetch price for {token_address[:12]}...: {e}")
            return None, None
    
    async def add_signal(
        self,
        token_address: str,
        token_symbol: str,
        message_id: int,
    ) -> Optional[SignalRecord]:
        """
        Add a new signal and fetch its entry price.
        
        Args:
            token_address: Solana token mint address
            token_symbol: Token symbol
            message_id: Telegram message ID
            
        Returns:
            SignalRecord if successful, None if price fetch failed
        """
        async with self._lock:
            # Skip if already tracked (avoid duplicates)
            if token_address in self._signals:
                logger.debug(f"Signal already tracked: ${token_symbol}")
                return self._signals[token_address]
            
            # Fetch entry price
            price_sol, price_usd = await self.fetch_token_price(token_address)
            
            if price_sol is None:
                logger.warning(f"Could not fetch entry price for ${token_symbol}")
                # Still record with 0 price
                price_sol = 0.0
                price_usd = 0.0
            
            record = SignalRecord(
                token_address=token_address,
                token_symbol=token_symbol,
                entry_price_sol=price_sol,
                entry_price_usd=price_usd,
                signal_time=datetime.now(timezone.utc),
                message_id=message_id,
                current_price_sol=price_sol,
                current_price_usd=price_usd,
                last_price_update=datetime.now(timezone.utc),
            )
            
            self._signals[token_address] = record
            self.save()
            
            logger.info(f"Signal recorded: ${token_symbol} @ {price_sol:.10f} SOL")
            return record
    
    async def update_prices(self, token_addresses: Optional[list[str]] = None) -> int:
        """
        Update current prices for signals.
        
        Args:
            token_addresses: Specific addresses to update, or None for all
            
        Returns:
            Number of prices successfully updated
        """
        addresses = token_addresses or list(self._signals.keys())
        updated = 0
        
        for addr in addresses:
            if addr not in self._signals:
                continue
            
            price_sol, price_usd = await self.fetch_token_price(addr)
            
            if price_sol is not None:
                async with self._lock:
                    self._signals[addr].current_price_sol = price_sol
                    self._signals[addr].current_price_usd = price_usd
                    self._signals[addr].last_price_update = datetime.now(timezone.utc)
                    updated += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.2)
        
        if updated > 0:
            self.save()
        
        return updated
    
    def get_signals_in_period(
        self,
        days: Optional[int] = None,
    ) -> list[SignalRecord]:
        """
        Get signals within a time period.
        
        Args:
            days: Number of days to look back, None for all time
            
        Returns:
            List of SignalRecords within the period
        """
        now = datetime.now(timezone.utc)
        
        if days is None:
            return list(self._signals.values())
        
        cutoff = now - timedelta(days=days)
        return [
            s for s in self._signals.values()
            if s.signal_time >= cutoff
        ]
    
    def calculate_pnl_stats(
        self,
        signals: list[SignalRecord],
    ) -> dict[str, Any]:
        """
        Calculate PnL statistics for a list of signals.
        
        Args:
            signals: List of signals to analyze
            
        Returns:
            Dictionary with PnL statistics
        """
        if not signals:
            return {
                "total_signals": 0,
                "winners": 0,
                "losers": 0,
                "win_rate": 0.0,
                "avg_multiplier": 0.0,
                "best_multiplier": 0.0,
                "worst_multiplier": 0.0,
                "total_pnl_percent": 0.0,
            }
        
        multipliers = []
        winners = 0
        losers = 0
        
        for s in signals:
            mult = s.multiplier
            if mult is not None and mult > 0:
                multipliers.append(mult)
                if mult >= 1.0:
                    winners += 1
                else:
                    losers += 1
        
        if not multipliers:
            return {
                "total_signals": len(signals),
                "winners": 0,
                "losers": 0,
                "win_rate": 0.0,
                "avg_multiplier": 0.0,
                "best_multiplier": 0.0,
                "worst_multiplier": 0.0,
                "total_pnl_percent": 0.0,
                "signals_with_price": 0,
            }
        
        avg_mult = sum(multipliers) / len(multipliers)
        best_mult = max(multipliers)
        worst_mult = min(multipliers)
        
        # Calculate total PnL as if equal weight invested
        total_pnl = sum((m - 1) for m in multipliers) / len(multipliers) * 100
        
        return {
            "total_signals": len(signals),
            "signals_with_price": len(multipliers),
            "winners": winners,
            "losers": losers,
            "win_rate": winners / len(multipliers) * 100 if multipliers else 0,
            "avg_multiplier": avg_mult,
            "best_multiplier": best_mult,
            "worst_multiplier": worst_mult,
            "total_pnl_percent": total_pnl,
        }
    
    def get_top_performers(
        self,
        signals: list[SignalRecord],
        n: int = 5,
    ) -> list[SignalRecord]:
        """Get top N performing signals."""
        with_mult = [(s, s.multiplier) for s in signals if s.multiplier is not None]
        with_mult.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in with_mult[:n]]
    
    def get_worst_performers(
        self,
        signals: list[SignalRecord],
        n: int = 5,
    ) -> list[SignalRecord]:
        """Get worst N performing signals."""
        with_mult = [(s, s.multiplier) for s in signals if s.multiplier is not None]
        with_mult.sort(key=lambda x: x[1])
        return [s for s, _ in with_mult[:n]]
    
    def save(self, filepath: Optional[Path] = None) -> None:
        """Save signal history to file."""
        save_path = filepath or self._history_file
        
        try:
            data = {
                "signals": {
                    addr: record.to_dict()
                    for addr, record in self._signals.items()
                },
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save signal history: {e}")
    
    def load(self, filepath: Optional[Path] = None) -> bool:
        """Load signal history from file."""
        load_path = filepath or self._history_file
        
        if not load_path.exists():
            logger.debug(f"No signal history file at {load_path}")
            return False
        
        try:
            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._signals = {
                addr: SignalRecord.from_dict(record_data)
                for addr, record_data in data.get("signals", {}).items()
            }
            
            logger.info(f"Loaded {len(self._signals)} signals from history")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load signal history: {e}")
            return False
