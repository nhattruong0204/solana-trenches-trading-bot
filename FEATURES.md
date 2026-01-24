# Solana Auto Trading Bot - Feature Documentation

> Complete feature reference for the Solana Trenches Trading Bot v1.0

---

## Table of Contents

1. [Core Trading Features](#1-core-trading-features)
2. [Signal Detection & Parsing](#2-signal-detection--parsing)
3. [Take Profit Strategies](#3-take-profit-strategies)
4. [Telegram Bot Interface](#4-telegram-bot-interface)
5. [PnL Tracking & Analytics](#5-pnl-tracking--analytics)
6. [Backtesting & Simulation](#6-backtesting--simulation)
7. [State Management](#7-state-management)
8. [Configuration & Settings](#8-configuration--settings)
9. [Deployment Features](#9-deployment-features)
10. [API Integrations](#10-api-integrations)

---

## 1. Core Trading Features

### 1.1 Automated Signal-Based Trading
- **Real-time Signal Monitoring**: Monitors "From The Trenches - VOLUME + SM" Telegram channel
- **Instant Buy Execution**: Automatically buys tokens when buy signals detected
- **Configurable Position Sizing**: Set SOL amount per trade (0.001 - 100 SOL)
- **Maximum Position Limits**: Control concurrent open positions (1-100)

### 1.2 Trade Execution via GMGN Bot
- **Integration**: Executes trades through `@GMGN_sol_bot` on Telegram
- **Buy Commands**: `buy <token_address> <amount_sol>`
- **Sell Commands**: `sell <token_address> <percentage>`
- **Retry Logic**: Automatic retries with exponential backoff (3 attempts)

### 1.3 Trading Modes
| Mode | Description |
|------|-------------|
| **Dry Run** (default) | Simulates trades without execution |
| **Live Trading** | Executes real trades on Solana |

### 1.4 Position Management
- Track open, partial, and closed positions
- Monitor position value with real-time multipliers
- Calculate holding duration in hours/days
- Estimated position value calculation

---

## 2. Signal Detection & Parsing

### 2.1 Buy Signal Detection
**Trigger Pattern**: `// VOLUME + SM APE SIGNAL DETECTED`

**Extracted Data**:
- Token symbol (e.g., `$TRUMP`)
- Token address (Solana base58, 32-44 chars)
- Timestamp
- Message ID

### 2.2 Profit Alert Detection
**Trigger Pattern**: `PROFIT ALERT`

**Extracted Data**:
- Multiplier achieved (e.g., `2.5X`)
- Reference to original signal
- Current FDV (optional)

### 2.3 Address Validation
- Base58 encoding verification
- Length validation (32-44 characters)
- Invalid character detection (no 0, O, I, l)

---

## 3. Take Profit Strategies

### 3.1 Strategy Types

| Type | Description |
|------|-------------|
| **Trailing Stop** | Sell when price drops X% from peak |
| **Fixed Exit** | Sell at target multiplier + stop loss |
| **Tiered Exit** | Sell portions at different multipliers |

### 3.2 Pre-Configured Strategies (13 Total)

#### Trailing Stop Strategies
| ID | Name | Stop % | Win Rate | ROI |
|----|------|--------|----------|-----|
| `trailing_15` | Trailing Stop (15%) | 15% | 77.3% | 40.3% |
| `trailing_20` | Trailing Stop (20%) | 20% | 77.3% | 36.7% |
| `trailing_25` | Trailing Stop (25%) | 25% | 77.3% | 33.1% |
| `trailing_30` | Trailing Stop (30%) | 30% | 68.2% | 29.6% |

#### Fixed Exit Strategies
| ID | Name | Target | Win Rate | ROI |
|----|------|--------|----------|-----|
| `fixed_5x` | Fixed Exit 5.0X | 5.0X | 45.5% | 26.2% |
| `fixed_4x` | Fixed Exit 4.0X | 4.0X | 50.0% | 23.2% |
| `fixed_3x` | Fixed Exit 3.0X | 3.0X | 54.5% | 16.1% |
| `fixed_2_5x` | Fixed Exit 2.5X | 2.5X | 59.1% | 13.0% |
| `fixed_2x` | Fixed Exit 2.0X | 2.0X | 72.7% | 11.1% |
| `fixed_1_5x` | Fixed Exit 1.5X | 1.5X | 72.7% | 3.5% |

#### Tiered Exit Strategies
| ID | Name | Tiers | Win Rate | ROI |
|----|------|-------|----------|-----|
| `tiered_2_3_5` | Tiered 2X+3X+5X | 33%@2X, 33%@3X, 34%@5X | 63.6% | 18.7% |
| `tiered_2_3` | Tiered 2X+3X | 50%@2X, 50%@3X | 72.7% | 14.5% |
| `tiered_1_5_2_5` | Tiered 1.5X+2.5X | 50%@1.5X, 50%@2.5X | 68.2% | 9.2% |

### 3.3 Strategy Management
- Enable/disable strategies via Telegram
- Toggle individual strategies
- Strategy state persistence
- Ranked by backtesting performance

---

## 4. Telegram Bot Interface

### 4.1 Bot Commands

#### Information Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome message and wallet setup |
| `/menu` | Interactive button menu |
| `/status` | Bot status (uptime, trades, etc.) |
| `/positions` | List open positions |
| `/settings` | Current trading settings |
| `/stats` | Trading statistics |
| `/help` | Show all commands |

#### PnL Commands
| Command | Description |
|---------|-------------|
| `/pnl` | Current positions PnL |
| `/signalpnl <days>` | Signal PnL for N days |
| `/signalpnl all` | Lifetime signal PnL |
| `/realpnl <days>` | Real-time PnL (live prices) |
| `/compare <days>` | Compare signal vs real PnL |

**Clickable Token Links**: In `/signalpnl`, `/realpnl`, and `/compare` results, each token symbol (e.g., `$TRUMP`) is a clickable hyperlink that redirects you directly to the original APE SIGNAL message in the "From The Trenches" channel.

#### Signal Sync Commands
| Command | Description |
|---------|-------------|
| `/bootstrap` | One-time full history sync |
| `/syncsignals` | Sync only NEW signals (incremental) |

#### Configuration Commands
| Command | Description |
|---------|-------------|
| `/setsize <SOL>` | Set buy amount |
| `/setsell <percent>` | Set sell percentage |
| `/setmultiplier <X>` | Set minimum sell multiplier |
| `/setmax <count>` | Set max open positions |
| `/setwallet <address>` | Set GMGN wallet address |

#### Control Commands
| Command | Description |
|---------|-------------|
| `/pause` | Pause trading |
| `/resume` | Resume trading |
| `/strategies` | View and toggle strategies |
| `/simulate <days>` | Run strategy simulation |

### 4.2 Interactive Menu
- Button-based navigation
- Real-time status display
- Quick access to all features
- Strategy toggle buttons

### 4.3 Notifications
| Event | Notification |
|-------|--------------|
| Signal Detected | Token symbol, address, links |
| Trade Executed | Status, amount, multiplier |
| Profit Alert | Multiplier, threshold, action |
| Bot Started | Configuration summary |

---

## 5. PnL Tracking & Analytics

### 5.1 Signal PnL (Historical)
- Based on profit alerts from channel
- Win rate calculation
- Average/best/worst multipliers
- Time-filtered (1d, 3d, 7d, 30d, all)

### 5.2 Real PnL (Live Prices)
- Fetches current prices from DexScreener
- Real-time multiplier calculation
- Unrealized PnL tracking

### 5.3 PnL Statistics
| Metric | Description |
|--------|-------------|
| Total Signals | Number of signals in period |
| Win Rate | % of profitable signals |
| 2X Rate | % reaching 2X or higher |
| Avg Multiplier | Average return multiplier |
| Best/Worst | Extreme performers |

### 5.4 Database Integration
- PostgreSQL for signal history
- Stores raw messages and parsed signals
- Links profit alerts to signals
- Historical data preservation

---

## 6. Backtesting & Simulation

### 6.1 Accurate Backtester
- Uses real OHLCV candle data from GeckoTerminal
- 15-minute candle resolution
- Simulates trailing stops tick-by-tick
- Maximum hold time (72 hours default)

### 6.2 Strategy Simulator
- Tests all 13 strategies against historical data
- Fee-inclusive calculations
- Comprehensive result reporting

### 6.3 Fee Structure
| Fee Type | Amount |
|----------|--------|
| Buy Fee | 1% |
| Sell Fee | 1% |
| Network Fee | ~0.00025 SOL/tx |
| Priority Fee | 0.5% |
| Slippage | 1% (avg) |
| **Breakeven** | ~1.05X |

### 6.4 Simulation Results
- Win rate per strategy
- Net PnL in SOL
- ROI percentage
- Average holding time
- Data coverage metrics

---

## 7. State Management

### 7.1 Trading State
- Persistent JSON storage (`trading_state.json`)
- Crash recovery support
- Atomic saves with locking

### 7.2 Tracked Data
| Data | Description |
|------|-------------|
| Positions | All open/partial/closed positions |
| Signal Mappings | Message ID → Position |
| Strategy State | Enabled/disabled strategies |
| Signal History | Local signal tracking |

### 7.3 State Operations
- Add/remove positions
- Update position status
- Mark partial/full sells
- Signal-to-position lookup

---

## 8. Configuration & Settings

### 8.1 Environment Variables

#### Required
| Variable | Description |
|----------|-------------|
| `TELEGRAM_API_ID` | Telegram API ID |
| `TELEGRAM_API_HASH` | Telegram API hash |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_ADMIN_USER_ID` | Your Telegram user ID |

#### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_DRY_RUN` | `true` | Enable dry run mode |
| `TRADING_BUY_AMOUNT_SOL` | `0.1` | SOL per trade |
| `TRADING_SELL_PERCENTAGE` | `50` | Sell % at target |
| `TRADING_MIN_MULTIPLIER` | `2.0` | Minimum sell trigger |
| `TRADING_MAX_POSITIONS` | `10` | Max concurrent positions |
| `GMGN_WALLET` | - | GMGN wallet address |

#### Database
| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | DB host |
| `POSTGRES_PORT` | `5432` | DB port |
| `POSTGRES_USER` | `postgres` | DB user |
| `POSTGRES_PASSWORD` | - | DB password |
| `POSTGRES_DATABASE` | `wallet_tracker` | DB name |

### 8.2 Runtime Configuration
All settings adjustable via Telegram commands without restart.

---

## 9. Deployment Features

### 9.1 Docker Support
- Multi-stage Dockerfile
- Docker Compose configuration
- Volume mounting for persistence
- Health checks

### 9.2 VPS Deployment
- Deploy script (`deploy-to-vps.sh`)
- SSH key-based deployment
- Auto-restart on failure
- Log persistence

### 9.3 File Server
- HTTP server for results archive
- JSON file listing
- API endpoint for file list
- HTML interface

---

## 10. API Integrations

### 10.1 Telegram APIs
| API | Purpose |
|-----|---------|
| User Client (Telethon) | Channel monitoring |
| Bot API (Telethon) | Commands & notifications |
| GMGN Bot | Trade execution |

### 10.2 Price Data APIs
| API | Purpose |
|-----|---------|
| DexScreener | Current token prices |
| GeckoTerminal | OHLCV candle data |

### 10.3 Database
| System | Purpose |
|--------|---------|
| PostgreSQL | Signal & PnL history |
| asyncpg | Async database driver |

---

## Feature Summary

| Category | Count |
|----------|-------|
| Trading Strategies | 13 |
| Telegram Commands | 20+ |
| Notification Types | 4 |
| PnL Analysis Modes | 3 |
| API Integrations | 5 |

---

*Last Updated: January 2026*
