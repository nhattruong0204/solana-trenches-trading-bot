# Changelog

All notable changes to the Solana Trenches Trading Bot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### In Progress
<!-- Add features currently being worked on here -->
<!-- Example:
- Wallet tracking (Claude session 01/26) — `src/signals/wallet_tracker.py`
  - Status: WebSocket connection done, alert formatting TODO
  - DO NOT TOUCH: `process_wallet_event()` signature finalized
-->

### Added
- **Multi-Channel Monitoring Support**
  - New channel registry in `src/constants.py`: `CHANNEL_VOLSM`, `CHANNEL_MAIN` identifiers
  - New MAIN channel constants: `TRENCHES_MAIN_CHANNEL_USERNAME`, `TRENCHES_MAIN_CHANNEL_NAME`
  - New signal indicators: `MAIN_BUY_SIGNAL_INDICATORS`, `MAIN_PROFIT_ALERT_INDICATORS`
  - `MonitoredChannelConfig` dataclass in `src/config.py` for channel-specific settings
  - `ChannelSettings.monitored_channels` property builds channel list from env vars
  - Environment variables: `MAIN_CHANNEL_ENABLED`, `MAIN_CHANNEL_TRADING` (default: False)
  - `ParserRegistry` class in `src/parsers.py` maps channels to channel-specific parsers
  - `MainChannelBuySignalParser` and `MainChannelProfitAlertParser` for MAIN channel format
  - `ChannelMessageParser` for channel-aware message parsing
  - `MessageParser` now accepts optional `channel_id` parameter for channel-specific parsing
  - Multi-channel support in `bot.py`:
    - `_channel_entities` dict stores all monitored channel entities
    - `_monitored_configs` maps Telegram channel IDs to config objects
    - `_init_channel()` now resolves all enabled channels
    - Event handler listens to all monitored channels
    - Messages routed to channel-specific parsers
    - Commercial mirroring only for channels with `commercial_mirroring=True` (default: VOLSM only)
    - Trading can be enabled/disabled per channel
  - `SignalDatabase.CHANNEL_DISPLAY_NAMES` mapping and `_get_channel_display_name()` helper
  - `insert_signal()` now accepts optional `channel_name` parameter
  - `record_signal()` and `record_profit_alert()` in notification_bot accept `channel_name`
  - Updated startup banner to show all monitored channels with status icons
  - Plan document: `docs/PLAN_MULTI_CHANNEL.md`

- AI context workflow documentation for better agent collaboration
  - `.github/copilot-instructions.md` — GitHub Copilot instructions
  - `CLAUDE_CONTEXT.md` — Claude Code context file
  - `docs/ARCHITECTURE.md` — System architecture documentation
  - `docs/CONVENTIONS.md` — Code conventions and standards
  - `.vscode/claude-prompts.code-snippets` — VS Code prompt snippets
- Deleted signal detection for `/signalpnl` and `/realpnl` commands
  - New `_check_deleted_messages()` helper method to check if signals still exist in channel
  - Deleted signals are marked with strikethrough text (~$TOKEN~) and 🗑️ emoji
  - Summary message now shows count of signals deleted by channel owner
  - Helps track how many signals were removed (potential rugs/scams)
  - Location: `src/notification_bot.py:280-340` (new method), lines 1455-1460, 1610-1618 (signalpnl), 
    lines 1700-1705, 1865-1873 (realpnl)
- **Commercial Channel Mirroring (SolSleuth Premium & Signals)**
  - Premium channel (SolSleuth Premium) now mirrors ALL messages from source channel exactly
  - New `mirror_message()` method in `SignalPublisher` and `CommercialBot` for raw message forwarding
  - Public channel (SolSleuth Signals) forwards winning signals (2X+) with original message + CTA
  - Profit alerts are tracked and trigger Public channel forwarding on first 2X+ milestone
  - `SignalMapping` dataclass now stores `raw_message` for accurate public channel forwarding
  - Location: `src/signal_publisher.py:220-300` (mirror_message), `src/commercial_bot.py:222-275`,
    `src/bot.py:454-470` (mirroring in message handler)

