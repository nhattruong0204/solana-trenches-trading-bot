# Code Conventions & Standards

## Code Style

### Formatting
- **Formatter:** Black with 100 character line length
- **Linter:** Ruff with rules: E, W, F, I, B, C4, UP, ARG, SIM
- **Type Checker:** mypy in strict mode

### Run formatters:
```bash
black src/ tests/
ruff check src/ tests/ --fix
mypy src/
```

## Python Conventions

### Type Hints
All functions must have type hints:
```python
# Good
def parse_signal(message: str) -> BuySignal | None:
    ...

# Bad - missing type hints
def parse_signal(message):
    ...
```

### Async/Await
All I/O operations must be async:
```python
# Good
async def fetch_position(token: str) -> Position | None:
    async with aiofiles.open(state_file) as f:
        data = await f.read()
    return Position.from_dict(json.loads(data))

# Bad - blocking I/O
def fetch_position(token: str) -> Position | None:
    with open(state_file) as f:
        data = f.read()
    return Position.from_dict(json.loads(data))
```

### Error Handling
Use custom exceptions with context:
```python
# Good
try:
    result = await trader.buy_token(address, amount)
except TelegramError as e:
    logger.error(f"Trade failed: {e}", exc_info=True)
    raise TradeExecutionError(f"Buy failed for {address}") from e

# Bad - swallowing exceptions
try:
    result = await trader.buy_token(address, amount)
except Exception:
    return None
```

### Logging
Use structured logging with appropriate levels:
```python
# Good
logger.info("Trade executed", extra={
    "token": token_address,
    "amount": amount_sol,
    "tx_hash": result.tx_hash
})

logger.debug(f"Parsing message: {message[:100]}...")
logger.warning(f"Position not found: {token}")
logger.error(f"Trade failed: {error}", exc_info=True)

# Bad - print statements
print(f"Trade executed for {token}")
```

## Architecture Patterns

### Dependency Injection
Pass dependencies explicitly:
```python
# Good
class TradingBot:
    def __init__(
        self,
        client: TelegramClient,
        trader: GMGNTrader,
        state: TradingState,
        settings: Settings
    ):
        self.client = client
        self.trader = trader
        self.state = state
        self.settings = settings

# Bad - global state
class TradingBot:
    def __init__(self):
        self.client = get_global_client()
        self.settings = Settings()
```

### Configuration
Always use Pydantic settings:
```python
# Good
from src.config import get_settings

settings = get_settings()
amount = settings.trading.buy_amount_sol

# Bad - direct environment access
import os
amount = float(os.environ.get("BUY_AMOUNT", "0.1"))
```

### Constants
Use constants module, never hardcode:
```python
# Good
from src.constants import BUY_SIGNAL_PATTERN, DEFAULT_TIMEOUT

if BUY_SIGNAL_PATTERN in message:
    ...

# Bad - hardcoded strings
if "// VOLUME + SM APE SIGNAL DETECTED" in message:
    ...
```

## Data Models

### Dataclass Usage
Use dataclasses for domain models:
```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Position:
    token_address: str
    token_symbol: str
    buy_time: datetime = field(default_factory=datetime.now)
    status: PositionStatus = PositionStatus.OPEN
```

### Serialization
Implement `to_dict()` and `from_dict()` for persistence:
```python
@dataclass
class Position:
    ...

    def to_dict(self) -> dict:
        return {
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "buy_time": self.buy_time.isoformat(),
            "status": self.status.value
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        return cls(
            token_address=data["token_address"],
            token_symbol=data["token_symbol"],
            buy_time=datetime.fromisoformat(data["buy_time"]),
            status=PositionStatus(data["status"])
        )
```

### Enums
Use Enums for status values:
```python
from enum import Enum

class PositionStatus(Enum):
    OPEN = "open"
    PARTIAL_SOLD = "partial_sold"
    CLOSED = "closed"
```

## Parser Conventions

### Return Types
Parsers return `T | None`, never raise for invalid input:
```python
# Good
def parse(self, message: str) -> BuySignal | None:
    if not self._is_valid_signal(message):
        return None
    return self._extract_signal(message)

# Bad - raising on invalid input
def parse(self, message: str) -> BuySignal:
    if not self._is_valid_signal(message):
        raise InvalidSignalError("Not a valid signal")
    return self._extract_signal(message)
```

