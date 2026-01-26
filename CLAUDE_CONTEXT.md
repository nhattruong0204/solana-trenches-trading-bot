# Claude Code Context — READ FIRST

## Quick Reference
- Architecture: `/docs/ARCHITECTURE.md`
- Conventions: `/docs/CONVENTIONS.md`
- Recent changes: `/CHANGELOG.md`
- Features: `/FEATURES.md`

## Project Summary
**Solana Trenches Trading Bot** — Automated trading bot that monitors Telegram signals and executes trades on Solana via GMGN bot.

**Tech Stack:**
- Python 3.11+
- Telethon (Telegram client)
- Pydantic v2 (configuration)
- AsyncPG (PostgreSQL)
- pytest (testing)

## Critical Invariants

### 1. Core Models (DO NOT CHANGE signatures)
```python
# src/models.py
Position.to_dict() -> dict        # Serialization format frozen
Position.from_dict(data) -> Position
BuySignal                         # Fields: token_address, token_symbol, timestamp, message_id
ProfitAlert                       # Fields: multiplier, original_signal_id
TradeResult                       # Fields: success, tx_hash, error_message
```

### 2. Parser Protocol (DO NOT CHANGE signatures)
```python
# src/parsers.py
BuySignalParser.parse(message) -> BuySignal | None    # Never throws
ProfitAlertParser.parse(message) -> ProfitAlert | None # Never throws
```

### 3. Trader Protocol (DO NOT CHANGE signatures)
```python
# src/trader.py
GMGNTrader.buy_token(token_address, amount_sol) -> TradeResult
GMGNTrader.sell_token(token_address, percentage) -> TradeResult
```

### 4. State Management
```python
# src/state.py
TradingState.add_position(position)    # Thread-safe, async
TradingState.get_position(token)       # Returns Position | None
TradingState.update_position(token, updates)
TradingState.close_position(token)
```

### 5. Configuration (via Pydantic)
```python
# src/config.py
Settings.telegram -> TelegramSettings
Settings.trading -> TradingSettings
Settings.risk -> RiskSettings
Settings.channel -> ChannelSettings
```

## Module Map

| Module | Purpose | Can Modify? |
|--------|---------|-------------|
| `bot.py` | Main orchestrator | With caution |
| `trader.py` | Trade execution | Need approval |
| `parsers.py` | Signal detection | Pattern additions OK |
| `models.py` | Domain models | DO NOT CHANGE |
| `state.py` | Position persistence | With caution |
| `config.py` | Configuration | Add new settings OK |
| `constants.py` | Constants/patterns | Add new OK |
| `exceptions.py` | Exception hierarchy | Add new OK |
| `risk_manager.py` | Risk management | With caution |
| `strategies.py` | Take profit strategies | Add new OK |
| `notification_bot.py` | Admin bot | Commands/handlers OK |

## Current Sprint Focus
Check `/CHANGELOG.md` [Unreleased] section for:
- Features in progress
- Modules that are frozen
- Recent changes to be aware of

## Common Tasks

### Adding a New Signal Type
1. Add pattern to `src/constants.py`
2. Create parser class in `src/parsers.py`
3. Register in `MessageParser`
4. Add tests in `tests/test_parsers.py`

### Adding a New Strategy
1. Define in `src/strategies.py`
2. Add to `STRATEGIES` dict
3. Add tests in `tests/test_strategies.py`

### Adding Configuration
1. Add to appropriate Settings class in `src/config.py`
2. Add env var to `.env.example`
3. Document in relevant README

### Adding Admin Command
1. Add handler in `src/notification_bot.py`
2. Register with `@events.register`
3. Update `/help` command list

## Testing Commands
```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/test_parsers.py -v

# Run with coverage
pytest --cov=src --cov-report=term-missing
```

## DO NOT MODIFY (Frozen for stability)
- `Position` class serialization format
- Parser return types
- `GMGNTrader` interface
- Exception hierarchy base classes

## Session Checklist
Before implementing, confirm:
- [ ] Read `/docs/ARCHITECTURE.md` for this component
- [ ] Checked `/CHANGELOG.md` for recent changes
- [ ] Identified which modules need changes
- [ ] No signature changes to frozen interfaces
- [ ] Tests exist or will be added
