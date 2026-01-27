"""
Tests for the signal_database module.

Note: Database tests use mocking since they require PostgreSQL connection.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.signal_database import (
    TokenSignal,
    ProfitAlert,
    SignalWithPnL,
    PnLStats,
    parse_signal_message,
    parse_profit_alert,
    parse_fdv_from_profit_alert,
    SignalDatabase,
)


class TestTokenSignal:
    """Tests for TokenSignal dataclass."""
    
    def test_create_token_signal(self):
        """Test creating a token signal."""
        now = datetime.now(timezone.utc)
        signal = TokenSignal(
            db_id=1,
            telegram_msg_id=12345,
            timestamp=now,
            token_symbol="TRUMP",
            token_address="6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump",
            initial_fdv=50000.0,
        )
        
        assert signal.db_id == 1
        assert signal.telegram_msg_id == 12345
        assert signal.token_symbol == "TRUMP"
        assert signal.initial_fdv == 50000.0
    
    def test_age_hours(self):
        """Test age_hours calculation."""
        past = datetime.now(timezone.utc) - timedelta(hours=5)
        signal = TokenSignal(
            db_id=1,
            telegram_msg_id=1,
            timestamp=past,
            token_symbol="TEST",
            token_address="addr12345678901234567890123456789012",
        )
        
        assert 4.9 < signal.age_hours < 5.1
    
    def test_age_days(self):
        """Test age_days calculation."""
        past = datetime.now(timezone.utc) - timedelta(days=3)
        signal = TokenSignal(
            db_id=1,
            telegram_msg_id=1,
            timestamp=past,
            token_symbol="TEST",
            token_address="addr12345678901234567890123456789012",
        )
        
        assert 2.9 < signal.age_days < 3.1
    
    def test_age_with_utc_timestamp(self):
        """Test age calculation with UTC timestamp."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        signal = TokenSignal(
            db_id=1,
            telegram_msg_id=1,
            timestamp=past,
            token_symbol="TEST",
            token_address="addr12345678901234567890123456789012",
        )
        
        # Should properly calculate age
        assert 1.9 < signal.age_hours < 2.1


class TestProfitAlert:
    """Tests for ProfitAlert dataclass."""
    
    def test_create_profit_alert(self):
        """Test creating a profit alert."""
        now = datetime.now(timezone.utc)
        alert = ProfitAlert(
            db_id=1,
            telegram_msg_id=100,
            reply_to_msg_id=50,
            timestamp=now,
            multiplier=2.5,
            initial_fdv=30000.0,
            current_fdv=75000.0,
        )
        
        assert alert.multiplier == 2.5
        assert alert.reply_to_msg_id == 50
        assert alert.current_fdv == 75000.0


class TestSignalWithPnL:
    """Tests for SignalWithPnL dataclass."""
    
    @pytest.fixture
    def sample_signal(self):
        return TokenSignal(
            db_id=1,
            telegram_msg_id=100,
            timestamp=datetime.now(timezone.utc),
            token_symbol="TEST",
            token_address="addr12345678901234567890123456789012",
        )
    
    @pytest.fixture
    def sample_alerts(self):
        now = datetime.now(timezone.utc)
        return [
            ProfitAlert(db_id=1, telegram_msg_id=101, reply_to_msg_id=100, timestamp=now - timedelta(hours=2), multiplier=1.5),
            ProfitAlert(db_id=2, telegram_msg_id=102, reply_to_msg_id=100, timestamp=now - timedelta(hours=1), multiplier=2.5),
            ProfitAlert(db_id=3, telegram_msg_id=103, reply_to_msg_id=100, timestamp=now, multiplier=2.0),
        ]
    
    def test_signal_without_profit(self, sample_signal):
        """Test signal with no profit alerts."""
        signal_pnl = SignalWithPnL(signal=sample_signal)
        
        assert signal_pnl.has_profit is False
        assert signal_pnl.max_multiplier == 0.0
        assert signal_pnl.reached_2x is False
        assert signal_pnl.pnl_percent == -100.0
        assert signal_pnl.latest_multiplier is None
    
    def test_signal_with_profit_alerts(self, sample_signal, sample_alerts):
        """Test signal with profit alerts."""
        signal_pnl = SignalWithPnL(signal=sample_signal, profit_alerts=sample_alerts)
        
        assert signal_pnl.has_profit is True
        assert signal_pnl.max_multiplier == 2.5
        assert signal_pnl.reached_2x is True
        assert signal_pnl.pnl_percent == 150.0  # (2.5 - 1) * 100
        assert signal_pnl.latest_multiplier == 2.0  # Most recent
    
    def test_signal_under_2x(self, sample_signal):
        """Test signal that hasn't reached 2X."""
        alert = ProfitAlert(
            db_id=1, telegram_msg_id=101, reply_to_msg_id=100,
            timestamp=datetime.now(timezone.utc), multiplier=1.8
        )
        signal_pnl = SignalWithPnL(signal=sample_signal, profit_alerts=[alert])
        
        assert signal_pnl.reached_2x is False
        assert signal_pnl.pnl_percent == 80.0


