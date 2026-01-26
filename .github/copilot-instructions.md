# Copilot Instructions for Solana Trenches Trading Bot

## MANDATORY: Before ANY code changes
1. Check `/docs/ARCHITECTURE.md` for component responsibilities
2. Check `/docs/CONVENTIONS.md` for patterns and rules
3. Check recent entries in `/CHANGELOG.md`

## Project Overview
An automated trading bot that monitors Telegram channel "From The Trenches - VOLUME + SM" for buy signals and executes trades on Solana via GMGN bot.

## RULES (non-negotiable)
- Never modify function signatures in `src/models.py` or `src/exceptions.py` without explicit approval
- All new features must be configurable via environment variables (see `src/config.py`)
- Every external call needs retry logic + logging
- No hardcoded values — use `src/constants.py` or environment variables
- All async operations must use proper error handling
- Configuration validation through Pydantic only

## Project Structure
```
src/
├── bot.py              — Main trading bot orchestrator
├── trader.py           — GMGN bot trade execution interface
├── parsers.py          — Signal detection from Telegram messages
├── models.py           — Domain models (Position, BuySignal, ProfitAlert)
├── state.py            — Position state persistence (JSON)
├── config.py           — Pydantic settings management
├── constants.py        — Magic strings, patterns, defaults
├── exceptions.py       — Custom exception hierarchy
├── risk_manager.py     — Stop loss, position sizing, circuit breaker
├── controller.py       — Remote Telegram control
├── notification_bot.py — Admin Telegram bot (commands/menus)
├── strategies.py       — Take profit strategy definitions
├── strategy_simulator.py — Backtesting & simulation
├── signal_database.py  — PostgreSQL signal history
├── signal_history.py   — Local signal tracking
├── signal_publisher.py — Public channel broadcasting
├── commercial_bot.py   — Premium features integration
├── subscription_manager.py — Subscription management
└── cli.py              — Command-line interface
```

## Module Responsibilities

### Core Trading (DO NOT MODIFY signatures without approval)
- `TradingBot` in `bot.py` — Main orchestrator, ties everything together
- `GMGNTrader` in `trader.py` — Trade execution abstraction
- `Position` in `models.py` — Core domain model for trades
- `TradingState` in `state.py` — Position persistence layer

### Signal Processing
- `BuySignalParser`, `ProfitAlertParser` in `parsers.py` — Parse Telegram messages
- `MessageParser` — Composite parser that tries all parsers
- Pattern matching uses constants from `constants.py`

### Risk Management
- `RiskManager` in `risk_manager.py` — Stop loss, sizing, circuit breaker
- `StopLossConfig`, `PositionSizingConfig`, `CircuitBreakerConfig` — Configuration classes

### Configuration
- `Settings` in `config.py` — Main settings with nested objects
- `TelegramSettings`, `TradingSettings`, `RiskSettings`, etc.
- Always use `@lru_cache` for settings singleton

## Current Active Work
Check `/CHANGELOG.md` [Unreleased] section for work in progress

## Critical Invariants
1. `Position.to_dict()` / `Position.from_dict()` — Serialization format frozen
2. `BuySignalParser.parse()` — Returns `BuySignal | None`, never throws
3. `ProfitAlertParser.parse()` — Returns `ProfitAlert | None`, never throws
4. `TradingState` — Thread-safe async operations required
5. All Telegram operations via Telethon client only

## Testing Requirements
- `tests/` — All tests must pass before merge
- Use `pytest -v` to run tests
- Fixtures in `tests/conftest.py`
- Mock external dependencies (Telegram, GMGN)

## Code Style
- Black formatter (100 char line length)
- Ruff linter enabled
- Strict mypy type checking
- Docstrings for all public APIs
- Type hints required for all functions

## Environment Variables
- See `.env.example` for all configuration options
- Never commit `.env` or credentials
- Use Pydantic for validation
