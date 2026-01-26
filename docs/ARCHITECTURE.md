# Architecture Documentation

## System Overview

The Solana Trenches Trading Bot is an automated trading system that:
1. Monitors a Telegram channel for buy signals
2. Parses and validates signals
3. Executes trades via GMGN bot on Solana
4. Manages positions and tracks P&L
5. Provides admin controls via Telegram bot

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Telegram Network                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │ Signal       │    │ GMGN Bot     │    │ Admin        │          │
│  │ Channel      │    │ @GMGN_sol_bot│    │ Control      │          │
│  └──────┬───────┘    └──────▲───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
└─────────┼───────────────────┼───────────────────┼───────────────────┘
          │                   │                   │
          ▼                   │                   ▼
┌─────────────────────────────┼───────────────────────────────────────┐
│         │                   │                   │                   │
│  ┌──────▼───────┐    ┌──────┴───────┐    ┌──────▼───────┐          │
│  │ TelegramClient│    │ GMGNTrader   │    │ Notification │          │
│  │ (Telethon)   │    │              │    │ Bot          │          │
│  └──────┬───────┘    └──────▲───────┘    └──────────────┘          │
│         │                   │                                       │
│  ┌──────▼───────┐    ┌──────┴───────┐                              │
│  │ MessageParser │    │ TradingBot   │◄────────────────┐           │
│  │              │    │              │                  │           │
│  └──────┬───────┘    └──────┬───────┘                  │           │
│         │                   │                          │           │
│  ┌──────▼───────┐    ┌──────▼───────┐    ┌─────────────┴──┐       │
│  │ BuySignal/   │    │ RiskManager  │    │ TradingState   │       │
│  │ ProfitAlert  │    │              │    │ (JSON)         │       │
│  └──────────────┘    └──────────────┘    └────────────────┘       │
│                                                                     │
│                      APPLICATION LAYER                              │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Core Trading Engine

#### TradingBot (`src/bot.py`)
**Responsibility:** Main orchestrator that coordinates all trading activities.

**Key Methods:**
- `start()` — Initialize and start the bot
- `handle_new_message()` — Process incoming messages
- `handle_buy_signal()` — Execute buy on new signal
- `handle_profit_alert()` — Execute sell on profit target

**Dependencies:**
- TelegramClient (Telethon)
- GMGNTrader
- TradingState
- RiskManager
- MessageParser

**State:** Stateless (delegates to TradingState)

#### GMGNTrader (`src/trader.py`)
**Responsibility:** Abstraction for trade execution via GMGN Telegram bot.

**Interface (FROZEN):**
```python
class GMGNTrader(Protocol):
    async def buy_token(self, token_address: str, amount_sol: float) -> TradeResult
    async def sell_token(self, token_address: str, percentage: float) -> TradeResult
```

**Implementation Details:**
- Sends commands to @GMGN_sol_bot via Telegram
- Waits for confirmation response
- Parses transaction hash from response
- Handles timeouts and errors

#### TradingState (`src/state.py`)
**Responsibility:** Persistent storage for open/closed positions.

**Storage:** JSON file (`trading_state.json`)

**Key Methods:**
```python
async def add_position(position: Position) -> None
async def get_position(token_address: str) -> Position | None
async def update_position(token_address: str, updates: dict) -> None
async def close_position(token_address: str) -> None
async def get_open_positions() -> list[Position]
```

**Thread Safety:** Uses asyncio locks for concurrent access.

### 2. Signal Processing

#### MessageParser (`src/parsers.py`)
**Responsibility:** Composite parser that delegates to specific parsers.

**Parser Types:**
- `BuySignalParser` — Detects "VOLUME + SM APE SIGNAL"
- `ProfitAlertParser` — Detects "PROFIT ALERT" messages

**Pattern Matching:** Uses regex patterns from `constants.py`

