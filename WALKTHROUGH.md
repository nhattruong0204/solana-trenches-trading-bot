# Solana Trenches Trading Bot - System Walkthrough

> A comprehensive guide for humans and AI agents to understand the bot architecture, data flow, and operational logic.

---

## Document Purpose

This document provides:
1. **High-level architecture** overview
2. **Module-by-module** breakdown
3. **Data flow** explanations
4. **Decision logic** documentation
5. **Integration points** reference

Designed to be readable by:
- Human developers and operators
- AI agents for code assistance
- New team members onboarding

---

## 1. System Overview

### 1.1 What This Bot Does

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SOLANA TRENCHES TRADING BOT                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   INPUTS:                         OUTPUTS:                          │
│   ┌──────────────────┐           ┌──────────────────┐              │
│   │ Telegram Channel │ ────────► │ Trade Execution  │              │
│   │ (Buy Signals)    │           │ (via GMGN Bot)   │              │
│   └──────────────────┘           └──────────────────┘              │
│   ┌──────────────────┐           ┌──────────────────┐              │
│   │ Profit Alerts    │ ────────► │ Position Sells   │              │
│   │ (2X, 3X, etc.)   │           │ (Based on Rules) │              │
│   └──────────────────┘           └──────────────────┘              │
│   ┌──────────────────┐           ┌──────────────────┐              │
│   │ Admin Commands   │ ────────► │ Bot Control      │              │
│   │ (Telegram Bot)   │           │ & Notifications  │              │
│   └──────────────────┘           └──────────────────┘              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Workflow

```
[Signal Channel] ──► [Parser] ──► [Buy Decision] ──► [GMGN Buy]
                                        │
                                        ▼
                              [Position Tracking]
                                        │
                                        ▼
[Profit Alert] ──────────────► [Sell Decision] ──► [GMGN Sell]
                                        │
                                        ▼
                              [State Persistence]
```

---

## 2. Module Architecture

### 2.1 Module Dependency Graph

```
                              ┌─────────────┐
                              │   main.py   │
                              └──────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │   cli.py    │
                              └──────┬──────┘
                                     │
                        ┌────────────┼────────────┐
                        │            │            │
                 ┌──────▼──────┐     │     ┌──────▼──────┐
                 │   bot.py    │◄────┴────►│notification_│
                 │ (Orchestrator)          │   bot.py    │
                 └──────┬──────┘           └──────┬──────┘
                        │                         │
        ┌───────┬───────┼───────┬───────┐        │
        │       │       │       │       │        │
   ┌────▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐    │
   │parser │ │state│ │trader│ │config│ │models│   │
   └───────┘ └─────┘ └──────┘ └──────┘ └──────┘   │
                                                  │
        ┌─────────────────────────────────────────┘
        │
   ┌────▼────────┐  ┌────────────┐  ┌─────────────┐
   │signal_db    │  │signal_hist │  │strategies   │
   └─────────────┘  └────────────┘  └─────────────┘
```

### 2.2 Module Responsibilities

| Module | Responsibility | Key Classes/Functions |
|--------|---------------|----------------------|
| `bot.py` | Main orchestrator, event loop | `TradingBot` |
| `notification_bot.py` | Telegram bot UI, commands | `NotificationBot` |
| `parsers.py` | Message parsing | `BuySignalParser`, `ProfitAlertParser` |
| `trader.py` | Trade execution | `GMGNTrader`, `BaseTrader` |
| `state.py` | Position tracking | `TradingState` |
| `strategies.py` | Take profit logic | `StrategyManager`, `TakeProfitStrategy` |
| `signal_database.py` | PostgreSQL integration | `SignalDatabase` |
| `signal_history.py` | Local signal tracking | `SignalHistory` |
| `price_history.py` | Price data fetching | `PriceHistoryFetcher`, `PriceHistory` |
| `accurate_backtester.py` | Strategy backtesting | `AccurateBacktester` |
| `strategy_simulator.py` | Strategy simulation | `StrategySimulator` |
| `config.py` | Configuration | `Settings` |
| `models.py` | Data structures | `Position`, `BuySignal`, `ProfitAlert` |
| `constants.py` | Magic values | Patterns, defaults |
| `exceptions.py` | Error types | Custom exceptions |

---

## 3. Data Flow Deep Dive

### 3.1 Buy Signal Flow

