"""Data models for token analysis."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from src.constants import ConfidenceLevel, RiskRating


# =============================================================================
# Event Models
# =============================================================================

class EventSource(str, Enum):
    """Source of token detection event."""
    CHAIN = "chain"          # PairCreated on-chain event
    MOLTBOOK = "moltbook"    # Moltbook API/scraper
    TWITTER = "twitter"      # Twitter/X mention
    MANUAL = "manual"        # Manual submission


@dataclass
class TokenEvent:
    """Detected new token event."""
    token_address: str
    pair_address: Optional[str]
    source: EventSource
    detected_at: datetime
    chain_id: int = 8453  # Base mainnet

    # Optional metadata from source
    token_symbol: Optional[str] = None
    token_name: Optional[str] = None
    deployer_address: Optional[str] = None
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.token_address.lower())


# =============================================================================
# Enrichment Data Models
# =============================================================================

@dataclass
class ContractAnalysis:
    """Contract security and metadata analysis."""
    token_address: str
    deployer_address: str
    analyzed_at: datetime

    # Token info
    name: str = ""
    symbol: str = ""
    decimals: int = 18
    total_supply: int = 0

    # Security checks
    is_honeypot: bool = False
    honeypot_reason: Optional[str] = None
    has_proxy: bool = False
    has_mint_function: bool = False
    has_blacklist: bool = False
    owner_address: Optional[str] = None
    is_renounced: bool = False

    # Deployer info
    deployer_balance_pct: float = 0.0
    deployer_eth_balance: float = 0.0
    deployer_tx_count: int = 0
    deployer_age_days: int = 0
    deployer_prior_tokens: list[str] = field(default_factory=list)

    # Confidence
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


@dataclass
class DevProfile:
    """Developer/team OSINT data."""
    token_address: str
    analyzed_at: datetime

    # Twitter/X
    twitter_handle: Optional[str] = None
    twitter_url: Optional[str] = None
    twitter_followers: int = 0
    twitter_account_age_days: int = 0
    twitter_verified: bool = False
    twitter_engagement_rate: float = 0.0
    recent_tweets: list[str] = field(default_factory=list)

    # LinkedIn/professional
    linkedin_url: Optional[str] = None
    real_name: Optional[str] = None
    professional_history: list[str] = field(default_factory=list)

    # Prior projects
    prior_projects: list[dict[str, Any]] = field(default_factory=list)
    prior_rugs: list[str] = field(default_factory=list)
    reputation_score: float = 0.0

    # Red flags
    red_flags: list[str] = field(default_factory=list)
    is_anonymous: bool = True

    # Attribution verification
    attribution_verified: bool = False  # On-chain proof of ownership
    attribution_method: Optional[str] = None  # ENS, signed message, etc.
    confidence: ConfidenceLevel = ConfidenceLevel.LOW


@dataclass
class OnChainMetrics:
    """On-chain trading metrics."""
    token_address: str
    pair_address: str
    fetched_at: datetime

    # Price data
    price_usd: float = 0.0
    price_native: float = 0.0  # In ETH

    # Valuation
    market_cap_usd: float = 0.0
    fdv_usd: float = 0.0
    circulating_supply: int = 0

    # Liquidity
    liquidity_usd: float = 0.0
    liquidity_native: float = 0.0

    # Volume
    volume_24h_usd: float = 0.0
    volume_1h_usd: float = 0.0
    buys_24h: int = 0
    sells_24h: int = 0

    # Price changes
    price_change_1h: float = 0.0
    price_change_6h: float = 0.0
    price_change_24h: float = 0.0

    # Holders
    holder_count: int = 0
    top_10_holder_pct: float = 0.0
    smart_wallet_count: int = 0
    smart_wallet_addresses: list[str] = field(default_factory=list)

    # Token age
    pair_created_at: Optional[datetime] = None
    token_age_hours: float = 0.0

    # Slippage analysis
    slippage_1_pct_buy: float = 0.0
    slippage_2_pct_buy: float = 0.0
    slippage_5_pct_buy: float = 0.0

    confidence: ConfidenceLevel = ConfidenceLevel.HIGH


# =============================================================================
# Synthesis Models
# =============================================================================

@dataclass
class Claim:
    """A claim about the token with confidence."""
    text: str
    confidence: float  # 0.0 to 1.0
    source: str  # Where this claim comes from
    is_pro: bool  # True for pros, False for cons
    verified: bool = False


@dataclass
class TokenBreakdown:
    """Complete token analysis breakdown."""
    token_address: str
    analyzed_at: datetime

    # Basic info
    symbol: str
    name: str
    fdv_usd: float
    fdv_display: str  # Formatted, e.g., "2.5M"

    # Risk assessment
    risk_rating: RiskRating
    overall_confidence: float  # 0.0 to 1.0

    # Developer
    dev_twitter_url: Optional[str] = None
    dev_twitter_handle: Optional[str] = None

    # Claims
    pros: list[Claim] = field(default_factory=list)
    cons: list[Claim] = field(default_factory=list)

    # Links
    dexscreener_url: str = ""
    contract_url: str = ""

    # Raw data (for debugging/auditing)
    contract_analysis: Optional[ContractAnalysis] = None
    dev_profile: Optional[DevProfile] = None
    on_chain_metrics: Optional[OnChainMetrics] = None

    # Processing metadata
    processing_time_seconds: float = 0.0
    requires_human_review: bool = False
    human_review_reasons: list[str] = field(default_factory=list)


# =============================================================================
# State Models
# =============================================================================

class AnalysisStatus(str, Enum):
    """Status of token analysis."""
    PENDING = "pending"
    ENRICHING = "enriching"
    SYNTHESIZING = "synthesizing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class AnalysisJob:
    """Analysis job tracking."""
    job_id: str
    token_address: str
    status: AnalysisStatus
    created_at: datetime
    updated_at: datetime

    # Progress
    event: Optional[TokenEvent] = None
    contract_analysis: Optional[ContractAnalysis] = None
    dev_profile: Optional[DevProfile] = None
    on_chain_metrics: Optional[OnChainMetrics] = None
    breakdown: Optional[TokenBreakdown] = None

    # Outcome
    error_message: Optional[str] = None
    telegram_message_id: Optional[int] = None
    published_at: Optional[datetime] = None


# =============================================================================
# Blacklist Models
# =============================================================================

@dataclass
class BlacklistEntry:
    """Blacklisted address or dev."""
    address: str
    reason: str
    added_at: datetime
    added_by: str  # Admin user ID or "system"
    category: str  # "wallet", "contract", "dev_twitter"
