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
- AI context workflow documentation for better agent collaboration
  - `.github/copilot-instructions.md` — GitHub Copilot instructions
  - `CLAUDE_CONTEXT.md` — Claude Code context file
  - `docs/ARCHITECTURE.md` — System architecture documentation
  - `docs/CONVENTIONS.md` — Code conventions and standards
  - `.vscode/claude-prompts.code-snippets` — VS Code prompt snippets

### Changed
<!-- Changes to existing functionality -->

### Fixed
<!-- Bug fixes -->

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