### Changed
- `MessageParser.__init__()` now optionally accepts `channel_id` for channel-specific parsing
- `_handle_buy_signal()` accepts `channel_id` and `trading_enabled` parameters
- `_handle_profit_alert()` accepts `channel_id` parameter
- Updated `_on_new_message()` in `bot.py` to mirror ALL messages to Premium channel (not just parsed signals)
- `send_profit_update()` now only tracks milestones and triggers Public channel forwarding (Premium already mirrored)
- `_forward_win_to_public()` now uses raw messages when available, with CTA appended separately

### Fixed
- **CRITICAL: Missing methods after PR #6 merge caused bot commands to fail**
  - `/syncsignals`, `/realpnl`, `/signalpnl` commands all crashed with AttributeError
  - Root cause: PR #6 merge lost `_ensure_trading_client_connected()` and `_check_deleted_messages()` methods
  - Fix: Re-added both methods to `src/notification_bot.py` (lines 254-340)
  - Both methods were originally added in commit 7c8b9e9 and 7106535 but lost during merge
- `/syncsignals` and `/bootstrap` commands failing with "Cannot send requests while disconnected"
  - Root cause: Code only checked if Telegram client object existed, not if it was connected
  - Fix: Added `_ensure_trading_client_connected()` helper that checks connection state
    and attempts automatic reconnection before fetching messages
  - Location: `src/notification_bot.py:254-287` (method definition)
  - Tests: Added 7 regression tests in `tests/test_notification_bot.py::TestEnsureTradingClientConnected`

### Deprecated
<!-- Features that will be removed in future versions -->

### Removed
<!-- Features removed in this version -->

### Security
<!-- Security fixes or improvements -->

---

## [1.0.0] - 2025-01-25

### Added
- Initial release of Solana Trenches Trading Bot
- Core trading engine with GMGN bot integration
- Signal parsing for buy signals and profit alerts
- Position state management with JSON persistence
- Risk management system
  - Fixed percentage stop loss
  - Trailing stop loss
  - Time-based stops
  - Dynamic position sizing
  - Circuit breaker for loss limits
- Admin Telegram bot with commands:
  - `/status`, `/positions`, `/settings`, `/stats`
  - `/setsize`, `/setsell`, `/setmultiplier`, `/setmax`
  - `/pause`, `/resume`, `/setwallet`
- Take profit strategies
  - Trailing stop strategies (15%, 20%, 25%, 30%)
  - Fixed exit strategies (1.5X to 5X)
  - Tiered exit strategies
- Backtesting and strategy simulation
- Signal database integration (PostgreSQL)
- Public channel broadcasting for marketing
- Premium subscription system
- KOL/whale tracking integration
- Docker deployment support
- Comprehensive documentation

### Technical Details
- Python 3.11+ with asyncio
- Telethon for Telegram integration
- Pydantic v2 for configuration
- AsyncPG for PostgreSQL
- pytest for testing (52 tests passing)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 1.0.0 | 2025-01-25 | Initial release |

---

## Contributing

When making changes:
1. Update the [Unreleased] section with your changes
2. Use the appropriate category (Added, Changed, Fixed, etc.)
3. Include relevant file paths for complex changes
4. Mark work-in-progress items clearly

### Categories

- **Added** — New features
- **Changed** — Changes to existing functionality
- **Deprecated** — Features that will be removed
- **Removed** — Features removed
- **Fixed** — Bug fixes
- **Security** — Security improvements

### In Progress Format

For work-in-progress items, use this format:
```markdown
- Feature name (session date) — `path/to/file.py`
  - Status: What's done, what's TODO
  - DO NOT TOUCH: Any frozen code
```
