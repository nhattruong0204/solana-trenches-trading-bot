"""
Application constants and magic values.

This module centralizes all hardcoded values to make them
easily discoverable and modifiable.
"""

from typing import Final

# ==============================================================================
# Channel Identifiers (used as keys in registries)
# ==============================================================================

CHANNEL_VOLSM: Final[str] = "volsm"
CHANNEL_MAIN: Final[str] = "main"

# ==============================================================================
# Telegram Channel Configuration - VOLUME + SM
# ==============================================================================

TRENCHES_CHANNEL_USERNAME: Final[str] = "fttrenches_volsm"
TRENCHES_CHANNEL_NAME: Final[str] = "From The Trenches - VOLUME + SM"

# ==============================================================================
# Telegram Channel Configuration - MAIN
# ==============================================================================

TRENCHES_MAIN_CHANNEL_USERNAME: Final[str] = "fttrenches_sol"
TRENCHES_MAIN_CHANNEL_NAME: Final[str] = "From The Trenches - MAIN"

# GMGN Bot Configuration
GMGN_BOT_USERNAME: Final[str] = "GMGN_sol_bot"

# ==============================================================================
# Signal Detection Patterns - VOLUME + SM Channel
# ==============================================================================

# Buy signal indicators (VOLUME + SM format)
BUY_SIGNAL_INDICATORS: Final[tuple[str, ...]] = (
    "// VOLUME + SM APE SIGNAL DETECTED",
    "`// VOLUME + SM APE SIGNAL DETECTED`",
)

# Profit alert indicators (shared across channels)
PROFIT_ALERT_INDICATORS: Final[tuple[str, ...]] = (
    "PROFIT ALERT",
    "`PROFIT ALERT`",
)

# ==============================================================================
# Signal Detection Patterns - MAIN Channel
# ==============================================================================

# Buy signal indicators (MAIN channel format)
# Includes both NEW-LAUNCH and MID-SIZED signals as "ape" signals
MAIN_BUY_SIGNAL_INDICATORS: Final[tuple[str, ...]] = (
    "🚀 **NEW-LAUNCH SIGNAL**",
    "NEW-LAUNCH SIGNAL",
    "// MID-SIZED SIGNAL DETECTED",
    "`// MID-SIZED SIGNAL DETECTED`",
    "MID-SIZED SIGNAL DETECTED",
)

# MAIN channel profit alert format
MAIN_PROFIT_ALERT_INDICATORS: Final[tuple[str, ...]] = (
    "`PROFIT ALERT` 🚀",
    "PROFIT ALERT` 🚀",
    "`PROFIT ALERT`",
    "PROFIT ALERT",
)

# ==============================================================================
# Regex Patterns
# ==============================================================================

# Token symbol extraction pattern (matches: "Token: - $SYMBOL" or "Token: $SYMBOL")
TOKEN_SYMBOL_PATTERN: Final[str] = r'Token:\s*-?\s*\$(\w+)'

# Solana address extraction pattern (base58, 32-44 chars)
# Matches addresses preceded by backticks or tree characters
TOKEN_ADDRESS_PATTERN: Final[str] = r'[`├└]\s*([1-9A-HJ-NP-Za-km-z]{32,44})'

# Multiplier extraction pattern (matches: "2.5X", "**3X**", etc.)
MULTIPLIER_PATTERN: Final[str] = r'\*?\*?([\d.]+)\s*X\*?\*?'

# ==============================================================================
# File Paths
# ==============================================================================

DEFAULT_STATE_FILE: Final[str] = "trading_state.json"
DEFAULT_LOG_FILE: Final[str] = "trading_bot.log"
DEFAULT_SESSION_FILE: Final[str] = "wallet_tracker_session"

# ==============================================================================
# Trading Defaults
# ==============================================================================

DEFAULT_BUY_AMOUNT_SOL: Final[float] = 0.1
DEFAULT_SELL_PERCENTAGE: Final[int] = 50
DEFAULT_MIN_MULTIPLIER: Final[float] = 2.0
DEFAULT_MAX_POSITIONS: Final[int] = 10

# ==============================================================================
# Timeouts and Retry Configuration
# ==============================================================================

TELEGRAM_CONNECT_TIMEOUT: Final[int] = 30  # seconds
BOT_ENTITY_TIMEOUT: Final[int] = 10  # seconds
MESSAGE_SEND_TIMEOUT: Final[int] = 10  # seconds
RETRY_ATTEMPTS: Final[int] = 3
RETRY_BACKOFF_FACTOR: Final[float] = 1.5

# ==============================================================================
# Logging Configuration
# ==============================================================================

LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT: Final[int] = 5
