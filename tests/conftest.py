"""
Test fixtures for the trading bot test suite.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.models import Position, PositionStatus, BuySignal, ProfitAlert


@pytest.fixture
def sample_buy_signal():
    """Create a sample buy signal for testing."""
    return BuySignal(
        message_id=12345,
        token_symbol="TRUMP",
        token_address="6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_profit_alert():
    """Create a sample profit alert for testing."""
    return ProfitAlert(
        message_id=12346,
        reply_to_msg_id=12345,
        multiplier=2.5,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_position():
    """Create a sample position for testing."""
    return Position(
        token_address="6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump",
        token_symbol="TRUMP",
        buy_time=datetime.now(timezone.utc),
        buy_amount_sol=0.1,
        signal_msg_id=12345,
        status=PositionStatus.OPEN,
    )


@pytest.fixture
def sample_buy_message():
    """Sample buy signal message from the channel."""
    return """🚨 *ALERT*

`// VOLUME + SM APE SIGNAL DETECTED` 🧪

├ Token: - $TRUMP
├ MC: $123,456
├ LP: $50,000
├ Vol: $10,000
└ `6YK4hC2rVQwKwXLJ9rgJCHhktNJPpFNvqjAh7fW1pump`

🔥 High volume detected!
"""


@pytest.fixture
def sample_profit_message():
    """Sample profit alert message from the channel."""
    return """📈 `PROFIT ALERT` 🚀

Token: $TRUMP
Current: **2.5X** 🎯

Original buy: $0.001
Current: $0.0025
"""


@pytest.fixture
def tmp_state_file(tmp_path):
    """Create a temporary state file path."""
    return tmp_path / "test_state.json"


@pytest.fixture
def mock_telegram_client():
    """Create a mock Telegram client."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=True)
    client.get_entity = AsyncMock()
    client.send_message = AsyncMock()
    return client


@pytest.fixture
def mock_settings(monkeypatch, tmp_path):
    """Create mock settings with environment variables."""
    monkeypatch.setenv("TELEGRAM_API_ID", "12345678")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef1234567890abcdef1234567890")
    monkeypatch.setenv("TRADING_DRY_RUN", "true")
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "bot.log"))
