# Telegram Alpha Radar — Changelog

All notable changes to the Alpha Radar module will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### In Progress
<!-- Add features currently being worked on here -->
<!-- Format:
- Feature name (session date) — `path/to/file.py`
  - Status: What's done, what's TODO
  - DO NOT TOUCH: Any frozen code
-->

---

## [2.0.0] - 2026-02-24

### Added — Modular Multi-Chain Architecture

Complete architectural redesign from flat module structure to clean, extensible architecture.

#### Core Layer (`core/`)
- `models.py` — Domain models: `TokenMatch`, `TrendingToken`, `MentionRecord`, `HealthStatus`
- `types.py` — `Chain` enum (SOLANA, EVM), `DetectorRegistry` type alias
- `utils.py` — `setup_logging()` with JSON format support, `utcnow()`, `truncate()`

#### Pluggable Detector System (`detectors/`)
- `base_detector.py` — Abstract base class with `detect()` and `chain_name` interface
- `solana_detector.py` — Base58 detection (32-44 chars), false-positive word list, system address filter, mixed-case heuristic
- `evm_detector.py` — 0x+40hex detection, lowercase normalization, blacklisted address filter (zero, dead, 0xfff...)

#### Telegram Listener (`listener/`)
- `telegram_listener.py` — Telethon MTProto user session, auto-reconnect (10 retries, 5s delay), FloodWaitError handling, message filtering (length, forwarded)

#### Storage Layer (`storage/`)
- `base_repository.py` — Abstract repository interface (connect, close, record_mention, get_trending, get_mention_count, cleanup)
- `postgres_repository.py` — asyncpg implementation with connection pooling, auto-schema creation, dedup via `UNIQUE (contract, chat_id, message_id)`, optimized indexes

#### Trending Engine (`trending/`)
- `trending_engine.py` — Configurable window/threshold detection, velocity scoring (`(current - previous) / previous`), final score formula: `mentions * 2 + unique_chats * 3 + velocity * 5`, per-chain independent ranking, optional Dexscreener liquidity filter (fail-open)

#### Notification System (`notifier/`)
- `telegram_notifier.py` — Formatted alerts to Saved Messages, per-contract cooldown window, dry-run mode support, expired cooldown cleanup

#### Application Entry Point
- `app.py` — Full orchestrator wiring all components, CLI flags (`--debug`, `--dry-run`), SIGINT/SIGTERM graceful shutdown, background trending loop, background DB cleanup loop (24h retention), Prometheus metrics (Counter: messages, mentions, alerts; Gauge: trending count), health check HTTP endpoint (`/health` on port 8080)
- `__main__.py` — Enables `python -m telegram_alpha_radar`

#### Configuration (`config.py`)
- 8 frozen dataclass configs: `TelegramConfig`, `DatabaseConfig`, `TrendingConfig`, `FilterConfig`, `DexscreenerConfig`, `MetricsConfig`, `HealthConfig`, `AppConfig`
- All values from environment variables with sensible defaults
- Startup validation with clear error messages

#### Production Files
- `schema.sql` — Full PostgreSQL initialization (contract_mentions + alert_history tables, 4 indexes)
- `requirements.txt` — telethon, asyncpg, aiohttp, python-dotenv, prometheus-client, pytest, pytest-asyncio
- `Dockerfile` — Python 3.12-slim, non-root user, exposes 8080 + 9090
- `.env.example` — 30+ documented configuration variables
- `README.md` — Architecture diagram, quick start, VPS deployment, Docker deployment, adding new chains guide, full config reference

#### Tests
- `tests/test_detectors.py` — 18 unit tests covering: valid detection, false-positive rejection, dedup, normalization, cross-chain handling, edge cases

### Changed
- Replaced flat module structure (`parser.py`, `storage.py`, `trending.py`, `listener.py`, `notifier.py`) with package-based architecture
- Scoring formula changed from `mention_count * unique_chats * (1 + velocity_ratio)` to `mentions * 2 + unique_chats * 3 + velocity * 5`
- Config variable names standardized with prefixes (`TRENDING_`, `FILTER_`, `DB_POOL_`, `DEXSCREENER_`)

### Removed
- `parser.py` — Replaced by `detectors/solana_detector.py` + `detectors/evm_detector.py`
- `storage.py` — Replaced by `storage/base_repository.py` + `storage/postgres_repository.py`
- `trending.py` — Replaced by `trending/trending_engine.py`
- `listener.py` — Replaced by `listener/telegram_listener.py`
- `notifier.py` — Replaced by `notifier/telegram_notifier.py`

---

## [1.0.0] - 2026-02-23

### Added
- Initial implementation of Telegram Alpha Radar
- Telegram MTProto listener using Telethon user session
- Contract detection: Solana (Base58) + EVM (0x hex)
- PostgreSQL storage with asyncpg and deduplication
- Trending detection with configurable time windows and thresholds
- Alert notifications to Telegram Saved Messages with cooldown
- Optional Dexscreener liquidity validation
- Optional Prometheus metrics endpoint
- Graceful shutdown with signal handlers
- Docker support
- Environment-based configuration via dataclasses

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.0.0 | 2026-02-24 | Modular multi-chain architecture redesign |
| 1.0.0 | 2026-02-23 | Initial release |

---

## How to Update This File

When making changes to the Alpha Radar:

1. Add your entry under `[Unreleased]` in the appropriate category
2. Include file paths for significant changes
3. Use imperative mood ("Add feature" not "Added feature") for unreleased items
4. When releasing, move unreleased items to a new version header

### Categories
- **Added** — New features or files
- **Changed** — Changes to existing functionality
- **Fixed** — Bug fixes
- **Removed** — Deleted features or files
- **Security** — Security-related changes

### In Progress Format
```markdown
- Feature name (session date) — `path/to/file.py`
  - Status: What's done, what's TODO
  - DO NOT TOUCH: Any frozen code/interfaces
```