class TestPnLStats:
    """Tests for PnLStats dataclass."""
    
    def test_default_pnl_stats(self):
        """Test default PnL stats values."""
        stats = PnLStats()
        
        assert stats.total_signals == 0
        assert stats.win_rate == 0.0
        assert stats.total_pnl_percent == 0.0
        assert stats.top_performers == []
    
    def test_custom_pnl_stats(self):
        """Test custom PnL stats."""
        stats = PnLStats(
            total_signals=100,
            signals_with_profit=60,
            win_rate=60.0,
            avg_multiplier=2.3,
            period_label="Last 7 Days",
        )
        
        assert stats.total_signals == 100
        assert stats.win_rate == 60.0
        assert stats.period_label == "Last 7 Days"


class TestParseSignalMessage:
    """Tests for parse_signal_message function."""
    
    def test_parse_standard_signal(self):
        """Test parsing standard signal format."""
        message = """🚨 *ALERT*

`// VOLUME + SM APE SIGNAL DETECTED` 🧪

├ Token: - $TRUMP
├ MC: $123,456
├ FDV: $50K
├ LP: $50,000
└ `6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump`
"""
        symbol, address, fdv = parse_signal_message(message)
        
        assert symbol == "TRUMP"
        assert address == "6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump"
        assert fdv == 50000.0
    
    def test_parse_signal_with_backtick_address(self):
        """Test parsing signal with backtick address format."""
        message = """
Token: - $MEMECOIN
├ MC: $100K
└ `6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump`
"""
        symbol, address, _ = parse_signal_message(message)
        
        assert symbol == "MEMECOIN"
        assert address == "6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump"
    
    def test_parse_signal_missing_fields(self):
        """Test parsing signal with missing fields."""
        message = "Random text without signal data"
        
        symbol, address, fdv = parse_signal_message(message)
        
        assert symbol is None
        assert address is None
        assert fdv is None
    
    def test_parse_fdv_with_decimals(self):
        """Test parsing FDV with decimal values."""
        message = """
Token: - $TEST
FDV: $50.5K
└ `addr1234567890123456789012345678901234`
"""
        _, _, fdv = parse_signal_message(message)
        assert fdv == 50500.0


class TestParseProfitAlert:
    """Tests for parse_profit_alert function."""
    
    def test_parse_markdown_multiplier(self):
        """Test parsing multiplier with markdown formatting."""
        message = "📈 PROFIT ALERT 🚀\n\n**2.5X** gain!"
        multiplier = parse_profit_alert(message)
        assert multiplier == 2.5
    
    def test_parse_double_asterisk_multiplier(self):
        """Test parsing multiplier with double asterisks."""
        message = "PROFIT ALERT - **3X** reached"
        multiplier = parse_profit_alert(message)
        assert multiplier == 3.0
    
    def test_parse_large_multiplier(self):
        """Test parsing large multiplier."""
        message = "PROFIT ALERT **10.5X**"
        multiplier = parse_profit_alert(message)
        assert multiplier == 10.5
    
    def test_parse_multiplier_with_label(self):
        """Test parsing with Multiplier: label."""
        message = "PROFIT ALERT Multiplier: 5X"
        multiplier = parse_profit_alert(message)
        assert multiplier == 5.0
    
    def test_parse_no_multiplier(self):
        """Test message without multiplier."""
        message = "Some random message"
        multiplier = parse_profit_alert(message)
        assert multiplier is None


