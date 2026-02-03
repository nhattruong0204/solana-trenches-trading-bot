"""Constants and configuration values for the token analysis bot."""

from enum import Enum
from typing import Final

# =============================================================================
# Chain Configuration
# =============================================================================

# Base Chain DEX Factory Addresses (for PairCreated events)
UNISWAP_V2_FACTORY: Final[str] = "0x8909Dc15e40173Ff4699343b6eB8132c65e18eC6"
UNISWAP_V3_FACTORY: Final[str] = "0x33128a8fC17869897dcE68Ed026d694621f6FDfD"
AERODROME_FACTORY: Final[str] = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
SUSHISWAP_FACTORY: Final[str] = "0x71524B4f93c58fcbF659783284E38825f0622859"

# Standard ERC20 ABI for token info
ERC20_ABI: Final[list] = [
    {"inputs": [], "name": "name", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalSupply", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "owner", "outputs": [{"type": "address"}], "stateMutability": "view", "type": "function"},
]

# PairCreated event ABI
PAIR_CREATED_ABI: Final[dict] = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "token0", "type": "address"},
        {"indexed": True, "name": "token1", "type": "address"},
        {"indexed": False, "name": "pair", "type": "address"},
        {"indexed": False, "name": "allPairsLength", "type": "uint256"},
    ],
    "name": "PairCreated",
    "type": "event",
}

# Known stablecoins and wrapped tokens (Base)
WETH_BASE: Final[str] = "0x4200000000000000000000000000000000000006"
USDC_BASE: Final[str] = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDT_BASE: Final[str] = "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"
DAI_BASE: Final[str] = "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb"

STABLECOINS: Final[set] = {USDC_BASE, USDT_BASE, DAI_BASE}
QUOTE_TOKENS: Final[set] = {WETH_BASE, USDC_BASE}


# =============================================================================
# Risk Rating Configuration
# =============================================================================

class RiskRating(str, Enum):
    """Token risk rating levels."""
    GREEN = "green"    # Low risk - strong fundamentals
    YELLOW = "yellow"  # Moderate concerns - proceed with caution
    ORANGE = "orange"  # High risk - early/thin liquidity
    RED = "red"        # Clear red flags - avoid

    @property
    def emoji(self) -> str:
        return {
            RiskRating.GREEN: "\U0001F7E9",   # Green square
            RiskRating.YELLOW: "\U0001F7E8",  # Yellow square
            RiskRating.ORANGE: "\U0001F7E7",  # Orange square
            RiskRating.RED: "\U0001F7E5",     # Red square
        }[self]


# Risk thresholds
MIN_LIQUIDITY_FOR_GREEN: Final[float] = 50000.0  # USD
MIN_LIQUIDITY_FOR_YELLOW: Final[float] = 10000.0
MIN_LIQUIDITY_FOR_ORANGE: Final[float] = 5000.0

MAX_TOP_HOLDER_PCT_GREEN: Final[float] = 10.0
MAX_TOP_HOLDER_PCT_YELLOW: Final[float] = 20.0
MAX_TOP_HOLDER_PCT_ORANGE: Final[float] = 30.0

MIN_HOLDERS_GREEN: Final[int] = 200
MIN_HOLDERS_YELLOW: Final[int] = 100
MIN_HOLDERS_ORANGE: Final[int] = 50


# =============================================================================
# Analysis Configuration
# =============================================================================

# Smart wallet databases/indicators
SMART_WALLET_LABELS: Final[list] = [
    "smart_money",
    "whale",
    "kol",
    "fund",
    "insider",
    "degen",
]

# Known scam patterns
HONEYPOT_INDICATORS: Final[list] = [
    "cannot_sell",
    "high_tax",
    "blacklist_function",
    "hidden_owner",
    "proxy_contract",
    "self_destruct",
]

# Dev reputation red flags
DEV_RED_FLAGS: Final[list] = [
    "prior_rug",
    "fake_followers",
    "new_account",
    "no_verification",
    "copied_project",
    "anonymous_team",
]


# =============================================================================
# API Rate Limits
# =============================================================================

DEXSCREENER_RATE_LIMIT: Final[int] = 300  # requests per minute
TWITTER_RATE_LIMIT: Final[int] = 300  # requests per 15 min window
BASESCAN_RATE_LIMIT: Final[int] = 5  # requests per second (free tier)


# =============================================================================
# Retry Configuration
# =============================================================================

MAX_RETRIES: Final[int] = 3
RETRY_BACKOFF_BASE: Final[float] = 2.0  # seconds
RETRY_BACKOFF_MAX: Final[float] = 30.0  # seconds


# =============================================================================
# Confidence Levels
# =============================================================================

class ConfidenceLevel(str, Enum):
    """Confidence level for claims/data."""
    VERIFIED = "verified"      # Cross-referenced from multiple sources
    HIGH = "high"              # Single reliable source
    MEDIUM = "medium"          # Inferred or partially verified
    LOW = "low"                # Speculation or unverified
    UNVERIFIED = "unverified"  # No verification possible


CONFIDENCE_THRESHOLDS: Final[dict] = {
    ConfidenceLevel.VERIFIED: 0.95,
    ConfidenceLevel.HIGH: 0.80,
    ConfidenceLevel.MEDIUM: 0.60,
    ConfidenceLevel.LOW: 0.40,
    ConfidenceLevel.UNVERIFIED: 0.0,
}


# =============================================================================
# Telegram Message Formatting
# =============================================================================

TELEGRAM_MAX_MESSAGE_LENGTH: Final[int] = 4096
TELEGRAM_MARKDOWN_ESCAPE_CHARS: Final[str] = r"_*[]()~`>#+-=|{}.!"

# Message template
TOKEN_BREAKDOWN_TEMPLATE: Final[str] = """{risk_emoji} ${symbol} - ${fdv_display} FDV

Dev: {dev_link}

Pros:
{pros_list}

Cons:
{cons_list}

Contract: `{contract_address}`
{dexscreener_url}"""
