"""
Price History Module - Fetches OHLCV data for accurate backtesting.

Uses GeckoTerminal API (free, no API key required).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# GeckoTerminal API base
GECKO_TERMINAL_API = "https://api.geckoterminal.com/api/v2"

# Rate limit: 30 requests per minute for free tier
RATE_LIMIT_DELAY = 2.5  # seconds between requests


@dataclass
class Candle:
    """Single OHLCV candle."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def timestamp_unix(self) -> int:
        return int(self.timestamp.timestamp())


@dataclass
class PriceHistory:
    """Price history for a token."""
    token_address: str
    pool_address: Optional[str] = None
    candles: list[Candle] = field(default_factory=list)
    timeframe_minutes: int = 15  # 15-minute candles
    
    @property
    def start_time(self) -> Optional[datetime]:
        if not self.candles:
            return None
        return min(c.timestamp for c in self.candles)
    
    @property
    def end_time(self) -> Optional[datetime]:
        if not self.candles:
            return None
        return max(c.timestamp for c in self.candles)
    
    def get_candles_after(self, after: datetime) -> list[Candle]:
        """Get candles after a specific timestamp."""
        return [c for c in self.candles if c.timestamp >= after]
    
    def get_price_at(self, timestamp: datetime) -> Optional[float]:
        """Get the close price at or just before a timestamp."""
        valid = [c for c in self.candles if c.timestamp <= timestamp]
        if not valid:
            return None
        return max(valid, key=lambda c: c.timestamp).close
    
    def get_high_after(self, timestamp: datetime) -> Optional[float]:
        """Get the highest price after a timestamp."""
        valid = [c for c in self.candles if c.timestamp >= timestamp]
        if not valid:
            return None
        return max(c.high for c in valid)
    
    def simulate_trailing_stop(
        self, 
        entry_time: datetime,
        entry_price: float,
        trailing_pct: float = 0.20,
        max_hold_hours: int = 72
    ) -> tuple[Optional[float], str, Optional[datetime]]:
        """
        Simulate a trailing stop from entry_time.
        
        Args:
            entry_time: When we entered the position
            entry_price: Entry price (usually at signal)
            trailing_pct: Trailing stop percentage (0.20 = 20%)
            max_hold_hours: Maximum hours to hold before forced exit
            
        Returns:
            (exit_multiplier, exit_reason, exit_time)
            - exit_multiplier: Final price / entry_price
            - exit_reason: "trailing_stop", "time_exit", "still_open"
            - exit_time: When we exited
        """
        candles = self.get_candles_after(entry_time)
        if not candles:
            return None, "no_data", None
        
        # Sort by timestamp
        candles = sorted(candles, key=lambda c: c.timestamp)
        
        peak_price = entry_price
        stop_price = entry_price * (1 - trailing_pct)
        max_hold_time = entry_time + timedelta(hours=max_hold_hours)
        
        for candle in candles:
            # Check time limit
            if candle.timestamp > max_hold_time:
                return candle.close / entry_price, "time_exit", candle.timestamp
            
            # Update peak and trailing stop
            if candle.high > peak_price:
                peak_price = candle.high
                stop_price = peak_price * (1 - trailing_pct)
            
            # Check if stop triggered (using low)
            if candle.low <= stop_price:
                # Exit at stop price
                exit_price = stop_price
                exit_mult = exit_price / entry_price
                return exit_mult, "trailing_stop", candle.timestamp
        
        # Still holding
        last_candle = candles[-1]
        return last_candle.close / entry_price, "still_open", last_candle.timestamp
    
    def simulate_fixed_exit(
        self,
        entry_time: datetime,
        entry_price: float,
        target_mult: float = 2.0,
        stop_loss_mult: float = 0.5,
        max_hold_hours: int = 72
    ) -> tuple[Optional[float], str, Optional[datetime]]:
        """
        Simulate a fixed take profit / stop loss exit.
        
        Returns:
            (exit_multiplier, exit_reason, exit_time)
        """
        candles = self.get_candles_after(entry_time)
        if not candles:
            return None, "no_data", None
        
        candles = sorted(candles, key=lambda c: c.timestamp)
        
        target_price = entry_price * target_mult
        stop_price = entry_price * stop_loss_mult
        max_hold_time = entry_time + timedelta(hours=max_hold_hours)
        
        for candle in candles:
            # Check time limit
            if candle.timestamp > max_hold_time:
                return candle.close / entry_price, "time_exit", candle.timestamp
            
            # Check stop loss first (pessimistic)
            if candle.low <= stop_price:
                return stop_loss_mult, "stop_loss", candle.timestamp
            
            # Check target
            if candle.high >= target_price:
                return target_mult, "target_hit", candle.timestamp
        
        # Still holding
        last_candle = candles[-1]
        return last_candle.close / entry_price, "still_open", last_candle.timestamp
    
    def simulate_tiered_exit(
        self,
        entry_time: datetime,
        entry_price: float,
        tiers: list[tuple[float, float]],  # [(multiplier, sell_pct), ...]
        trailing_pct: float = 0.25,
        max_hold_hours: int = 72
    ) -> tuple[float, str, list[tuple[float, float, datetime]]]:
        """
        Simulate tiered exit with optional trailing on remainder.
        
        Args:
            entry_time: Entry timestamp
            entry_price: Entry price
            tiers: List of (multiplier, sell_percentage) e.g. [(2.0, 0.5), (3.0, 0.5)]
            trailing_pct: Trailing stop on remaining after tiers
            max_hold_hours: Max hold time
            
        Returns:
            (weighted_exit_mult, exit_reason, exits_list)
            exits_list: [(mult, portion, time), ...]
        """
        candles = self.get_candles_after(entry_time)
        if not candles:
            return 1.0, "no_data", []
        
        candles = sorted(candles, key=lambda c: c.timestamp)
        max_hold_time = entry_time + timedelta(hours=max_hold_hours)
        
        remaining_pct = 1.0
        exits: list[tuple[float, float, datetime]] = []
        tiers_remaining = list(tiers)
        
        peak_price = entry_price
        
        for candle in candles:
            if candle.timestamp > max_hold_time:
                # Time exit remaining
                if remaining_pct > 0:
                    exits.append((candle.close / entry_price, remaining_pct, candle.timestamp))
                break
            
            # Check tiers
            for tier_mult, tier_pct in tiers_remaining[:]:
                target_price = entry_price * tier_mult
                if candle.high >= target_price:
                    sell_pct = min(tier_pct, remaining_pct)
                    exits.append((tier_mult, sell_pct, candle.timestamp))
                    remaining_pct -= sell_pct
                    tiers_remaining.remove((tier_mult, tier_pct))
            
            # Update peak for trailing
            if candle.high > peak_price:
                peak_price = candle.high
            
            # Check trailing stop on remaining
            if remaining_pct > 0 and not tiers_remaining:
                stop_price = peak_price * (1 - trailing_pct)
                if candle.low <= stop_price:
                    exits.append((stop_price / entry_price, remaining_pct, candle.timestamp))
                    remaining_pct = 0
                    break
        
        # If still holding
        if remaining_pct > 0 and candles:
            last_candle = candles[-1]
            exits.append((last_candle.close / entry_price, remaining_pct, last_candle.timestamp))
        
        # Calculate weighted average exit
        if not exits:
            return 1.0, "no_data", []
        
        weighted_mult = sum(mult * pct for mult, pct, _ in exits)
        
        # Determine primary exit reason
        if any("trailing" in str(e) for e in exits):
            reason = "trailing_stop"
        elif len(exits) == len(tiers) + 1:
            reason = "all_tiers_hit"
        else:
            reason = "partial_exit"
        
        return weighted_mult, reason, exits


