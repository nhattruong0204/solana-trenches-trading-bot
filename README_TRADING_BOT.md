# Solana Auto Trading Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-ready automated trading bot for Solana tokens based on Telegram signals from the "From The Trenches - VOLUME + SM" channel.

## Features

- 🚀 **Automated Trading**: Buy on signal detection, sell at configurable multiplier
- 🔒 **Safe by Default**: Dry-run mode enabled by default
- 📊 **Position Tracking**: Persistent state management with JSON storage
- 🐳 **Docker Ready**: Multi-stage Dockerfile for production deployment
- ✅ **Type-Safe**: Full type hints with Pydantic validation
- 🧪 **Well Tested**: Comprehensive test suite with pytest

## Strategy

| Action | Trigger |
|--------|---------|
| **BUY** | `// VOLUME + SM APE SIGNAL DETECTED 🧪` message |
| **SELL 50%** | `PROFIT ALERT 🚀` with `Multiplier: 2X+` |

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram account with channel access
- GMGN bot configured with your Solana wallet

### Installation

```bash
# Clone the repository
git clone https://github.com/nhattruong0204/solana-trenches-trading-bot.git
cd solana-trenches-trading-bot/trading_bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
nano .env  # Edit with your credentials
```

### Configuration

Edit `.env` with your settings:

```env
# Required
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash

# Trading (all optional with sensible defaults)
TRADING_DRY_RUN=true          # Set to 'false' for live trading
TRADING_BUY_AMOUNT_SOL=0.1    # SOL per buy
TRADING_SELL_PERCENTAGE=50    # % to sell at target
TRADING_MIN_MULTIPLIER=2.0    # Sell trigger (2X)
TRADING_MAX_POSITIONS=10      # Max concurrent positions
```

### Running

```bash
# Dry run mode (default - recommended for testing)
python main.py

# With verbose logging
python main.py --verbose

# Enable live trading (requires confirmation)
python main.py --live

# Custom buy amount
python main.py --buy-amount 0.5
```

## Project Structure

```
trading_bot/
├── src/                    # Main package
│   ├── __init__.py        # Package exports
│   ├── bot.py             # Main bot orchestrator
│   ├── cli.py             # Command-line interface
│   ├── config.py          # Pydantic settings
│   ├── constants.py       # Configuration constants
│   ├── exceptions.py      # Custom exceptions
│   ├── logging_config.py  # Logging setup
│   ├── models.py          # Data models
│   ├── parsers.py         # Message parsers
│   ├── state.py           # State management
│   └── trader.py          # Trade execution
├── tests/                  # Test suite
│   ├── conftest.py        # Test fixtures
│   ├── test_models.py
│   ├── test_parsers.py
│   ├── test_state.py
│   └── test_trader.py
├── main.py                 # Entry point
├── pyproject.toml         # Project configuration
├── requirements.txt       # Dependencies
├── Dockerfile             # Docker image
└── docker-compose.yml     # Docker orchestration
```

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

See [DOCKER_GUIDE.md](DOCKER_GUIDE.md) for detailed deployment instructions.

## CLI Reference

```
usage: trading-bot [-h] [-V] [-v] [-q] [--log-file FILE]
                   [--live] [--dry-run] [--buy-amount SOL]
                   [--sell-percentage PCT] [--min-multiplier X]
                   [--max-positions N] [--disabled]
                   [--state-file FILE] [--reset-state]
                   {status,validate} ...

Options:
  -V, --version          Show version
  -v, --verbose          Enable debug logging
  -q, --quiet            Suppress non-essential output
  --live                 Enable live trading
  --buy-amount SOL       SOL amount per signal
  --sell-percentage PCT  Percentage to sell (1-100)
  --min-multiplier X     Minimum multiplier for sell
  --max-positions N      Max concurrent positions

Commands:
  validate               Validate configuration
  status                 Show bot status
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html

# Type checking
mypy src

# Linting
ruff check src tests

# Formatting
black src tests
```

## Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TELEGRAM_API_ID` | *required* | Telegram API ID |
| `TELEGRAM_API_HASH` | *required* | Telegram API hash |
| `TELEGRAM_PHONE` | - | Phone for auth |
| `TRADING_ENABLED` | `true` | Master switch |
| `TRADING_DRY_RUN` | `true` | Simulation mode |
| `TRADING_BUY_AMOUNT_SOL` | `0.1` | SOL per buy |
| `TRADING_SELL_PERCENTAGE` | `50` | % to sell |
| `TRADING_MIN_MULTIPLIER` | `2.0` | Sell trigger |
| `TRADING_MAX_POSITIONS` | `10` | Max positions |
| `SIGNAL_CHANNEL` | `fttrenches_volsm` | Channel username |
| `GMGN_BOT` | `GMGN_sol_bot` | Bot username |

## Safety Notes

⚠️ **IMPORTANT WARNINGS**

1. **Start with DRY_RUN=true** - Always test before live trading
2. **Only trade what you can afford to lose** - This is experimental software
3. **Monitor the bot** - Don't leave it unattended for extended periods
4. **GMGN bot must be pre-configured** - Set up your wallet first
5. **Keep your API credentials secure** - Never commit `.env` to git

## License

MIT License - See [LICENSE](../LICENSE) for details.

## Disclaimer

This software is provided "as is" without warranty of any kind. Trading cryptocurrencies carries significant risk. You may lose some or all of your investment. The authors are not responsible for any financial losses incurred from using this software.

**NEVER invest more than you can afford to lose.**
