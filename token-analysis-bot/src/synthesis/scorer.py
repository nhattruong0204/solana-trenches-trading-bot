"""Risk scoring engine for token analysis."""

import logging
from dataclasses import dataclass
from typing import Optional

from src.constants import (
    MAX_TOP_HOLDER_PCT_GREEN,
    MAX_TOP_HOLDER_PCT_ORANGE,
    MAX_TOP_HOLDER_PCT_YELLOW,
    MIN_HOLDERS_GREEN,
    MIN_HOLDERS_ORANGE,
    MIN_HOLDERS_YELLOW,
    MIN_LIQUIDITY_FOR_GREEN,
    MIN_LIQUIDITY_FOR_ORANGE,
    MIN_LIQUIDITY_FOR_YELLOW,
    RiskRating,
)
from src.models import ContractAnalysis, DevProfile, OnChainMetrics

logger = logging.getLogger(__name__)


@dataclass
class RiskScore:
    """Detailed risk score breakdown."""
    rating: RiskRating
    overall_score: float  # 0-100, higher is better
    confidence: float  # 0-1

    # Component scores
    liquidity_score: float
    holder_score: float
    contract_score: float
    dev_score: float

    # Factors
    primary_reason: str
    positive_factors: list[str]
    negative_factors: list[str]


