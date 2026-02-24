# Telegram Alpha Radar — Agent Onboarding Memory

> **Read this first** before modifying any code in `telegram_alpha_radar/`.
> This document captures architectural decisions, invariants, and tribal knowledge
> so that any new AI agent (or human) can work on this module safely.

---

## Project Identity

| Field | Value |
|-------|-------|
| **Module** | `telegram_alpha_radar/` |
| **Version** | 2.0.0 |
| **Purpose** | Monitor all Telegram messages, detect token contracts (Solana + EVM), track trending tokens, send alerts |
| **Parent repo** | `solana-trenches-trading-bot` |
| **Entry point** | `python -m telegram_alpha_radar.app` |
| **Python** | 3.11+ |
| **Async framework** | asyncio (no threads, no blocking calls) |

---

## Architecture Overview

```
Telegram messages (Telethon MTProto user session)
        │
        ▼
  TelegramListener  ─────  Filters (length, forwarded)
        │
        ▼
  Detector Registry  ─────  SolanaDetector, EvmDetector, ...
        │
        ▼
  PostgresRepository ─────  Dedup on (contract, chat_id, message_id)
        │
        ▼
  TrendingEngine     ─────  Window aggregation + velocity scoring
        │
        ▼
  TelegramNotifier   ─────  Alerts to Saved Messages (with cooldown)
```

### Module Map

| Module | Location | Purpose | Safe to modify? |
|--------|----------|---------|-----------------|
| `app.py` | root | Orchestrator, CLI, signal handlers | With caution |
| `config.py` | root | All environment-based configuration | Add new settings OK |
| `core/models.py` | core/ | Domain models (TokenMatch, TrendingToken) | **DO NOT change field names** |
| `core/types.py` | core/ | Chain enum, DetectorRegistry type | Add new chains OK |
| `core/utils.py` | core/ | Logging, UTC helpers | Add new utils OK |
| `detectors/base_detector.py` | detectors/ | ABC for all detectors | **DO NOT change signature** |
| `detectors/solana_detector.py` | detectors/ | Solana Base58 detection | Patterns OK, interface frozen |
| `detectors/evm_detector.py` | detectors/ | EVM 0x detection | Patterns OK, interface frozen |
| `listener/telegram_listener.py` | listener/ | Telethon event handling | With caution |
| `storage/base_repository.py` | storage/ | ABC for storage backends | **DO NOT change signature** |
| `storage/postgres_repository.py` | storage/ | asyncpg implementation | SQL changes need migration |
| `trending/trending_engine.py` | trending/ | Scoring + Dexscreener filter | Scoring formula OK to tune |
| `notifier/telegram_notifier.py` | notifier/ | Alert formatting + cooldown | Format OK, cooldown logic caution |

---

## Critical Invariants (DO NOT BREAK)

### 1. BaseDetector interface

```python
class BaseDetector(ABC):
    @property
    def chain_name(self) -> str: ...
    async def detect(self, message: str, chat_id: int, message_id: int) -> list[TokenMatch]: ...
```

All detectors must return `list[TokenMatch]`. The listener iterates all registered detectors.
**Never** change the `detect()` signature — every detector in the registry depends on it.

### 2. BaseRepository interface

```python
class BaseRepository(ABC):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def is_connected(self) -> bool: ...
    async def record_mention(self, match: TokenMatch) -> bool: ...
    async def get_trending(self, *, since, min_mentions, min_unique_chats, chain=None) -> list[TrendingToken]: ...
    async def get_mention_count(self, contract, since, until) -> int: ...
    async def cleanup_old_mentions(self, before) -> int: ...
```

If you add a new storage backend (Redis, SQLite), implement this ABC.

### 3. TokenMatch model (frozen dataclass)

```python
TokenMatch(contract: str, chain: str, chat_id: int, message_id: int, timestamp: datetime)
```

This is the universal currency between detectors and storage. **Do not rename fields.**

### 4. Scoring formula

```python
score = mentions * 2 + unique_chats * 3 + velocity * 5
```

Defined in `TrendingToken.compute_score()`. If you change this, update:
- `core/models.py` — the method
- `README.md` — documented formula
- `CHANGELOG.md` — record the change

### 5. Database schema deduplication

```sql
UNIQUE (contract, chat_id, message_id)
```

This constraint is the dedup mechanism. Changing it will cause duplicate alerts.