**Return Types (FROZEN):**
```python
BuySignalParser.parse(message) -> BuySignal | None
ProfitAlertParser.parse(message) -> ProfitAlert | None
```

#### Signal Patterns (`src/constants.py`)
```python
BUY_SIGNAL_PATTERN = "// VOLUME + SM APE SIGNAL DETECTED"
PROFIT_ALERT_PATTERN = "PROFIT ALERT"
TOKEN_SYMBOL_PATTERN = r'Token:\s*-?\s*\$(\w+)'
TOKEN_ADDRESS_PATTERN = r'[`├└]\s*([1-9A-HJ-NP-Za-km-z]{32,44})'
MULTIPLIER_PATTERN = r'\*?\*?([\d.]+)\s*X\*?\*?'
```

### 3. Domain Models (`src/models.py`)

#### Position (FROZEN)
```python
@dataclass
class Position:
    token_address: str
    token_symbol: str
    buy_time: datetime
    buy_amount_sol: float
    buy_price: float | None
    status: PositionStatus
    sell_transactions: list[SellTransaction]
    signal_message_id: int | None

    def to_dict(self) -> dict
    @classmethod
    def from_dict(cls, data: dict) -> Position
```

#### PositionStatus
```python
class PositionStatus(Enum):
    OPEN = "open"
    PARTIAL_SOLD = "partial_sold"
    CLOSED = "closed"
```

#### BuySignal
```python
@dataclass
class BuySignal:
    token_address: str
    token_symbol: str
    timestamp: datetime
    message_id: int
    raw_message: str
```

#### ProfitAlert
```python
@dataclass
class ProfitAlert:
    multiplier: float
    original_signal_id: int | None
    token_address: str | None
    timestamp: datetime
```

### 4. Risk Management (`src/risk_manager.py`)

**Responsibility:** Enforces trading rules and limits.

#### Components:
- **Stop Loss Manager** — Fixed, trailing, time-based, ATR stops
- **Position Sizer** — Dynamic position sizing based on risk
- **Portfolio Heat Tracker** — Total portfolio exposure
- **Circuit Breaker** — Daily/consecutive loss limits

#### Configuration Classes:
```python
@dataclass
class StopLossConfig:
    enabled: bool
    type: StopLossType  # fixed_percentage, trailing, time_based, atr
    percentage: float
    trailing_activation: float
    time_hours: int

@dataclass
class PositionSizingConfig:
    enabled: bool
    risk_per_trade: float
    min_size_sol: float
    max_size_sol: float

@dataclass
class CircuitBreakerConfig:
    enabled: bool
    daily_loss_limit_pct: float
    consecutive_loss_limit: int
```

### 5. Configuration (`src/config.py`)

**Pattern:** Pydantic Settings with nested models and LRU caching.

```python
class Settings(BaseSettings):
    telegram: TelegramSettings
    trading: TradingSettings
    channel: ChannelSettings
    paths: PathSettings
    risk: RiskSettings
    public_channel: PublicChannelSettings
    subscription: SubscriptionSettings

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

#### Setting Categories:

| Category | Class | Key Fields |
|----------|-------|------------|
| Telegram | `TelegramSettings` | api_id, api_hash, phone, session_name |
| Trading | `TradingSettings` | enabled, dry_run, buy_amount, sell_pct, max_positions |
| Channel | `ChannelSettings` | signal_channel, gmgn_bot |
| Risk | `RiskSettings` | stop_loss_*, position_sizing_*, circuit_breaker_* |
| Paths | `PathSettings` | state_file, log_file |

### 6. Exception Hierarchy (`src/exceptions.py`)

```
TradingBotError (base)
├── ConfigurationError
├── TelegramError
│   ├── TelegramConnectionError
│   ├── TelegramAuthError
│   ├── ChannelNotFoundError
│   └── BotNotFoundError
├── TradingError
│   ├── MaxPositionsError
│   ├── DuplicatePositionError
│   └── TradeExecutionError
├── ParserError
│   ├── InvalidSignalFormatError
│   └── TokenAddressExtractionError
└── StateError
    ├── StatePersistenceError
    └── StateCorruptionError
```