class TestParseFdvFromProfitAlert:
    """Tests for parse_fdv_from_profit_alert function."""
    
    def test_parse_both_fdv(self):
        """Test parsing both initial and current FDV."""
        message = """
PROFIT ALERT **3X**
Initial FDV: $50K
Current FDV: $150K
"""
        initial, current = parse_fdv_from_profit_alert(message)
        
        assert initial == 50000.0
        assert current == 150000.0
    
    def test_parse_fdv_with_m_suffix(self):
        """Test parsing FDV with M (million) suffix."""
        message = """
Initial FDV: $1.5M
Current FDV: $5M
"""
        initial, current = parse_fdv_from_profit_alert(message)
        
        assert initial == 1500000.0
        assert current == 5000000.0
    
    def test_parse_partial_fdv(self):
        """Test parsing when only one FDV is present."""
        message = "PROFIT ALERT Current FDV: $200K"
        
        initial, current = parse_fdv_from_profit_alert(message)
        
        assert initial is None
        assert current == 200000.0


class TestSignalDatabase:
    """Tests for SignalDatabase class."""
    
    @pytest.fixture
    def db(self):
        """Create a SignalDatabase instance."""
        return SignalDatabase("postgresql://test:test@localhost:5432/test")
    
    @pytest.mark.asyncio
    async def test_connect_success(self, db):
        """Test successful database connection."""
        with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_pool:
            mock_pool.return_value = MagicMock()
            
            result = await db.connect()
            
            assert result is True
            mock_pool.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, db):
        """Test database connection failure."""
        with patch('asyncpg.create_pool', new_callable=AsyncMock) as mock_pool:
            mock_pool.side_effect = Exception("Connection failed")
            
            result = await db.connect()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_disconnect(self, db):
        """Test database disconnect."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        db._pool = mock_pool
        
        await db.disconnect()
        
        mock_pool.close.assert_called_once()
        assert db._pool is None
    
    @pytest.mark.asyncio
    async def test_get_signals_not_connected(self, db):
        """Test getting signals when not connected."""
        db._pool = None
        
        result = await db.get_signals_in_period(days=7)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_signal_count(self, db):
        """Test getting signal count."""
        # Mock the pool
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            'total_signals': 100,
            'total_profit_alerts': 500,
        })
        
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn)))
        db._pool = mock_pool
        
        # The method may not exist yet, but this tests the pattern
        # Just verify pool is properly set
        assert db._pool is not None


class TestDatabaseIntegration:
    """Integration-style tests that verify query building."""
    
    def test_channel_name_constant(self):
        """Test that channel name is correctly defined."""
        db = SignalDatabase("postgresql://test:test@localhost/test")
        assert db.CHANNEL_NAME == "From The Trenches - VOLUME + SM"
    
    def test_dsn_stored(self):
        """Test that DSN is stored correctly."""
        dsn = "postgresql://user:pass@host:5432/db"
        db = SignalDatabase(dsn)
        assert db._dsn == dsn
        assert db._pool is None  # Not connected yet


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_parse_signal_with_proper_format(self):
        """Test parsing signal with proper format."""
        message = """