class PriceHistoryFetcher:
    """Fetches price history from GeckoTerminal."""
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._pool_cache: dict[str, str] = {}  # token_address -> pool_address
        self._last_request_time: float = 0
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Accept": "application/json"}
            )
        return self._client
    
    async def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()
    
    async def get_pool_address(self, token_address: str) -> Optional[str]:
        """Get the main pool address for a token."""
        if token_address in self._pool_cache:
            return self._pool_cache[token_address]
        
        await self._rate_limit()
        client = await self._get_client()
        
        try:
            url = f"{GECKO_TERMINAL_API}/networks/solana/tokens/{token_address}/pools"
            response = await client.get(url)
            
            if response.status_code != 200:
                logger.warning(f"Failed to get pools for {token_address}: {response.status_code}")
                return None
            
            data = response.json()
            pools = data.get("data", [])
            
            if not pools:
                return None
            
            # Get the pool with highest liquidity
            best_pool = None
            best_liquidity = 0
            
            for pool in pools:
                attrs = pool.get("attributes", {})
                reserve = attrs.get("reserve_in_usd")
                if reserve:
                    try:
                        liquidity = float(reserve)
                        if liquidity > best_liquidity:
                            best_liquidity = liquidity
                            best_pool = attrs.get("address")
                    except (ValueError, TypeError):
                        pass
            
            # If no liquidity data, just take the first
            if not best_pool and pools:
                best_pool = pools[0].get("attributes", {}).get("address")
            
            if best_pool:
                self._pool_cache[token_address] = best_pool
            
            return best_pool
            
        except Exception as e:
            logger.error(f"Error getting pool for {token_address}: {e}")
            return None
    
    async def fetch_ohlcv(
        self,
        token_address: str,
        pool_address: Optional[str] = None,
        timeframe_minutes: int = 15,
        limit: int = 1000
    ) -> Optional[PriceHistory]:
        """
        Fetch OHLCV data for a token.
        
        Args:
            token_address: Token mint address
            pool_address: Pool address (will be fetched if not provided)
            timeframe_minutes: Candle timeframe (1, 5, 15 supported)
            limit: Max number of candles
            
        Returns:
            PriceHistory object or None if failed
        """
        if not pool_address:
            pool_address = await self.get_pool_address(token_address)
            if not pool_address:
                logger.warning(f"No pool found for {token_address}")
                return None
        
        await self._rate_limit()
        client = await self._get_client()
        
        try:
            # GeckoTerminal uses aggregate parameter for timeframe
            # minute endpoints: aggregate=1, 5, 15
            url = f"{GECKO_TERMINAL_API}/networks/solana/pools/{pool_address}/ohlcv/minute"
            params = {
                "aggregate": timeframe_minutes,
                "limit": limit
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.warning(f"OHLCV fetch failed for {pool_address}: {response.status_code}")
                return None
            
            data = response.json()
            ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            
            if not ohlcv_list:
                return None
            
            # Parse candles: [timestamp, open, high, low, close, volume]
            candles = []
            for item in ohlcv_list:
                if len(item) >= 6:
                    try:
                        candle = Candle(
                            timestamp=datetime.fromtimestamp(item[0]),
                            open=float(item[1]),
                            high=float(item[2]),
                            low=float(item[3]),
                            close=float(item[4]),
                            volume=float(item[5])
                        )
                        candles.append(candle)
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Failed to parse candle: {e}")
            
            return PriceHistory(
                token_address=token_address,
                pool_address=pool_address,
                candles=candles,
                timeframe_minutes=timeframe_minutes
            )
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {pool_address}: {e}")
            return None
    
    async def fetch_multiple(
        self,
        token_addresses: list[str],
        timeframe_minutes: int = 15,
        limit: int = 1000,
        progress_callback=None
    ) -> dict[str, PriceHistory]:
        """
        Fetch price history for multiple tokens.
        
        Args:
            token_addresses: List of token addresses
            timeframe_minutes: Candle timeframe
            limit: Max candles per token
            progress_callback: async callback(current, total)
            
        Returns:
            Dict mapping token_address -> PriceHistory
        """
        results = {}
        total = len(token_addresses)
        
        for i, address in enumerate(token_addresses):
            try:
                history = await self.fetch_ohlcv(
                    address, 
                    timeframe_minutes=timeframe_minutes,
                    limit=limit
                )
                if history:
                    results[address] = history
                    logger.debug(f"Fetched {len(history.candles)} candles for {address}")
                else:
                    logger.debug(f"No data for {address}")
            except Exception as e:
                logger.error(f"Failed to fetch {address}: {e}")
            
            if progress_callback:
                await progress_callback(i + 1, total)
        
        return results
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_fetcher: Optional[PriceHistoryFetcher] = None


def get_price_fetcher() -> PriceHistoryFetcher:
    """Get or create the price history fetcher."""
    global _fetcher
    if _fetcher is None:
        _fetcher = PriceHistoryFetcher()
    return _fetcher