### 7. User Interface

#### CLI (`src/cli.py`)
```bash
trading-bot [OPTIONS]
  --live              Enable live trading
  --buy-amount SOL    Set buy amount
  --sell-percentage % Set sell percentage
  --max-positions N   Max concurrent positions
  --verbose           Debug logging
```

#### Admin Bot (`src/notification_bot.py`)
**Commands:**
- `/status` — Bot status and stats
- `/positions` — List open positions
- `/settings` — Current configuration
- `/setsize <SOL>` — Change buy amount
- `/pause` / `/resume` — Control trading
- `/pnl` — Current P&L summary

#### Remote Controller (`src/controller.py`)
Telegram-based remote control for the bot.

### 8. Strategy System (`src/strategies.py`)

**Built-in Strategies:**

| Name | Type | Description |
|------|------|-------------|
| trailing_15 | Trailing | 15% trailing stop |
| trailing_20 | Trailing | 20% trailing stop |
| fixed_2x | Fixed | Sell at 2X |
| fixed_5x | Fixed | Sell at 5X |
| tiered_2_3_5 | Tiered | Sell 33% at 2X, 3X, 5X |

**Adding New Strategy:**
```python
STRATEGIES["my_strategy"] = TakeProfitStrategy(
    name="my_strategy",
    type=StrategyType.FIXED,
    targets=[TargetLevel(multiplier=3.0, sell_percentage=100)]
)
```

### 9. Data Flow

```
1. Message Event
   └─► TelegramClient receives message from Signal Channel

2. Parse Signal
   └─► MessageParser.parse()
       ├─► BuySignalParser.parse() → BuySignal | None
       └─► ProfitAlertParser.parse() → ProfitAlert | None

3. Validate & Size
   └─► RiskManager
       ├─► check_can_trade() → bool
       ├─► calculate_position_size() → float
       └─► check_circuit_breaker() → bool

4. Execute Trade
   └─► GMGNTrader.buy_token() / sell_token()
       └─► Send command to @GMGN_sol_bot
       └─► Parse response for tx_hash

5. Update State
   └─► TradingState
       ├─► add_position() / update_position()
       └─► Persist to JSON file

6. Notify
   └─► NotificationBot
       └─► Send admin notification
```

### 10. Database Schema (PostgreSQL)

Used by `signal_database.py` for historical analysis:

```sql
-- Signals table (from wallet_tracker)
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    token_address VARCHAR(44) NOT NULL,
    token_symbol VARCHAR(20),
    signal_time TIMESTAMP,
    message_id BIGINT,
    multiplier_reached FLOAT,
    closed_at TIMESTAMP
);
```

## Extension Points

### Adding New Signal Type
1. Add pattern to `constants.py`
2. Create `XxxParser` class in `parsers.py`
3. Add to `MessageParser._parsers` list
4. Create corresponding model in `models.py`
5. Handle in `TradingBot.handle_new_message()`

### Adding New Risk Rule
1. Add configuration to `RiskSettings` in `config.py`
2. Implement check in `RiskManager`
3. Call from `TradingBot` before trade execution

### Adding New Admin Command
1. Create handler method in `NotificationBot`
2. Register with `@events.register(events.NewMessage(pattern=...))`
3. Update `/help` command output

### Adding New Strategy
1. Define strategy in `strategies.py`
2. Add to `STRATEGIES` dict
3. Strategy automatically available for selection

## Security Considerations

- **Credentials:** Never commit `.env` file
- **API Keys:** Telegram API credentials in environment only
- **Session Files:** `.session` files contain auth tokens
- **Wallet Access:** GMGN bot handles wallet, not this code
- **Input Validation:** All user input validated via Pydantic
