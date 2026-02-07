# Solana Auto Trading Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-52%20passed-success.svg)](tests/)

A production-ready automated trading bot for Solana tokens based on Telegram signals from the "From The Trenches - VOLUME + SM" channel.

## Features

- 🚀 **Automated Trading**: Buy on signal detection, sell at configurable multiplier
- 🔒 **Safe by Default**: Dry-run mode enabled by default
- 📊 **Position Tracking**: Persistent state management with JSON storage
- 🐳 **Docker Ready**: Multi-stage Dockerfile for production deployment
- ✅ **Type-Safe**: Full type hints with Pydantic validation
- 🧪 **Well Tested**: Comprehensive test suite with 52 passing tests

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your Telegram credentials

# Run in dry-run mode
python main.py

# Run with live trading (requires confirmation)
python main.py --live
```

## Documentation

### For Users
- [README_TRADING_BOT.md](README_TRADING_BOT.md) - Full trading bot documentation
- [FEATURES.md](FEATURES.md) - Complete feature reference
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [WALKTHROUGH.md](WALKTHROUGH.md) - Step-by-step walkthrough

### For Developers
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture and components
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) - Code style and conventions

### For Building Telegram Bots
- [docs/COPILOT_TELEGRAM_QUICK_START.md](docs/COPILOT_TELEGRAM_QUICK_START.md) - Quick start for Copilot agents
- [docs/TELEGRAM_BOT_GUIDE.md](docs/TELEGRAM_BOT_GUIDE.md) - Comprehensive Telegram bot patterns

These guides document the Telegram bot patterns used in this repository and help developers (including Copilot agents) replicate similar functionality.