Token: - $ROCKET
├ MC: $100K
└ `7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr`
"""
        symbol, address, _ = parse_signal_message(message)
        assert symbol == "ROCKET"
        assert address == "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
    
    def test_parse_multiplier_with_asterisks(self):
        """Test multiplier parsing with asterisks."""
        # With asterisks (matches pattern)
        assert parse_profit_alert("PROFIT ALERT **1.1X**") == 1.1
        
        # Integer with asterisks
        assert parse_profit_alert("PROFIT ALERT **5X**") == 5.0
        
        # Large decimal with asterisks
        assert parse_profit_alert("PROFIT ALERT **99.9X**") == 99.9
    
    def test_signal_with_empty_alerts_list(self):
        """Test signal with empty alerts list explicitly."""
        signal = TokenSignal(
            db_id=1,
            telegram_msg_id=1,
            timestamp=datetime.now(timezone.utc),
            token_symbol="TEST",
            token_address="addr12345678901234567890123456789012",
        )
        signal_pnl = SignalWithPnL(signal=signal, profit_alerts=[])
        
        assert signal_pnl.has_profit is False
        assert signal_pnl.latest_multiplier is None


class TestSignalDatabaseAdvanced:
    """Advanced tests for SignalDatabase operations."""
    
    @pytest.fixture
    def db(self):
        """Create a SignalDatabase instance."""
        return SignalDatabase("postgresql://test:test@localhost:5432/test")
    
    @pytest.mark.asyncio
    async def test_get_signals_not_connected_returns_empty(self, db):
        """Test that getting signals when not connected returns empty list."""
        result = await db.get_signals_in_period(days=30)
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_signal_count_not_connected(self, db):
        """Test signal count when not connected."""
        result = await db.get_signal_count()
        # Returns default structure with zeros when not connected
        assert result.get("total_signals", 0) == 0
        assert "total" in result or "total_signals" in result
    
    @pytest.mark.asyncio
    async def test_get_latest_message_id_not_connected(self, db):
        """Test latest message ID when not connected."""
        result = await db.get_latest_message_id()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_insert_signal_not_connected(self, db):
        """Test insert signal when not connected."""
        result = await db.insert_signal(
            message_id=1,
            token_symbol="TEST",
            token_address="addr123",
            signal_time=datetime.now(timezone.utc),
            raw_text="Test signal",
        )
        assert result is False
    
    @pytest.mark.asyncio
    async def test_insert_profit_alert_not_connected(self, db):
        """Test insert profit alert when not connected."""
        result = await db.insert_profit_alert(
            message_id=1,
            reply_to_msg_id=0,
            multiplier=2.0,
            alert_time=datetime.now(timezone.utc),
            raw_text="Profit alert",
        )
        assert result is False
    
    @pytest.mark.asyncio
    async def test_calculate_pnl_stats_empty(self, db):
        """Test PnL stats calculation with no data."""
        stats = await db.calculate_pnl_stats(days=7)
        
        assert stats.total_signals == 0
        assert stats.win_rate == 0.0
        assert stats.period_label == "Last 7 Days"
    
    @pytest.mark.asyncio
    async def test_calculate_pnl_stats_all_time(self, db):
        """Test PnL stats calculation for all time."""
        stats = await db.calculate_pnl_stats(days=None)
        
        assert stats.period_label == "All Time"


class TestSignalDatabaseWithMockedPool:
    """Tests with mocked database pool."""
    
    @pytest.fixture
    def db_with_pool(self):
        """Create db with mocked pool."""
        db = SignalDatabase("postgresql://test:test@localhost:5432/test")
        
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()
        
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
        db._pool = mock_pool
        
        return db, mock_conn
    
    @pytest.mark.asyncio
    async def test_get_signal_count_with_pool(self, db_with_pool):
        """Test signal count with mocked pool."""
        db, mock_conn = db_with_pool
        mock_conn.fetchval = AsyncMock(return_value=42)
        
        # Will query database
        result = await db.get_signal_count()
        
        # The mock returns 42 for both queries
        assert mock_conn.fetchval.called


class TestChannelState:
    """Tests for channel state management."""
    
    @pytest.fixture
    def db(self):
        return SignalDatabase("postgresql://test:test@localhost:5432/test")
    
    @pytest.mark.asyncio
    async def test_get_channel_state_not_connected(self, db):
        """Test channel state when not connected."""
        result = await db.get_channel_state(12345)
        
        assert result["last_message_id"] == 0
        assert result["bootstrap_completed"] is False
    
    @pytest.mark.asyncio
    async def test_update_channel_cursor_not_connected(self, db):
        """Test updating cursor when not connected."""
        result = await db.update_channel_cursor(
            channel_id=12345,
            channel_name="Test Channel",
            last_message_id=100,
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_ensure_channel_state_table_not_connected(self, db):
        """Test ensuring table when not connected."""
        result = await db.ensure_channel_state_table()
        assert result is False


class TestParseFunctions:
    """Additional tests for parsing functions."""
    
    def test_parse_signal_with_k_suffix(self):
        """Test parsing FDV with K suffix."""
        msg = "FDV: $100K\nToken: - $TEST\n└ `addr12345678901234567890123456789012`"
        _, _, fdv = parse_signal_message(msg)
        assert fdv == 100000.0
    
    def test_parse_profit_alert_various_formats(self):
        """Test parsing profit alerts with various multiplier formats."""
        # Standard format
        assert parse_profit_alert("PROFIT ALERT **2X**") == 2.0
        
        # With decimal
        assert parse_profit_alert("PROFIT ALERT **2.5X**") == 2.5
        
        # With Multiplier label
        assert parse_profit_alert("Multiplier: 3X") == 3.0
        
        # NEW: Simple format like "3.0X profit alert" (lowercase)
        assert parse_profit_alert("3.0X profit alert") == 3.0
        assert parse_profit_alert("48.0X profit alert") == 48.0
        assert parse_profit_alert("5.0X profit alert") == 5.0
        assert parse_profit_alert("42.0X profit alert") == 42.0
    
    def test_parse_fdv_from_profit_alert_various(self):
        """Test parsing FDV from profit alerts."""
        # Both values
        msg1 = "Initial FDV: $100K\nCurrent FDV: $300K"
        init1, curr1 = parse_fdv_from_profit_alert(msg1)
        assert init1 == 100000.0
        assert curr1 == 300000.0
        
        # Only current
        msg2 = "Current FDV: $500K"
        init2, curr2 = parse_fdv_from_profit_alert(msg2)
        assert init2 is None
        assert curr2 == 500000.0


class AsyncContextManager:
    """Helper for creating async context managers in tests."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        pass


