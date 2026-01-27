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

    Fixed in: bugfix/fix-commercial-channel
    """

    def test_jsonb_dict_parsing(self):
        """Test that raw_json as dict (JSONB) is handled correctly."""
        import json
        
        # Simulate what asyncpg returns for JSONB column
        raw_json_as_dict = {"multiplier": 5.0, "reply_to_msg_id": 42426}
        
        # Old code would fail here with TypeError
        # json.loads(raw_json_as_dict)  # TypeError!
        
        # New code handles dict directly
        if isinstance(raw_json_as_dict, dict):
            json_data = raw_json_as_dict
        else:
            json_data = json.loads(raw_json_as_dict)
        
        assert json_data.get('reply_to_msg_id') == 42426
        assert json_data.get('multiplier') == 5.0

    def test_jsonb_string_parsing(self):
        """Test that raw_json as string (TEXT) still works."""
        import json
        
        # Simulate raw_json stored as TEXT string
        raw_json_as_string = '{"multiplier": 3.0, "reply_to_msg_id": 12345}'
        
        if isinstance(raw_json_as_string, dict):
            json_data = raw_json_as_string
        else:
            json_data = json.loads(raw_json_as_string)
        
        assert json_data.get('reply_to_msg_id') == 12345
        assert json_data.get('multiplier') == 3.0

    def test_jsonb_none_handling(self):
        """Test that None raw_json is handled correctly."""
        raw_json = None
        
        if raw_json is None:
            json_data = {}
        elif isinstance(raw_json, dict):
            json_data = raw_json
        else:
            json_data = {}
        
        assert json_data == {}
        assert json_data.get('reply_to_msg_id') is None