class RiskScorer:
    """Calculates risk ratings for tokens."""

    def __init__(self):
        # Weights for different components
        self.weights = {
            "liquidity": 0.25,
            "holders": 0.20,
            "contract": 0.30,
            "dev": 0.25,
        }

    def calculate_risk(
        self,
        contract_analysis: ContractAnalysis,
        dev_profile: DevProfile,
        onchain_metrics: OnChainMetrics,
    ) -> RiskScore:
        """Calculate comprehensive risk score."""
        # Calculate component scores
        liquidity_score = self._score_liquidity(onchain_metrics)
        holder_score = self._score_holders(onchain_metrics)
        contract_score = self._score_contract(contract_analysis)
        dev_score = self._score_dev(dev_profile)

        # Calculate weighted overall score
        overall_score = (
            liquidity_score * self.weights["liquidity"]
            + holder_score * self.weights["holders"]
            + contract_score * self.weights["contract"]
            + dev_score * self.weights["dev"]
        )

        # Collect factors
        positive_factors = []
        negative_factors = []

        # Liquidity factors
        if onchain_metrics.liquidity_usd >= MIN_LIQUIDITY_FOR_GREEN:
            positive_factors.append(f"Strong liquidity (${onchain_metrics.liquidity_usd:,.0f})")
        elif onchain_metrics.liquidity_usd < MIN_LIQUIDITY_FOR_ORANGE:
            negative_factors.append(f"Low liquidity (${onchain_metrics.liquidity_usd:,.0f})")

        # Holder factors
        if onchain_metrics.holder_count >= MIN_HOLDERS_GREEN:
            positive_factors.append(f"Good holder base ({onchain_metrics.holder_count})")
        elif onchain_metrics.holder_count < MIN_HOLDERS_ORANGE:
            negative_factors.append(f"Few holders ({onchain_metrics.holder_count})")

        if onchain_metrics.top_10_holder_pct <= MAX_TOP_HOLDER_PCT_GREEN:
            positive_factors.append("Well-distributed holdings")
        elif onchain_metrics.top_10_holder_pct > MAX_TOP_HOLDER_PCT_ORANGE:
            negative_factors.append(f"High concentration ({onchain_metrics.top_10_holder_pct:.1f}%)")

        # Contract factors
        if contract_analysis.is_honeypot:
            negative_factors.append("HONEYPOT DETECTED")
        if contract_analysis.is_renounced:
            positive_factors.append("Contract renounced")
        if contract_analysis.has_mint_function:
            negative_factors.append("Has mint function")
        if contract_analysis.has_blacklist:
            negative_factors.append("Has blacklist")
        if contract_analysis.has_proxy:
            negative_factors.append("Proxy contract (upgradeable)")

        # Dev factors
        if dev_profile.attribution_verified:
            positive_factors.append("Dev identity verified on-chain")
        if dev_profile.twitter_verified:
            positive_factors.append("Verified Twitter")
        if dev_profile.twitter_followers >= 10000:
            positive_factors.append(f"Strong following ({dev_profile.twitter_followers:,})")
        if dev_profile.is_anonymous:
            negative_factors.append("Anonymous developer")
        for flag in dev_profile.red_flags:
            negative_factors.append(f"Dev red flag: {flag}")

        # Determine rating
        rating = self._determine_rating(
            overall_score,
            contract_analysis,
            dev_profile,
            negative_factors,
        )

        # Determine primary reason
        primary_reason = self._get_primary_reason(
            rating, contract_analysis, dev_profile, onchain_metrics
        )

        # Calculate confidence based on data completeness
        confidence = self._calculate_confidence(
            contract_analysis, dev_profile, onchain_metrics
        )

        return RiskScore(
            rating=rating,
            overall_score=overall_score,
            confidence=confidence,
            liquidity_score=liquidity_score,
            holder_score=holder_score,
            contract_score=contract_score,
            dev_score=dev_score,
            primary_reason=primary_reason,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
        )

    def _score_liquidity(self, metrics: OnChainMetrics) -> float:
        """Score liquidity on 0-100 scale."""
        liq = metrics.liquidity_usd

        if liq >= MIN_LIQUIDITY_FOR_GREEN:
            # 80-100 range for good liquidity
            return min(80 + (liq - MIN_LIQUIDITY_FOR_GREEN) / 5000, 100)
        elif liq >= MIN_LIQUIDITY_FOR_YELLOW:
            # 50-80 range
            return 50 + (liq - MIN_LIQUIDITY_FOR_YELLOW) / (
                MIN_LIQUIDITY_FOR_GREEN - MIN_LIQUIDITY_FOR_YELLOW
            ) * 30
        elif liq >= MIN_LIQUIDITY_FOR_ORANGE:
            # 20-50 range
            return 20 + (liq - MIN_LIQUIDITY_FOR_ORANGE) / (
                MIN_LIQUIDITY_FOR_YELLOW - MIN_LIQUIDITY_FOR_ORANGE
            ) * 30
        else:
            # 0-20 range
            return max(0, liq / MIN_LIQUIDITY_FOR_ORANGE * 20)

    def _score_holders(self, metrics: OnChainMetrics) -> float:
        """Score holder distribution on 0-100 scale."""
        score = 50.0

        # Holder count component (0-50 points)
        if metrics.holder_count >= MIN_HOLDERS_GREEN:
            holder_score = 50
        elif metrics.holder_count >= MIN_HOLDERS_YELLOW:
            holder_score = 30 + (metrics.holder_count - MIN_HOLDERS_YELLOW) / (
                MIN_HOLDERS_GREEN - MIN_HOLDERS_YELLOW
            ) * 20
        elif metrics.holder_count >= MIN_HOLDERS_ORANGE:
            holder_score = 10 + (metrics.holder_count - MIN_HOLDERS_ORANGE) / (
                MIN_HOLDERS_YELLOW - MIN_HOLDERS_ORANGE
            ) * 20
        else:
            holder_score = metrics.holder_count / MIN_HOLDERS_ORANGE * 10

        # Concentration component (0-50 points)
        if metrics.top_10_holder_pct <= MAX_TOP_HOLDER_PCT_GREEN:
            conc_score = 50
        elif metrics.top_10_holder_pct <= MAX_TOP_HOLDER_PCT_YELLOW:
            conc_score = 30 + (MAX_TOP_HOLDER_PCT_YELLOW - metrics.top_10_holder_pct) / (
                MAX_TOP_HOLDER_PCT_YELLOW - MAX_TOP_HOLDER_PCT_GREEN
            ) * 20
        elif metrics.top_10_holder_pct <= MAX_TOP_HOLDER_PCT_ORANGE:
            conc_score = 10 + (MAX_TOP_HOLDER_PCT_ORANGE - metrics.top_10_holder_pct) / (
                MAX_TOP_HOLDER_PCT_ORANGE - MAX_TOP_HOLDER_PCT_YELLOW
            ) * 20
        else:
            conc_score = max(0, (100 - metrics.top_10_holder_pct) / (100 - MAX_TOP_HOLDER_PCT_ORANGE) * 10)

        return holder_score + conc_score

    def _score_contract(self, analysis: ContractAnalysis) -> float:
        """Score contract safety on 0-100 scale."""
        score = 100.0

        # Critical failures
        if analysis.is_honeypot:
            return 0  # Instant fail

        # Major deductions
        if analysis.has_mint_function:
            score -= 25
        if analysis.has_blacklist:
            score -= 20
        if analysis.has_proxy:
            score -= 15
        if not analysis.is_renounced:
            score -= 10

        # Deployer concerns
        if analysis.deployer_balance_pct > 10:
            score -= 15
        elif analysis.deployer_balance_pct > 5:
            score -= 10

        # Prior tokens (potential serial deployer)
        if len(analysis.deployer_prior_tokens) > 10:
            score -= 20
        elif len(analysis.deployer_prior_tokens) > 5:
            score -= 10

        return max(0, score)

    def _score_dev(self, profile: DevProfile) -> float:
        """Score developer credibility on 0-100 scale."""
        score = 50.0  # Start neutral

        # Positive factors
        if profile.attribution_verified:
            score += 25
        if profile.twitter_verified:
            score += 15
        if profile.twitter_followers >= 10000:
            score += 15
        elif profile.twitter_followers >= 1000:
            score += 10
        elif profile.twitter_followers >= 500:
            score += 5

        if profile.twitter_account_age_days >= 365:
            score += 10
        elif profile.twitter_account_age_days >= 180:
            score += 5

        if profile.reputation_score >= 80:
            score += 10
        elif profile.reputation_score >= 60:
            score += 5

        # Negative factors
        if profile.is_anonymous:
            score -= 20

        # Red flags
        for flag in profile.red_flags:
            if "scammer" in flag.lower() or "rug" in flag.lower():
                score -= 40
            elif "fake" in flag.lower():
                score -= 15
            else:
                score -= 10

        return max(0, min(100, score))

    def _determine_rating(
        self,
        overall_score: float,
        contract: ContractAnalysis,
        dev: DevProfile,
        negative_factors: list[str],
    ) -> RiskRating:
        """Determine final risk rating."""
        # Instant RED conditions
        if contract.is_honeypot:
            return RiskRating.RED

        if any("scammer" in f.lower() for f in negative_factors):
            return RiskRating.RED

        if len(negative_factors) >= 5:
            return RiskRating.RED

        # Score-based rating
        if overall_score >= 75 and len(negative_factors) <= 1:
            return RiskRating.GREEN
        elif overall_score >= 55 and len(negative_factors) <= 2:
            return RiskRating.YELLOW
        elif overall_score >= 35:
            return RiskRating.ORANGE
        else:
            return RiskRating.RED

    def _get_primary_reason(
        self,
        rating: RiskRating,
        contract: ContractAnalysis,
        dev: DevProfile,
        metrics: OnChainMetrics,
    ) -> str:
        """Get the primary reason for the rating."""
        if rating == RiskRating.RED:
            if contract.is_honeypot:
                return "Honeypot detected - cannot sell tokens"
            if any("scammer" in f.lower() for f in dev.red_flags):
                return "Developer associated with known scams"
            return "Multiple critical risk factors"

        elif rating == RiskRating.GREEN:
            if dev.attribution_verified:
                return "Verified developer with good metrics"
            if metrics.liquidity_usd >= MIN_LIQUIDITY_FOR_GREEN:
                return "Strong liquidity and healthy distribution"
            return "Overall positive risk assessment"

        elif rating == RiskRating.YELLOW:
            if dev.is_anonymous:
                return "Anonymous developer - proceed with caution"
            if metrics.liquidity_usd < MIN_LIQUIDITY_FOR_GREEN:
                return "Moderate liquidity - watch for changes"
            return "Some concerns but tradeable"

        else:  # ORANGE
            if metrics.liquidity_usd < MIN_LIQUIDITY_FOR_YELLOW:
                return "Low liquidity - high slippage risk"
            if metrics.token_age_hours < 6:
                return "Very early stage - high volatility expected"
            return "Multiple risk factors - exercise caution"

    def _calculate_confidence(
        self,
        contract: ContractAnalysis,
        dev: DevProfile,
        metrics: OnChainMetrics,
    ) -> float:
        """Calculate confidence in the risk assessment."""
        confidence = 0.5  # Start at 50%

        # Data completeness factors
        if contract.symbol:
            confidence += 0.1
        if contract.deployer_address:
            confidence += 0.1
        if dev.twitter_handle:
            confidence += 0.1
        if dev.attribution_verified:
            confidence += 0.1
        if metrics.liquidity_usd > 0:
            confidence += 0.1
        if metrics.holder_count > 0:
            confidence += 0.1

        return min(1.0, confidence)