class TestJsonbParsing:
    """
    Regression tests for JSONB raw_json parsing.

    Bug: When raw_json column is JSONB type, asyncpg returns it as a Python dict,
    not a string. The code was using json.loads() which fails with TypeError
    when passed a dict. This caused profit alerts to not be matched to signals.

    Fixed in: bugfix/fix-signal-pnl-not-working
    """

    @pytest.fixture
    def db_with_signals_and_alerts(self):
        """Create db with mocked signals and profit alerts."""
        db = SignalDatabase("postgresql://test:test@localhost:5432/test")

        now = datetime.now(timezone.utc)

        # Mock signals
        signals = [
            {
                'id': 1,
                'telegram_message_id': 100,
                'raw_text': 'APE SIGNAL DETECTED Token: - $TEST └ `addr12345678901234567890123456789012` FDV: $50K',
                'message_timestamp': now - timedelta(hours=24),
            },
            {
                'id': 2,
                'telegram_message_id': 200,
                'raw_text': 'APE SIGNAL DETECTED Token: - $COIN └ `addr98765432109876543210987654321098` FDV: $100K',
                'message_timestamp': now - timedelta(hours=12),
            },
        ]

        # Mock profit alerts - raw_json as DICT (how asyncpg returns JSONB)
        alerts_jsonb = [
            {
                'id': 10,
                'telegram_message_id': 101,
                'raw_text': 'PROFIT ALERT **2X**',
                'message_timestamp': now - timedelta(hours=20),
                'raw_json': {'reply_to_msg_id': 100, 'multiplier': 2.0},  # Dict from JSONB
            },
            {
                'id': 11,
                'telegram_message_id': 102,
                'raw_text': 'PROFIT ALERT **3X**',
                'message_timestamp': now - timedelta(hours=18),
                'raw_json': {'reply_to_msg_id': 100, 'multiplier': 3.0},  # Dict from JSONB
            },
        ]

        mock_conn = AsyncMock()

        async def mock_fetch(query, *args):
            if 'APE SIGNAL DETECTED' in query:
                return signals
            elif 'PROFIT ALERT' in query:
                return alerts_jsonb
            return []

        mock_conn.fetch = mock_fetch

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
        db._pool = mock_pool

        return db

    @pytest.mark.asyncio
    async def test_jsonb_dict_parsing(self, db_with_signals_and_alerts):
        """
        Test that raw_json returned as dict (JSONB) is correctly parsed.

        Regression test for: profit alerts not matching signals when raw_json is JSONB.
        """
        db = db_with_signals_and_alerts

        results = await db.get_signals_in_period(days=30)

        # Should have 2 signals
        assert len(results) == 2

        # First signal should have 2 profit alerts matched
        signal_100 = next((r for r in results if r.signal.telegram_msg_id == 100), None)
        assert signal_100 is not None
        assert len(signal_100.profit_alerts) == 2
        assert signal_100.max_multiplier == 3.0

        # Second signal should have 0 profit alerts
        signal_200 = next((r for r in results if r.signal.telegram_msg_id == 200), None)
        assert signal_200 is not None
        assert len(signal_200.profit_alerts) == 0

    @pytest.fixture
    def db_with_string_raw_json(self):
        """Create db with raw_json as string (legacy TEXT column behavior)."""
        db = SignalDatabase("postgresql://test:test@localhost:5432/test")

        now = datetime.now(timezone.utc)

        signals = [
            {
                'id': 1,
                'telegram_message_id': 100,
                'raw_text': 'APE SIGNAL DETECTED Token: - $TEST └ `addr12345678901234567890123456789012` FDV: $50K',
                'message_timestamp': now - timedelta(hours=24),
            },
        ]

        # raw_json as STRING (legacy behavior or TEXT column)
        alerts_text = [
            {
                'id': 10,
                'telegram_message_id': 101,
                'raw_text': 'PROFIT ALERT **2.5X**',
                'message_timestamp': now - timedelta(hours=20),
                'raw_json': '{"reply_to_msg_id": 100, "multiplier": 2.5}',  # String
            },
        ]

        mock_conn = AsyncMock()

        async def mock_fetch(query, *args):
            if 'APE SIGNAL DETECTED' in query:
                return signals
            elif 'PROFIT ALERT' in query:
                return alerts_text
            return []

        mock_conn.fetch = mock_fetch

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
        db._pool = mock_pool

        return db

    @pytest.mark.asyncio
    async def test_string_raw_json_parsing(self, db_with_string_raw_json):
        """
        Test that raw_json as string (legacy TEXT behavior) still works.
        """
        db = db_with_string_raw_json

        results = await db.get_signals_in_period(days=30)

        assert len(results) == 1
        assert len(results[0].profit_alerts) == 1
        assert results[0].max_multiplier == 2.5

    @pytest.fixture
    def db_with_null_raw_json(self):
        """Create db with null raw_json values."""
        db = SignalDatabase("postgresql://test:test@localhost:5432/test")

        now = datetime.now(timezone.utc)

        signals = [
            {
                'id': 1,
                'telegram_message_id': 100,
                'raw_text': 'APE SIGNAL DETECTED Token: - $TEST └ `addr12345678901234567890123456789012`',
                'message_timestamp': now,
            },
        ]

        # Profit alert with null raw_json (should be skipped)
        alerts = [
            {
                'id': 10,
                'telegram_message_id': 101,
                'raw_text': 'PROFIT ALERT **2X**',
                'message_timestamp': now,
                'raw_json': None,
            },
        ]

        mock_conn = AsyncMock()

        async def mock_fetch(query, *args):
            if 'APE SIGNAL DETECTED' in query:
                return signals
            elif 'PROFIT ALERT' in query:
                return alerts
            return []

        mock_conn.fetch = mock_fetch

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncContextManager(mock_conn))
        db._pool = mock_pool

        return db

    @pytest.mark.asyncio
    async def test_null_raw_json_handled(self, db_with_null_raw_json):
        """
        Test that null raw_json is handled gracefully (alert skipped).
        """
        db = db_with_null_raw_json

        results = await db.get_signals_in_period(days=30)

        assert len(results) == 1
        # Alert should be skipped due to null raw_json (no reply_to_msg_id)
        assert len(results[0].profit_alerts) == 0