### Pattern Matching
Use compiled regex and extract to constants:
```python
import re
from src.constants import TOKEN_ADDRESS_PATTERN

_TOKEN_ADDRESS_RE = re.compile(TOKEN_ADDRESS_PATTERN)

def extract_token_address(message: str) -> str | None:
    match = _TOKEN_ADDRESS_RE.search(message)
    return match.group(1) if match else None
```

## Testing Conventions

### Test Structure
```
tests/
├── conftest.py          # Shared fixtures
├── test_<module>.py     # One test file per source module
└── fixtures/            # Test data files (if needed)
```

### Fixture Usage
Use fixtures from conftest.py:
```python
# conftest.py
@pytest.fixture
def sample_buy_signal():
    return BuySignal(
        token_address="ABC123...",
        token_symbol="TEST",
        timestamp=datetime.now(),
        message_id=12345
    )

# test_parsers.py
def test_parse_buy_signal(sample_buy_signal):
    # Use fixture
    assert sample_buy_signal.token_symbol == "TEST"
```

### Mock External Services
Always mock Telegram and external APIs:
```python
@pytest.fixture
def mock_telegram_client():
    client = AsyncMock(spec=TelegramClient)
    client.send_message = AsyncMock(return_value=MagicMock(id=1))
    return client

async def test_buy_token(mock_telegram_client):
    trader = GMGNTrader(mock_telegram_client, settings)
    result = await trader.buy_token("ABC123", 0.1)
    mock_telegram_client.send_message.assert_called_once()
```

### Async Tests
Use pytest-asyncio:
```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

## Git Conventions

### Commit Messages
```
type: short description

- Detail 1
- Detail 2

Types: feat, fix, refactor, test, docs, chore
```

### Branch Names
```
feature/description
fix/issue-description
refactor/component-name
```

## Documentation

### Docstrings
Use Google-style docstrings for public APIs:
```python
def buy_token(self, token_address: str, amount_sol: float) -> TradeResult:
    """Execute a buy order for the specified token.

    Args:
        token_address: Solana token address (base58 encoded).
        amount_sol: Amount in SOL to spend.

    Returns:
        TradeResult with success status and transaction hash.

    Raises:
        TradeExecutionError: If the trade fails to execute.
    """
```

### Module-Level Comments
Every module should have a brief docstring:
```python
"""Signal parsing and validation.

This module provides parsers for extracting trading signals from
Telegram messages, including buy signals and profit alerts.
"""
```

## Security Rules

### Never Commit Secrets
- `.env` files
- `.session` files
- API keys or credentials
- Wallet private keys

### Input Validation
Always validate external input:
```python
# Good
from pydantic import BaseModel, validator

class TradingSettings(BaseModel):
    buy_amount_sol: float

    @validator("buy_amount_sol")
    def validate_amount(cls, v):
        if not 0.001 <= v <= 100:
            raise ValueError("Amount must be between 0.001 and 100 SOL")
        return v

# Bad - no validation
buy_amount = float(user_input)
```

### Rate Limiting
Implement rate limiting for external calls:
```python
from asyncio import sleep

async def send_with_rate_limit(message: str):
    await sleep(0.5)  # Minimum delay between messages
    await client.send_message(bot, message)
```

## Performance Guidelines

### Caching
Use LRU cache for expensive operations:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

### Async Operations
Batch async operations when possible:
```python
# Good - parallel execution
results = await asyncio.gather(
    fetch_position(token1),
    fetch_position(token2),
    fetch_position(token3)
)

# Bad - sequential execution
result1 = await fetch_position(token1)
result2 = await fetch_position(token2)
result3 = await fetch_position(token3)
```

### Resource Cleanup
Use context managers:
```python
# Good
async with aiofiles.open(file_path, 'w') as f:
    await f.write(data)

# Bad - manual cleanup
f = await aiofiles.open(file_path, 'w')
await f.write(data)
await f.close()  # May not run if exception occurs
```