```
STEP 1: Message Received from Channel
────────────────────────────────────
Telegram Event
    ↓
TradingBot._handle_new_message()
    ↓
MessageParser.parse()

STEP 2: Signal Validation
─────────────────────────
BuySignalParser.can_parse(text)
    → Check for "VOLUME + SM APE SIGNAL DETECTED"
    ↓
BuySignalParser.parse()
    → Extract: token_symbol, token_address
    → Validate: Solana address format

STEP 3: Buy Decision
────────────────────
TradingBot._process_buy_signal()
    ↓
Check: trading_enabled?
Check: not trading_paused?
Check: position_count < max_positions?
Check: not duplicate_position?
    ↓
If all pass → Execute buy

STEP 4: Trade Execution
───────────────────────
GMGNTrader.buy_token(address, amount_sol, symbol)
    ↓
Send message to @GMGN_sol_bot: "buy <address> <sol>"
    ↓
Wait for confirmation

STEP 5: State Update
────────────────────
TradingState.add_position()
    ↓
Position(token_address, symbol, buy_time, amount)
    ↓
Save to trading_state.json
```

### 3.2 Sell Decision Flow

```
STEP 1: Profit Alert Received
─────────────────────────────
Telegram Event with "PROFIT ALERT"
    ↓
ProfitAlertParser.parse()
    → Extract: multiplier (e.g., 2.5X)
    → Link to: original signal (reply_to_msg_id)

STEP 2: Position Lookup
───────────────────────
TradingState.get_position_by_signal(signal_msg_id)
    ↓
Returns: Position or None

STEP 3: Strategy Evaluation
───────────────────────────
StrategyManager.should_sell(current_mult, peak_mult)
    ↓
Active Strategy Type:
    ├── TRAILING_STOP: current <= peak * (1 - stop_pct)?
    ├── FIXED_EXIT: current >= target_mult?
    └── TIERED_EXIT: current >= tier_mult?
    ↓
Returns: (should_sell, reason, sell_percentage)

STEP 4: Sell Execution
──────────────────────
If should_sell:
    GMGNTrader.sell_token(address, percentage, symbol)
    ↓
    Send message to @GMGN_sol_bot: "sell <address> <pct>%"

STEP 5: Position Update
───────────────────────
Position.mark_partial_sell(percentage, multiplier)
    ↓
If sold_percentage >= 100:
    Position.status = CLOSED
    ↓
Save state
```

### 3.3 Telegram Command Flow

```
USER INPUT                    BOT PROCESSING                 OUTPUT
───────────                   ──────────────                 ──────
/status          →    NotificationBot._cmd_status()   →    Status message
    │                         │
    │                         ▼
    │               Get TradingBot.get_status()
    │                         │
    │                         ▼
    │               Format: running, uptime, trades
    │                         │
    └─────────────────────────┴──────────────────→    📊 BOT STATUS
                                                       • Running: ✅
                                                       • Uptime: 2h 30m
                                                       • Trades: 5
```

---

## 4. Strategy System

### 4.1 Strategy Hierarchy

```
TakeProfitStrategy (dataclass)
    │
    ├── id: str           # Unique identifier
    ├── name: str         # Display name
    ├── strategy_type: StrategyType
    │       ├── TRAILING_STOP
    │       ├── FIXED_EXIT
    │       └── TIERED_EXIT
    ├── rank: int         # Performance rank (1 = best)
    ├── enabled: bool     # Active for trading
    └── params: dict      # Strategy-specific parameters
```

### 4.2 Strategy Evaluation Logic

```python
# Pseudocode for strategy evaluation

def should_sell(current_mult, peak_mult):
    strategy = get_active_strategy()
    
    if strategy.type == TRAILING_STOP:
        stop_level = peak_mult * (1 - stop_pct)
        if current_mult <= stop_level:
            return SELL, "trailing_stop", 100%
    
    elif strategy.type == FIXED_EXIT:
        if current_mult >= target_mult:
            return SELL, "target_hit", 100%
        if current_mult <= stop_loss_mult:
            return SELL, "stop_loss", 100%
    
    elif strategy.type == TIERED_EXIT:
        for (tier_mult, tier_pct) in tiers:
            if current_mult >= tier_mult:
                return SELL, f"tier_{tier_mult}", tier_pct
    
    return HOLD, None, 0
```

### 4.3 Strategy Performance Data

| Rank | Strategy | Win Rate | Net PnL | ROI |
|------|----------|----------|---------|-----|
| 1 | Trailing 15% | 77.3% | +4.03 SOL | 40.3% |
| 2 | Trailing 20% | 77.3% | +3.67 SOL | 36.7% |
| 3 | Trailing 25% | 77.3% | +3.31 SOL | 33.1% |
| 4 | Trailing 30% | 68.2% | +2.96 SOL | 29.6% |
| 5 | Fixed 5X | 45.5% | +2.62 SOL | 26.2% |

