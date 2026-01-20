"""
Signal Database Integration for PnL calculations.

This module integrates with the wallet_tracker PostgreSQL database
to query historical signal data from "From The Trenches - VOLUME + SM" channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class TokenSignal:
    """Represents a token signal from the channel."""
    
    db_id: int
    telegram_msg_id: int
    timestamp: datetime
    token_symbol: str
    token_address: str
    initial_fdv: Optional[float] = None
    
    @property
    def age_hours(self) -> float:
        """Get signal age in hours."""
        now = datetime.now(timezone.utc)
        if self.timestamp.tzinfo is None:
            ts = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            ts = self.timestamp
        delta = now - ts
        return delta.total_seconds() / 3600
    
    @property
    def age_days(self) -> float:
        """Get signal age in days."""
        return self.age_hours / 24


@dataclass
class ProfitAlert:
    """Represents a profit alert for a signal."""
    
    db_id: int
    telegram_msg_id: int
    reply_to_msg_id: int
    timestamp: datetime
    multiplier: float
    initial_fdv: Optional[float] = None
    current_fdv: Optional[float] = None


@dataclass
class SignalWithPnL:
    """Signal combined with its PnL data from profit alerts."""
    
    signal: TokenSignal
    profit_alerts: list[ProfitAlert] = field(default_factory=list)
    
    @property
    def has_profit(self) -> bool:
        return len(self.profit_alerts) > 0
    
    @property
    def max_multiplier(self) -> float:
        """Maximum multiplier achieved."""
        if not self.profit_alerts:
            return 0.0
        return max(a.multiplier for a in self.profit_alerts)
    
    @property
    def reached_2x(self) -> bool:
        """Check if signal reached 2X."""
        return self.max_multiplier >= 2.0
    
    @property
    def pnl_percent(self) -> float:
        """PnL percentage (assuming HODL to max)."""
        if not self.has_profit:
            return -100.0  # Total loss
        return (self.max_multiplier - 1) * 100
    
    @property
    def latest_multiplier(self) -> Optional[float]:
        """Get most recent multiplier."""
        if not self.profit_alerts:
            return None
        sorted_alerts = sorted(self.profit_alerts, key=lambda a: a.timestamp, reverse=True)
        return sorted_alerts[0].multiplier


@dataclass
class PnLStats:
    """PnL statistics for a period."""
    
    total_signals: int = 0
    signals_with_profit: int = 0
    signals_reached_2x: int = 0
    losing_signals: int = 0
    win_rate: float = 0.0
    win_rate_2x: float = 0.0
    avg_multiplier: float = 0.0
    best_multiplier: float = 0.0
    worst_multiplier: float = 0.0
    total_pnl_percent: float = 0.0
    period_label: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    top_performers: list[SignalWithPnL] = field(default_factory=list)
    worst_performers: list[SignalWithPnL] = field(default_factory=list)


def parse_signal_message(raw_text: str) -> tuple[Optional[str], Optional[str], Optional[float]]:
    """
    Parse a signal message to extract token info.
    
    Returns: (symbol, address, fdv)
    """
    symbol = None
    address = None
    fdv = None
    
    # Extract token symbol: Token: - $SYMBOL or Token: $SYMBOL
    symbol_match = re.search(r'Token:\s*-?\s*\$(\w+)', raw_text)
    if symbol_match:
        symbol = symbol_match.group(1)
    
    # Extract token address (Solana base58 - typically 32-44 chars)
    address_match = re.search(r'[`├└]\s*([1-9A-HJ-NP-Za-km-z]{32,44})', raw_text)
    if address_match:
        address = address_match.group(1)
    
    # Extract FDV: FDV: $XXK or $XX.XK or $XXXK
    fdv_match = re.search(r'FDV[`:\s]*\$?([\d.]+)\s*K', raw_text, re.IGNORECASE)
    if fdv_match:
        try:
            fdv = float(fdv_match.group(1)) * 1000
        except ValueError:
            pass
    
    return symbol, address, fdv


def parse_profit_alert(raw_text: str) -> Optional[float]:
    """
    Parse a profit alert message to extract multiplier.
    
    Returns: multiplier (e.g., 6.0 for 6X)
    """
    # Match patterns like: **2X**, **3X**, **6X**, **10X**, **1.5X**
    multiplier_match = re.search(r'\*\*?([\d.]+)\s*X\*?\*?', raw_text, re.IGNORECASE)
    if multiplier_match:
        try:
            return float(multiplier_match.group(1))
        except ValueError:
            pass
    
    # Alternative pattern without markdown
    multiplier_match2 = re.search(r'Multiplier[:\s`]*([\d.]+)\s*X', raw_text, re.IGNORECASE)
    if multiplier_match2:
        try:
            return float(multiplier_match2.group(1))
        except ValueError:
            pass
    
    return None


def parse_fdv_from_profit_alert(raw_text: str) -> tuple[Optional[float], Optional[float]]:
    """Extract initial and current FDV from profit alert."""
    initial_fdv = None
    current_fdv = None
    
    # Initial FDV
    initial_match = re.search(r'Initial FDV[:\s`]*\*?\*?\$?([\d.]+)\s*([KMB])?', raw_text, re.IGNORECASE)
    if initial_match:
        try:
            val = float(initial_match.group(1))
            suffix = initial_match.group(2)
            if suffix:
                suffix = suffix.upper()
                if suffix == 'K':
                    val *= 1_000
                elif suffix == 'M':
                    val *= 1_000_000
                elif suffix == 'B':
                    val *= 1_000_000_000
            initial_fdv = val
        except ValueError:
            pass
    
    # Current FDV
    current_match = re.search(r'Current FDV[:\s`]*\*?\*?\$?([\d.]+)\s*([KMB])?', raw_text, re.IGNORECASE)
    if current_match:
        try:
            val = float(current_match.group(1))
            suffix = current_match.group(2)
            if suffix:
                suffix = suffix.upper()
                if suffix == 'K':
                    val *= 1_000
                elif suffix == 'M':
                    val *= 1_000_000
                elif suffix == 'B':
                    val *= 1_000_000_000
            current_fdv = val
        except ValueError:
            pass
    
    return initial_fdv, current_fdv


class SignalDatabase:
    """
    Database interface for querying signal PnL data.
    
    Connects to the wallet_tracker PostgreSQL database to query
    historical signals and profit alerts from "From The Trenches" channel.
    """
    
    CHANNEL_NAME = "From The Trenches - VOLUME + SM"
    
    def __init__(self, dsn: str) -> None:
        """
        Initialize database connection.
        
        Args:
            dsn: PostgreSQL connection string
        """
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> bool:
        """Establish connection pool."""
        if self._pool is not None:
            return True
        
        try:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=1,
                max_size=5,
            )
            logger.info("Connected to signal database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to signal database: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def get_signals_in_period(
        self,
        days: Optional[int] = None,
    ) -> list[SignalWithPnL]:
        """
        Get all signals with their PnL data for a time period.
        
        Args:
            days: Number of days to look back, None for all time
            
        Returns:
            List of SignalWithPnL objects
        """
        if not self._pool:
            logger.error("Database not connected")
            return []
        
        try:
            async with self._pool.acquire() as conn:
                # Build date filter
                date_filter = ""
                if days is not None:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                    date_filter = f"AND message_timestamp >= '{cutoff.isoformat()}'"
                
                # Get signals
                signals_query = f'''
                    SELECT id, telegram_message_id, raw_text, message_timestamp
                    FROM raw_telegram_messages
                    WHERE chat_title = $1
                    AND raw_text LIKE '%APE SIGNAL DETECTED%'
                    {date_filter}
                    ORDER BY message_timestamp DESC
                '''
                
                signals = await conn.fetch(signals_query, self.CHANNEL_NAME)
                
                if not signals:
                    return []
                
                # Build signal map
                signal_map: dict[int, TokenSignal] = {}
                for s in signals:
                    symbol, address, fdv = parse_signal_message(s['raw_text'])
                    if not address:
                        continue
                    
                    signal = TokenSignal(
                        db_id=s['id'],
                        telegram_msg_id=s['telegram_message_id'],
                        timestamp=s['message_timestamp'],
                        token_symbol=symbol or "UNKNOWN",
                        token_address=address,
                        initial_fdv=fdv,
                    )
                    signal_map[s['telegram_message_id']] = signal
                
                # Get profit alerts
                alerts_query = '''
                    SELECT id, telegram_message_id, raw_text, message_timestamp, raw_json
                    FROM raw_telegram_messages
                    WHERE chat_title = $1
                    AND raw_text LIKE '%PROFIT ALERT%'
                '''
                
                alerts = await conn.fetch(alerts_query, self.CHANNEL_NAME)
                
                # Build profit map
                profit_map: dict[int, list[ProfitAlert]] = {}
                for a in alerts:
                    try:
                        json_data = json.loads(a['raw_json']) if a['raw_json'] else {}
                    except json.JSONDecodeError:
                        continue
                    
                    reply_to = json_data.get('reply_to_msg_id')
                    if not reply_to:
                        continue
                    
                    multiplier = parse_profit_alert(a['raw_text'])
                    if not multiplier:
                        continue
                    
                    initial_fdv, current_fdv = parse_fdv_from_profit_alert(a['raw_text'])
                    
                    alert = ProfitAlert(
                        db_id=a['id'],
                        telegram_msg_id=a['telegram_message_id'],
                        reply_to_msg_id=reply_to,
                        timestamp=a['message_timestamp'],
                        multiplier=multiplier,
                        initial_fdv=initial_fdv,
                        current_fdv=current_fdv,
                    )
                    
                    if reply_to not in profit_map:
                        profit_map[reply_to] = []
                    profit_map[reply_to].append(alert)
                
                # Combine signals with profits
                results = []
                for tg_msg_id, signal in signal_map.items():
                    alerts = profit_map.get(tg_msg_id, [])
                    results.append(SignalWithPnL(signal=signal, profit_alerts=alerts))
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to query signals: {e}")
            return []
    
    async def calculate_pnl_stats(
        self,
        days: Optional[int] = None,
    ) -> PnLStats:
        """
        Calculate PnL statistics for a period.
        
        Args:
            days: Number of days to look back, None for all time
            
        Returns:
            PnLStats object with statistics
        """
        signals = await self.get_signals_in_period(days)
        
        period_label = f"Last {days} Day{'s' if days != 1 else ''}" if days else "All Time"
        
        if not signals:
            return PnLStats(period_label=period_label)
        
        # Calculate stats
        total = len(signals)
        with_profit = [s for s in signals if s.has_profit]
        reached_2x = [s for s in signals if s.reached_2x]
        losers = [s for s in signals if not s.has_profit]
        
        multipliers = [s.max_multiplier for s in with_profit if s.max_multiplier > 0]
        
        win_rate = (len(with_profit) / total * 100) if total > 0 else 0
        win_rate_2x = (len(reached_2x) / total * 100) if total > 0 else 0
        avg_mult = sum(multipliers) / len(multipliers) if multipliers else 0
        best_mult = max(multipliers) if multipliers else 0
        worst_mult = min(multipliers) if multipliers else 0
        
        # Calculate total PnL
        # Winners: (multiplier - 1) * 100%
        # Losers: -100%
        total_pnl = sum(s.pnl_percent for s in signals) / total if total > 0 else 0
        
        # Get top and worst performers
        sorted_by_mult = sorted(with_profit, key=lambda s: s.max_multiplier, reverse=True)
        top_performers = sorted_by_mult[:5]
        
        sorted_by_mult_asc = sorted(with_profit, key=lambda s: s.max_multiplier)
        worst_performers = sorted_by_mult_asc[:5]
        
        # Date range
        timestamps = [s.signal.timestamp for s in signals]
        start_date = min(timestamps) if timestamps else None
        end_date = max(timestamps) if timestamps else None
        
        return PnLStats(
            total_signals=total,
            signals_with_profit=len(with_profit),
            signals_reached_2x=len(reached_2x),
            losing_signals=len(losers),
            win_rate=win_rate,
            win_rate_2x=win_rate_2x,
            avg_multiplier=avg_mult,
            best_multiplier=best_mult,
            worst_multiplier=worst_mult,
            total_pnl_percent=total_pnl,
            period_label=period_label,
            start_date=start_date,
            end_date=end_date,
            top_performers=top_performers,
            worst_performers=worst_performers,
        )
    
    async def get_signal_count(self) -> dict[str, int]:
        """Get basic signal counts from database."""
        if not self._pool:
            return {"total": 0, "with_profit": 0}
        
        try:
            async with self._pool.acquire() as conn:
                total = await conn.fetchval('''
                    SELECT COUNT(*) FROM raw_telegram_messages
                    WHERE chat_title = $1
                    AND raw_text LIKE '%APE SIGNAL DETECTED%'
                ''', self.CHANNEL_NAME)
                
                alerts = await conn.fetchval('''
                    SELECT COUNT(*) FROM raw_telegram_messages
                    WHERE chat_title = $1
                    AND raw_text LIKE '%PROFIT ALERT%'
                ''', self.CHANNEL_NAME)
                
                return {
                    "total_signals": total or 0,
                    "total_profit_alerts": alerts or 0,
                }
        except Exception as e:
            logger.error(f"Failed to get signal count: {e}")
            return {"total_signals": 0, "total_profit_alerts": 0}
    
    async def get_latest_message_id(self) -> Optional[int]:
        """Get the latest telegram message ID in the database for this channel."""
        if not self._pool:
            return None
        
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchval('''
                    SELECT MAX(telegram_message_id) FROM raw_telegram_messages
                    WHERE chat_title = $1
                ''', self.CHANNEL_NAME)
                return result
        except Exception as e:
            logger.error(f"Failed to get latest message ID: {e}")
            return None
    
    async def insert_signal(
        self,
        message_id: int,
        token_symbol: str,
        token_address: str,
        signal_time: datetime,
        raw_text: str,
    ) -> bool:
        """
        Insert a new signal into the database.
        
        Args:
            message_id: Telegram message ID
            token_symbol: Token symbol
            token_address: Token address
            signal_time: Signal timestamp
            raw_text: Raw message text
            
        Returns:
            True if inserted, False if already exists or failed
        """
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                # Check if already exists
                exists = await conn.fetchval('''
                    SELECT 1 FROM raw_telegram_messages
                    WHERE chat_title = $1 AND telegram_message_id = $2
                ''', self.CHANNEL_NAME, message_id)
                
                if exists:
                    return False
                
                # Insert the message
                await conn.execute('''
                    INSERT INTO raw_telegram_messages (
                        telegram_message_id,
                        telegram_chat_id,
                        chat_title,
                        raw_text,
                        message_timestamp,
                        sender_id,
                        sender_username,
                        source_bot,
                        is_parsed,
                        ingested_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                ''', 
                    message_id,
                    0,  # telegram_chat_id - we don't have it
                    self.CHANNEL_NAME,
                    raw_text,
                    signal_time,
                    0,  # sender_id
                    'channel',  # sender_username
                    'trenches_sync',  # source_bot
                    False,  # is_parsed
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to insert signal: {e}")
            return False
    
    async def insert_profit_alert(
        self,
        message_id: int,
        reply_to_msg_id: int,
        multiplier: float,
        alert_time: datetime,
        raw_text: str,
    ) -> bool:
        """
        Insert a profit alert into the database.
        
        Args:
            message_id: Telegram message ID
            reply_to_msg_id: Message ID this is replying to
            multiplier: Profit multiplier
            alert_time: Alert timestamp
            raw_text: Raw message text
            
        Returns:
            True if inserted, False if already exists or failed
        """
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                # Check if already exists
                exists = await conn.fetchval('''
                    SELECT 1 FROM raw_telegram_messages
                    WHERE chat_title = $1 AND telegram_message_id = $2
                ''', self.CHANNEL_NAME, message_id)
                
                if exists:
                    return False
                
                # Insert the message
                # Note: reply_to_msg_id is stored in raw_json since there's no dedicated column
                raw_json = f'{{"reply_to_msg_id": {reply_to_msg_id}, "multiplier": {multiplier}}}'
                
                await conn.execute('''
                    INSERT INTO raw_telegram_messages (
                        telegram_message_id,
                        telegram_chat_id,
                        chat_title,
                        raw_text,
                        raw_json,
                        message_timestamp,
                        sender_id,
                        sender_username,
                        source_bot,
                        is_parsed,
                        ingested_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                ''', 
                    message_id,
                    0,  # telegram_chat_id
                    self.CHANNEL_NAME,
                    raw_text,
                    raw_json,
                    alert_time,
                    0,  # sender_id
                    'channel',  # sender_username
                    'trenches_sync',  # source_bot
                    False,  # is_parsed
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to insert profit alert: {e}")
            return False
