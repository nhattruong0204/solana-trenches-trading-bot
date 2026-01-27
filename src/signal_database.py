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
    loser_signals: list[SignalWithPnL] = field(default_factory=list)  # Signals with no profit alerts


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
                        raw_json = a['raw_json']
                        # Handle JSONB (returned as dict by asyncpg) or TEXT (string)
                        if raw_json is None:
                            json_data = {}
                        elif isinstance(raw_json, dict):
                            # asyncpg returns JSONB as dict directly
                            json_data = raw_json
                        else:
                            # Fallback: parse as JSON string
                            json_data = json.loads(raw_json)
                    except (json.JSONDecodeError, TypeError):
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
        
        # Get top and worst performers (show 15 each)
        sorted_by_mult = sorted(with_profit, key=lambda s: s.max_multiplier, reverse=True)
        top_performers = sorted_by_mult[:15]
        
        sorted_by_mult_asc = sorted(with_profit, key=lambda s: s.max_multiplier)
        worst_performers = sorted_by_mult_asc[:15]
        
        # Get loser signals (sorted by timestamp, most recent first)
        loser_signals = sorted(losers, key=lambda s: s.signal.timestamp, reverse=True)[:15]
        
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
            loser_signals=loser_signals,
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

    # =========================================================================
    # Channel State / Cursor Management (Production-Grade Pattern)
    # =========================================================================
    
    async def get_channel_state(self, channel_id: int) -> dict:
        """
        Get the current state/cursor for a channel.
        
        Returns:
            dict with last_message_id, bootstrap_completed, etc.
        """
        if not self._pool:
            return {"last_message_id": 0, "bootstrap_completed": False}
        
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT last_message_id, bootstrap_completed, last_processed_at
                    FROM telegram_channel_state
                    WHERE channel_id = $1
                ''', channel_id)
                
                if row:
                    return {
                        "last_message_id": row["last_message_id"],
                        "bootstrap_completed": row["bootstrap_completed"],
                        "last_processed_at": row["last_processed_at"],
                    }
                return {"last_message_id": 0, "bootstrap_completed": False}
                
        except Exception as e:
            logger.error(f"Failed to get channel state: {e}")
            return {"last_message_id": 0, "bootstrap_completed": False}
    
    async def update_channel_cursor(
        self, 
        channel_id: int, 
        channel_name: str,
        last_message_id: int,
        mark_bootstrap_complete: bool = False
    ) -> bool:
        """
        Update the cursor (last_message_id) for a channel.
        
        This should be called AFTER successfully processing and committing messages.
        
        Args:
            channel_id: Telegram channel ID
            channel_name: Channel name for reference
            last_message_id: The latest message ID that was processed
            mark_bootstrap_complete: Set to True after initial full sync
            
        Returns:
            True if updated successfully
        """
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                if mark_bootstrap_complete:
                    await conn.execute('''
                        INSERT INTO telegram_channel_state 
                            (channel_id, channel_name, last_message_id, last_processed_at, 
                             bootstrap_completed, bootstrap_completed_at, updated_at)
                        VALUES ($1, $2, $3, NOW(), TRUE, NOW(), NOW())
                        ON CONFLICT (channel_id) DO UPDATE SET
                            last_message_id = GREATEST(telegram_channel_state.last_message_id, $3),
                            last_processed_at = NOW(),
                            bootstrap_completed = TRUE,
                            bootstrap_completed_at = COALESCE(telegram_channel_state.bootstrap_completed_at, NOW()),
                            updated_at = NOW()
                    ''', channel_id, channel_name, last_message_id)
                else:
                    await conn.execute('''
                        INSERT INTO telegram_channel_state 
                            (channel_id, channel_name, last_message_id, last_processed_at, updated_at)
                        VALUES ($1, $2, $3, NOW(), NOW())
                        ON CONFLICT (channel_id) DO UPDATE SET
                            last_message_id = GREATEST(telegram_channel_state.last_message_id, $3),
                            last_processed_at = NOW(),
                            updated_at = NOW()
                    ''', channel_id, channel_name, last_message_id)
                
                logger.info(f"Updated cursor for channel {channel_id}: last_message_id={last_message_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update channel cursor: {e}")
            return False
    
    async def ensure_channel_state_table(self) -> bool:
        """
        Ensure the telegram_channel_state table exists.
        Called on startup to handle upgrades from older versions.
        """
        if not self._pool:
            return False
        
        try:
            async with self._pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS telegram_channel_state (
                        id SERIAL PRIMARY KEY,
                        channel_id BIGINT NOT NULL UNIQUE,
                        channel_name TEXT NOT NULL,
                        last_message_id BIGINT NOT NULL DEFAULT 0,
                        last_processed_at TIMESTAMP WITH TIME ZONE,
                        bootstrap_completed BOOLEAN DEFAULT FALSE,
                        bootstrap_completed_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                return True
        except Exception as e:
            logger.error(f"Failed to ensure channel_state table: {e}")
            return False

    async def get_signals_for_real_pnl(
        self, 
        days: Optional[int] = None
    ) -> list[TokenSignal]:
        """
        Get signals for real PnL calculation.
        
        Args:
            days: Number of days to look back (None for all time)
            
        Returns:
            List of TokenSignal objects with token addresses
        """
        if not self._pool:
            return []
        
        try:
            async with self._pool.acquire() as conn:
                if days:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                    rows = await conn.fetch('''
                        SELECT id, telegram_message_id, message_timestamp, raw_text
                        FROM raw_telegram_messages
                        WHERE chat_title = $1
                        AND source_bot = 'trenches_sync'
                        AND raw_json IS NULL
                        AND message_timestamp >= $2
                        ORDER BY message_timestamp DESC
                    ''', self.CHANNEL_NAME, cutoff)
                else:
                    rows = await conn.fetch('''
                        SELECT id, telegram_message_id, message_timestamp, raw_text
                        FROM raw_telegram_messages
                        WHERE chat_title = $1
                        AND source_bot = 'trenches_sync'
                        AND raw_json IS NULL
                        ORDER BY message_timestamp DESC
                    ''', self.CHANNEL_NAME)
                
                signals = []
                for row in rows:
                    symbol, address, fdv = parse_signal_message(row['raw_text'] or '')
                    if symbol and address:
                        signals.append(TokenSignal(
                            db_id=row['id'],
                            telegram_msg_id=row['telegram_message_id'],
                            timestamp=row['message_timestamp'],
                            token_symbol=symbol,
                            token_address=address,
                            initial_fdv=fdv,
                        ))
                
                return signals
                
        except Exception as e:
            logger.error(f"Failed to get signals for real PnL: {e}")
            return []

    async def get_signals_with_pnl_for_compare(
        self, 
        days: Optional[int] = None
    ) -> list[SignalWithPnL]:
        """
        Get signals with their profit alerts for comparison.
        
        Uses the same logic as get_signals_in_period for consistency.
        
        Args:
            days: Number of days to look back (None for all time)
            
        Returns:
            List of SignalWithPnL objects
        """
        # Reuse the existing get_signals_in_period method
        return await self.get_signals_in_period(days)


@dataclass
class RealPnLResult:
    """Result of a real-time PnL calculation for a single token."""
    
    signal: TokenSignal
    current_price: Optional[float] = None
    current_mcap: Optional[float] = None
    initial_mcap: Optional[float] = None
    multiplier: Optional[float] = None
    pnl_percent: Optional[float] = None
    is_rugged: bool = False
    error: Optional[str] = None
    
    @property
    def status_emoji(self) -> str:
        if self.is_rugged:
            return "💀"
        if self.multiplier is None:
            return "❓"
        if self.multiplier >= 10:
            return "🚀"
        if self.multiplier >= 2:
            return "🟢"
        if self.multiplier >= 1:
            return "🟡"
        return "🔴"


@dataclass
class RealPnLStats:
    """Aggregated real-time PnL statistics."""
    
    total_signals: int = 0
    successful_fetches: int = 0
    rugged_count: int = 0
    winners: int = 0  # > 1X
    losers: int = 0   # < 1X
    avg_multiplier: float = 0.0
    best_multiplier: float = 0.0
    worst_multiplier: float = 0.0
    avg_pnl_percent: float = 0.0
    period_label: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    results: list[RealPnLResult] = field(default_factory=list)
    top_performers: list[RealPnLResult] = field(default_factory=list)
    worst_performers: list[RealPnLResult] = field(default_factory=list)
    rugged_tokens: list[RealPnLResult] = field(default_factory=list)


@dataclass
class CompareResult:
    """Comparison result for a single token - signal PnL vs real PnL."""
    
    signal: TokenSignal
    signal_multiplier: Optional[float] = None  # From profit alerts
    signal_pnl_percent: Optional[float] = None
    real_multiplier: Optional[float] = None  # From live DexScreener
    real_pnl_percent: Optional[float] = None
    is_rugged: bool = False
    has_profit_alert: bool = False
    
    @property
    def best_multiplier(self) -> float:
        """Get the best of signal or real multiplier for sorting."""
        mults = [m for m in [self.signal_multiplier, self.real_multiplier] if m is not None]
        return max(mults) if mults else 0
    
    @property
    def signal_emoji(self) -> str:
        """Emoji for signal PnL status."""
        if not self.has_profit_alert:
            return "❌"
        if self.signal_multiplier is None:
            return "❓"
        if self.signal_multiplier >= 10:
            return "🚀"
        if self.signal_multiplier >= 2:
            return "🟢"
        if self.signal_multiplier >= 1:
            return "🟡"
        return "🔴"
    
    @property
    def real_emoji(self) -> str:
        """Emoji for real PnL status."""
        if self.is_rugged:
            return "💀"
        if self.real_multiplier is None:
            return "❓"
        if self.real_multiplier >= 10:
            return "🚀"
        if self.real_multiplier >= 2:
            return "🟢"
        if self.real_multiplier >= 1:
            return "🟡"
        return "🔴"


@dataclass
class CompareStats:
    """Aggregated comparison statistics."""
    
    total_signals: int = 0
    period_label: str = ""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    results: list[CompareResult] = field(default_factory=list)
    
    # Signal PnL stats
    signal_winners: int = 0
    signal_avg_mult: float = 0.0
    
    # Real PnL stats  
    real_winners: int = 0
    real_avg_mult: float = 0.0
    rugged_count: int = 0


async def fetch_token_price_dexscreener(token_address: str) -> dict:
    """
    Fetch current token price and market cap from DexScreener.
    
    Args:
        token_address: Solana token address
        
    Returns:
        Dict with price, mcap, liquidity info
    """
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = await client.get(url)
            
            if response.status_code != 200:
                return {"error": f"API error: {response.status_code}"}
            
            data = response.json()
            pairs = data.get("pairs", [])
            
            if not pairs:
                return {"error": "No trading pairs found", "is_rugged": True}
            
            # Get the pair with highest liquidity
            best_pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            
            price_usd = float(best_pair.get("priceUsd", 0) or 0)
            mcap = float(best_pair.get("marketCap", 0) or best_pair.get("fdv", 0) or 0)
            liquidity = float(best_pair.get("liquidity", {}).get("usd", 0) or 0)
            
            # Check if rugged (very low liquidity or price)
            is_rugged = liquidity < 100 or mcap < 1000
            
            return {
                "price_usd": price_usd,
                "mcap": mcap,
                "liquidity": liquidity,
                "is_rugged": is_rugged,
                "pair_address": best_pair.get("pairAddress"),
                "dex": best_pair.get("dexId"),
            }
            
    except httpx.TimeoutException:
        return {"error": "Timeout fetching price"}
    except Exception as e:
        return {"error": str(e)}


async def calculate_real_pnl(
    signals: list[TokenSignal],
    progress_callback=None,
) -> RealPnLStats:
    """
    Calculate real-time PnL by fetching current prices from DexScreener.
    
    Args:
        signals: List of signals to calculate PnL for
        progress_callback: Optional async callback for progress updates
        
    Returns:
        RealPnLStats with all results
    """
    results = []
    total = len(signals)
    
    for i, signal in enumerate(signals):
        # Progress update
        if progress_callback and (i + 1) % 10 == 0:
            await progress_callback(i + 1, total)
        
        # Fetch current price
        price_data = await fetch_token_price_dexscreener(signal.token_address)
        
        result = RealPnLResult(signal=signal)
        
        if "error" in price_data:
            result.error = price_data["error"]
            result.is_rugged = price_data.get("is_rugged", False)
        else:
            result.current_price = price_data.get("price_usd")
            result.current_mcap = price_data.get("mcap")
            result.is_rugged = price_data.get("is_rugged", False)
            
            # Calculate multiplier if we have initial FDV
            if signal.initial_fdv and result.current_mcap:
                result.initial_mcap = signal.initial_fdv
                result.multiplier = result.current_mcap / signal.initial_fdv
                result.pnl_percent = (result.multiplier - 1) * 100
        
        results.append(result)
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    # Calculate aggregated stats
    successful = [r for r in results if r.multiplier is not None]
    rugged = [r for r in results if r.is_rugged]
    
    multipliers = [r.multiplier for r in successful if r.multiplier]
    winners = [r for r in successful if r.multiplier and r.multiplier >= 1]
    losers = [r for r in successful if r.multiplier and r.multiplier < 1]
    
    # Sort for top/worst performers
    sorted_by_mult = sorted(successful, key=lambda r: r.multiplier or 0, reverse=True)
    top_performers = sorted_by_mult[:15]
    worst_performers = sorted_by_mult[-15:][::-1] if len(sorted_by_mult) > 15 else sorted_by_mult[::-1]
    
    # Date range
    timestamps = [s.signal.timestamp for s in results]
    start_date = min(timestamps) if timestamps else None
    end_date = max(timestamps) if timestamps else None
    
    return RealPnLStats(
        total_signals=total,
        successful_fetches=len(successful),
        rugged_count=len(rugged),
        winners=len(winners),
        losers=len(losers),
        avg_multiplier=sum(multipliers) / len(multipliers) if multipliers else 0,
        best_multiplier=max(multipliers) if multipliers else 0,
        worst_multiplier=min(multipliers) if multipliers else 0,
        avg_pnl_percent=sum(r.pnl_percent for r in successful if r.pnl_percent) / len(successful) if successful else 0,
        start_date=start_date,
        end_date=end_date,
        results=results,
        top_performers=top_performers,
        worst_performers=worst_performers,
        rugged_tokens=rugged[:15],
    )


async def calculate_comparison(
    signals_with_pnl: list[SignalWithPnL],
    progress_callback=None,
) -> CompareStats:
    """
    Calculate comparison between signal PnL (profit alerts) and real PnL (live prices).
    
    Args:
        signals_with_pnl: List of signals with their profit alerts
        progress_callback: Optional async callback for progress updates
        
    Returns:
        CompareStats with all comparison results sorted by best multiplier
    """
    results = []
    total = len(signals_with_pnl)
    
    for i, swp in enumerate(signals_with_pnl):
        # Progress update
        if progress_callback and (i + 1) % 10 == 0:
            await progress_callback(i + 1, total)
        
        signal = swp.signal
        
        # Create comparison result
        result = CompareResult(signal=signal)
        
        # Signal PnL from profit alerts
        if swp.max_multiplier:
            result.has_profit_alert = True
            result.signal_multiplier = swp.max_multiplier
            result.signal_pnl_percent = swp.pnl_percent
        
        # Real PnL from DexScreener
        price_data = await fetch_token_price_dexscreener(signal.token_address)
        
        if "error" not in price_data:
            current_mcap = price_data.get("mcap")
            result.is_rugged = price_data.get("is_rugged", False)
            
            if signal.initial_fdv and current_mcap:
                result.real_multiplier = current_mcap / signal.initial_fdv
                result.real_pnl_percent = (result.real_multiplier - 1) * 100
        else:
            result.is_rugged = price_data.get("is_rugged", False)
        
        results.append(result)
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    # Sort by best multiplier (highest first)
    sorted_results = sorted(results, key=lambda r: r.best_multiplier, reverse=True)
    
    # Calculate stats
    signal_mults = [r.signal_multiplier for r in results if r.signal_multiplier]
    real_mults = [r.real_multiplier for r in results if r.real_multiplier]
    signal_winners = len([m for m in signal_mults if m >= 1])
    real_winners = len([m for m in real_mults if m >= 1])
    rugged = len([r for r in results if r.is_rugged])
    
    # Date range
    timestamps = [r.signal.timestamp for r in results]
    start_date = min(timestamps) if timestamps else None
    end_date = max(timestamps) if timestamps else None
    
    return CompareStats(
        total_signals=total,
        period_label="",
        start_date=start_date,
        end_date=end_date,
        results=sorted_results,
        signal_winners=signal_winners,
        signal_avg_mult=sum(signal_mults) / len(signal_mults) if signal_mults else 0,
        real_winners=real_winners,
        real_avg_mult=sum(real_mults) / len(real_mults) if real_mults else 0,
        rugged_count=rugged,
    )