---

## 5. State Management

### 5.1 State File Structure

```json
// trading_state.json
{
  "positions": {
    "TokenAddress123...": {
      "token_address": "TokenAddress123...",
      "token_symbol": "TRUMP",
      "buy_time": "2026-01-24T10:30:00+00:00",
      "buy_amount_sol": 0.1,
      "signal_msg_id": 12345,
      "status": "open",
      "sold_percentage": 0.0,
      "last_multiplier": 1.5
    }
  },
  "signal_to_token": {
    "12345": "TokenAddress123..."
  }
}
```

### 5.2 State Operations

```
┌──────────────────────────────────────────────────────────┐
│                    TradingState                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  add_position(position)                                  │
│      → Add new position to tracking                      │
│      → Map signal_msg_id → token_address                 │
│      → Mark state dirty                                  │
│                                                          │
│  get_position(token_address) → Position | None           │
│                                                          │
│  get_position_by_signal(msg_id) → Position | None        │
│                                                          │
│  update_position(address, updates)                       │
│      → Update position fields                            │
│      → Mark state dirty                                  │
│                                                          │
│  save() → Async write to JSON                            │
│                                                          │
│  load() → Async read from JSON                           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Database Schema

### 6.1 PostgreSQL Tables

```sql
-- telegram_messages: Raw message storage
CREATE TABLE telegram_messages (
    id SERIAL PRIMARY KEY,
    telegram_msg_id BIGINT NOT NULL,
    channel_id BIGINT,
    raw_text TEXT,
    timestamp TIMESTAMPTZ,
    reply_to_msg_id BIGINT
);

-- parsed_signals: Extracted token signals
CREATE TABLE parsed_signals (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES telegram_messages(id),
    token_symbol VARCHAR(50),
    token_address VARCHAR(64),
    initial_fdv DECIMAL,
    parsed_at TIMESTAMPTZ
);

-- profit_alerts: Parsed profit alerts
CREATE TABLE profit_alerts (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES telegram_messages(id),
    signal_id INTEGER REFERENCES parsed_signals(id),
    multiplier DECIMAL,
    current_fdv DECIMAL,
    parsed_at TIMESTAMPTZ
);
```

### 6.2 Query Patterns

```python
# Get signal PnL for time period
async def get_signal_pnl(days: int) -> PnLStats:
    """
    1. Query signals from parsed_signals WHERE timestamp > NOW() - days
    2. For each signal, query related profit_alerts
    3. Calculate max_multiplier from alerts
    4. Compute win_rate, avg_multiplier, etc.
    """
```

---

## 7. Configuration Reference

### 7.1 Environment Variables

```bash
# Required - Telegram
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abc123...
TELEGRAM_BOT_TOKEN=123:ABC...
TELEGRAM_ADMIN_USER_ID=987654321

# Required - Trading
GMGN_WALLET=HN7cABqLq46...

# Optional - Trading Config
TRADING_DRY_RUN=true          # Default: true
TRADING_BUY_AMOUNT_SOL=0.1    # Default: 0.1
TRADING_SELL_PERCENTAGE=50     # Default: 50
TRADING_MIN_MULTIPLIER=2.0     # Default: 2.0
TRADING_MAX_POSITIONS=10       # Default: 10

# Optional - Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secret
POSTGRES_DATABASE=wallet_tracker
```

### 7.2 Settings Class Hierarchy

```
Settings (BaseSettings)
    ├── TelegramSettings
    │       ├── api_id: int
    │       ├── api_hash: str
    │       └── session_name: str
    ├── TradingSettings
    │       ├── enabled: bool
    │       ├── dry_run: bool
    │       ├── buy_amount_sol: float
    │       └── ...
    ├── ChannelSettings
    │       ├── signal_channel: str
    │       └── gmgn_bot: str
    └── PathSettings
            ├── state_file: Path
            └── log_file: Path
```

---

## 8. Error Handling

### 8.1 Exception Hierarchy

```
TradingBotError (base)
    ├── ConfigurationError
    │       └── MissingEnvironmentVariableError
    ├── TelegramError
    │       ├── TelegramConnectionError
    │       ├── TelegramAuthenticationError
    │       ├── ChannelNotFoundError
    │       └── BotNotFoundError
    ├── TradingError
    │       ├── TradingDisabledError
    │       ├── MaxPositionsReachedError
    │       ├── DuplicatePositionError
    │       └── TradeExecutionError
    └── StateError
            ├── StateCorruptionError
            ├── StatePersistenceError
            └── PositionNotFoundError