---

## Common Tasks

### Adding a New Chain Detector

1. Create `detectors/mychain_detector.py` — subclass `BaseDetector`
2. Add chain to `core/types.py` → `Chain` enum
3. Register in `app.py` → `self._detectors` list
4. Add unit tests in `tests/test_detectors.py`
5. Update `CHANGELOG.md`

### Adding a New Storage Backend

1. Create `storage/redis_repository.py` — subclass `BaseRepository`
2. Add config class in `config.py`
3. Swap in `app.py` constructor
4. No schema.sql needed for Redis

### Tuning Trending Thresholds

All thresholds are in `.env` / `config.py`:
- `TRENDING_WINDOW_MINUTES` — detection time window (default: 5)
- `TRENDING_MIN_MENTIONS` — minimum mentions to trigger (default: 3)
- `TRENDING_MIN_UNIQUE_CHATS` — minimum distinct chats (default: 2)
- `TRENDING_COOLDOWN_MINUTES` — alert cooldown per contract (default: 15)

### Adding False-Positive Filters

- Solana: Edit `_FALSE_POSITIVE_WORDS` or `_SYSTEM_ADDRESSES` in `solana_detector.py`
- EVM: Edit `_BLACKLISTED_ADDRESSES` in `evm_detector.py`

### Changing Alert Format

Edit `TelegramNotifier._format_alert()` in `notifier/telegram_notifier.py`.
Alerts go to Telegram "Saved Messages" (self-chat).

---

## Environment & Configuration

All config flows through `config.py` using `@dataclass(frozen=True)` classes.
Every setting reads from environment variables with sensible defaults.

**Required** (no defaults):
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_PHONE`
- `DB_PASSWORD`

**Optional** (have defaults): everything else. See `.env.example` for full list.

---

## Production Details

| Aspect | Detail |
|--------|--------|
| **Health check** | `GET /health` on port 8080 |
| **Prometheus** | `GET /metrics` on port 9090 (when `METRICS_ENABLED=true`) |
| **Graceful shutdown** | SIGINT/SIGTERM → cancels all tasks → closes DB pool → disconnects Telethon |
| **Reconnect** | Telethon auto-reconnect with 10 retries, 5s delay |
| **Flood wait** | Caught and slept automatically |
| **DB cleanup** | Background loop deletes mentions older than 24h (every 1h) |
| **Cooldown cleanup** | Expired cooldowns pruned after each trending check |

---

## Testing

```bash
pytest tests/test_detectors.py -v
```

Tests cover:
- Valid address detection (Solana + EVM)
- False-positive rejection (common words, system addresses, zero/dead addresses)
- Deduplication within same message
- Case normalization (EVM)
- Mixed-chain message handling
- Edge cases (empty messages, short strings)

---

## Known Decisions & Trade-offs

1. **User session, not Bot API** — We use Telethon with a real phone number so we can monitor ALL incoming messages (groups, channels, private). Bot API can only see messages sent to the bot.

2. **In-memory cooldowns** — Alert cooldowns are stored in a Python dict, not in PostgreSQL. This means cooldowns reset on restart. Acceptable because the worst case is a duplicate alert after restart.

3. **Fail-open Dexscreener** — If the Dexscreener API is down or returns an error, we pass the token through (don't filter it out). Better to alert on a low-liquidity token than miss a real trending one.

4. **No blocking calls** — Every I/O operation is async. Do NOT use `time.sleep()`, `requests.get()`, or any synchronous library. Use `asyncio.sleep()`, `aiohttp`, `asyncpg`.

5. **Single asyncio event loop** — Everything runs on one loop. No threads, no `run_in_executor()` unless absolutely necessary for CPU-bound work.

---

## Files You Should NOT Touch Without Good Reason

- `detectors/base_detector.py` — ABC interface is frozen
- `storage/base_repository.py` — ABC interface is frozen
- `core/models.py` — Field names are frozen (DB schema depends on them)
- `schema.sql` — Changing the UNIQUE constraint breaks dedup

---

## Session Checklist

Before making changes:
- [ ] Read this file completely
- [ ] Check `CHANGELOG.md` for recent changes
- [ ] Identify which modules need changes (see Module Map above)
- [ ] Confirm no frozen interfaces are being modified
- [ ] Write or update tests
- [ ] Update `CHANGELOG.md` with your changes