```

### 8.2 Error Recovery

```
Error Type              Recovery Action
──────────              ───────────────
TelegramConnectionError → Retry with backoff, notify admin
TradeExecutionError     → Log, notify admin, don't crash
StateCorruptionError    → Load backup, notify admin
MaxPositionsReachedError → Skip trade, log, continue
```

---

## 9. Operational Workflows

### 9.1 Bot Startup Sequence

```
1. Load configuration from .env
2. Validate required environment variables
3. Initialize TradingState (load from JSON)
4. Create TelegramClient (user session)
5. Create NotificationBot (bot token)
6. Resolve signal channel entity
7. Initialize GMGN trader
8. Connect to PostgreSQL (if configured)
9. Register event handlers
10. Send startup notification
11. Enter event loop
```

### 9.2 Graceful Shutdown

```
1. Receive SIGINT/SIGTERM
2. Set shutdown flag
3. Complete pending trades
4. Save state to JSON
5. Disconnect Telegram clients
6. Close database connections
7. Exit
```

### 9.3 Daily Operations Checklist

```
□ Check bot status (/status)
□ Review open positions (/positions)
□ Check PnL (/signalpnl 1d)
□ Sync new signals if needed (/syncsignals)
□ Verify wallet balance
□ Check error logs
```

---

## 10. Integration Points

### 10.1 External APIs

| API | Purpose | Rate Limit |
|-----|---------|------------|
| Telegram MTProto | Channel monitoring | Standard |
| Telegram Bot API | Commands & notifications | 30/sec |
| GMGN Bot | Trade execution | Per bot limits |
| DexScreener | Current prices | ~300/min |
| GeckoTerminal | OHLCV candles | 30/min |

### 10.2 API Usage Patterns

```python
# DexScreener - Get token price
async def get_price(token_address: str) -> float:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    response = await httpx.get(url)
    data = response.json()
    return data["pairs"][0]["priceUsd"]

# GeckoTerminal - Get OHLCV candles
async def get_candles(pool_address: str) -> list[Candle]:
    url = f"{GECKO_API}/networks/solana/pools/{pool_address}/ohlcv/minute"
    params = {"aggregate": 15, "limit": 1000}
    response = await httpx.get(url, params=params)
    return parse_candles(response.json())
```

---

## 11. Testing & Quality

### 11.1 Test Coverage

```
Module                Coverage
──────                ────────
exceptions.py         100%
constants.py          100%
strategies.py         95%
models.py             95%
parsers.py            85%
config.py             80%
state.py              81%
trader.py             81%
──────────────────────────
Overall               46%
```

### 11.2 Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=term

# Run specific module tests
pytest tests/test_strategies.py -v
```

---

## 12. Troubleshooting Guide

### 12.1 Common Issues

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| "Bot not connected" | Missing bot token | Set TELEGRAM_BOT_TOKEN |
| "Channel not found" | Wrong channel username | Verify SIGNAL_CHANNEL |
| "Trading disabled" | Dry run mode | Use --live flag |
| "Max positions" | Position limit reached | Increase TRADING_MAX_POSITIONS |
| "Invalid address" | Bad wallet format | Check Solana address format |

### 12.2 Debug Commands

```bash
# Check bot logs
tail -f trading_bot.log

# Check Docker logs
docker logs -f trading-bot

# Test database connection
psql $DATABASE_URL -c "SELECT COUNT(*) FROM telegram_messages;"
```

---

## 13. Quick Reference Card

### Commands Cheat Sheet

```
INFORMATION:           TRADING:              CONFIG:
/status               /pause                /setsize 0.1
/positions            /resume               /setsell 50
/pnl                  /strategies           /setmultiplier 2.0
/signalpnl 7d                              /setwallet <addr>
/realpnl 7d           SYNC:
/compare 7d           /syncsignals
/simulate 30          /bootstrap
```

### Strategy Quick Picks

```
Conservative: Trailing 15% (Rank #1, 77% win rate)
Balanced:     Fixed 3X (Rank #8, 55% win rate)
Aggressive:   Fixed 5X (Rank #5, 45% win rate)
```

---

## Document Metadata

```yaml
title: Solana Trenches Trading Bot - System Walkthrough
version: 1.0.0
last_updated: 2026-01-24
author: Development Team
audience: 
  - Human developers
  - AI coding assistants
  - System operators
format: Markdown with ASCII diagrams
```

---

*End of Walkthrough Document*
