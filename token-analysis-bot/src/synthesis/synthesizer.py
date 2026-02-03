"""Token analysis synthesizer - combines all data into final breakdown."""

import logging
from datetime import datetime
from typing import Optional

from src.config import Settings
from src.models import (
    AnalysisJob,
    AnalysisStatus,
    Claim,
    ContractAnalysis,
    DevProfile,
    OnChainMetrics,
    TokenBreakdown,
)
from src.synthesis.llm_client import LLMClient
from src.synthesis.prompts import SYNTHESIS_PROMPT, format_fdv
from src.synthesis.scorer import RiskScore, RiskScorer

logger = logging.getLogger(__name__)


class TokenSynthesizer:
    """Synthesizes all enrichment data into final token breakdown."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm_client = LLMClient(settings)
        self.risk_scorer = RiskScorer()

    async def initialize(self) -> None:
        """Initialize synthesizer components."""
        await self.llm_client.initialize()
        logger.info("Token synthesizer initialized")

    async def close(self) -> None:
        """Close synthesizer components."""
        await self.llm_client.close()

    async def synthesize(
        self,
        contract_analysis: ContractAnalysis,
        dev_profile: DevProfile,
        onchain_metrics: OnChainMetrics,
        job: Optional[AnalysisJob] = None,
    ) -> TokenBreakdown:
        """Synthesize all data into a token breakdown."""
        logger.info(f"Synthesizing breakdown for: {contract_analysis.token_address}")
        start_time = datetime.utcnow()

        if job:
            job.status = AnalysisStatus.SYNTHESIZING
            job.updated_at = start_time

        try:
            # Calculate risk score
            risk_score = self.risk_scorer.calculate_risk(
                contract_analysis, dev_profile, onchain_metrics
            )

            # Generate pros/cons using LLM
            llm_analysis = await self._generate_llm_analysis(
                contract_analysis, dev_profile, onchain_metrics
            )

            # Build final breakdown
            breakdown = self._build_breakdown(
                contract_analysis,
                dev_profile,
                onchain_metrics,
                risk_score,
                llm_analysis,
            )

            # Check if human review needed
            breakdown.requires_human_review = self._needs_human_review(
                breakdown, risk_score
            )
            if breakdown.requires_human_review:
                breakdown.human_review_reasons = self._get_review_reasons(
                    breakdown, risk_score
                )

            # Calculate processing time
            breakdown.processing_time_seconds = (
                datetime.utcnow() - start_time
            ).total_seconds()

            # Update job
            if job:
                job.breakdown = breakdown
                if breakdown.requires_human_review:
                    job.status = AnalysisStatus.AWAITING_APPROVAL
                else:
                    job.status = AnalysisStatus.APPROVED
                job.updated_at = datetime.utcnow()

            logger.info(
                f"Synthesis complete: {breakdown.symbol} "
                f"({breakdown.risk_rating.value}) in {breakdown.processing_time_seconds:.2f}s"
            )

            return breakdown

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            if job:
                job.status = AnalysisStatus.FAILED
                job.error_message = str(e)
                job.updated_at = datetime.utcnow()
            raise

    async def _generate_llm_analysis(
        self,
        contract: ContractAnalysis,
        dev: DevProfile,
        metrics: OnChainMetrics,
    ) -> dict:
        """Generate LLM-based pros/cons analysis."""
        # Format prompt with data
        prompt = SYNTHESIS_PROMPT.format(
            token_address=contract.token_address,
            symbol=contract.symbol or "UNKNOWN",
            name=contract.name or "Unknown Token",
            deployer_address=contract.deployer_address or "Unknown",
            deployer_balance_pct=contract.deployer_balance_pct,
            is_honeypot=contract.is_honeypot,
            has_mint_function=contract.has_mint_function,
            has_blacklist=contract.has_blacklist,
            is_renounced=contract.is_renounced,
            has_proxy=contract.has_proxy,
            deployer_prior_tokens_count=len(contract.deployer_prior_tokens),
            dev_twitter=dev.twitter_url or "Anonymous",
            dev_followers=dev.twitter_followers,
            dev_account_age_days=dev.twitter_account_age_days,
            dev_verified=dev.twitter_verified,
            attribution_verified=dev.attribution_verified,
            prior_projects=len(dev.prior_projects),
            red_flags=", ".join(dev.red_flags) if dev.red_flags else "None",
            is_anonymous=dev.is_anonymous,
            fdv=metrics.fdv_usd,
            market_cap=metrics.market_cap_usd,
            liquidity=metrics.liquidity_usd,
            volume_24h=metrics.volume_24h_usd,
            holder_count=metrics.holder_count,
            top_10_holder_pct=metrics.top_10_holder_pct,
            token_age_hours=metrics.token_age_hours,
            price_change_24h=metrics.price_change_24h,
        )

        # Get LLM analysis
        try:
            result = await self.llm_client.generate_json(prompt)
            return result
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Return fallback analysis
            return self._generate_fallback_analysis(contract, dev, metrics)

    def _generate_fallback_analysis(
        self,
        contract: ContractAnalysis,
        dev: DevProfile,
        metrics: OnChainMetrics,
    ) -> dict:
        """Generate rule-based analysis when LLM fails."""
        pros = []
        cons = []

        # Liquidity
        if metrics.liquidity_usd >= 50000:
            pros.append({
                "text": f"Strong liquidity (${metrics.liquidity_usd:,.0f})",
                "confidence": 0.95,
                "source": "DexScreener"
            })
        elif metrics.liquidity_usd < 10000:
            cons.append({
                "text": f"Low liquidity (${metrics.liquidity_usd:,.0f})",
                "confidence": 0.95,
                "source": "DexScreener"
            })

        # Holders
        if metrics.holder_count >= 200:
            pros.append({
                "text": f"Good holder base ({metrics.holder_count})",
                "confidence": 0.90,
                "source": "Basescan"
            })
        elif metrics.holder_count < 50:
            cons.append({
                "text": f"Very few holders ({metrics.holder_count})",
                "confidence": 0.90,
                "source": "Basescan"
            })

        # Contract
        if contract.is_renounced:
            pros.append({
                "text": "Contract ownership renounced",
                "confidence": 0.95,
                "source": "Contract analysis"
            })
        if contract.is_honeypot:
            cons.append({
                "text": "HONEYPOT - Cannot sell tokens",
                "confidence": 0.99,
                "source": "Honeypot checker"
            })
        if contract.has_mint_function:
            cons.append({
                "text": "Has mint function (supply can increase)",
                "confidence": 0.90,
                "source": "Contract analysis"
            })

        # Developer
        if dev.twitter_verified:
            pros.append({
                "text": "Verified Twitter account",
                "confidence": 0.95,
                "source": "Twitter"
            })
        if dev.twitter_followers >= 10000:
            pros.append({
                "text": f"Large following ({dev.twitter_followers:,})",
                "confidence": 0.90,
                "source": "Twitter"
            })
        if dev.is_anonymous:
            cons.append({
                "text": "Anonymous developer",
                "confidence": 0.85,
                "source": "OSINT"
            })
        for flag in dev.red_flags[:2]:  # Limit to 2 red flags
            cons.append({
                "text": flag,
                "confidence": 0.80,
                "source": "OSINT"
            })

        return {
            "pros": pros[:5],  # Limit to 5
            "cons": cons[:4],  # Limit to 4
            "overall_assessment": "Automated analysis based on available data",
            "confidence_score": 0.70,
        }

    def _build_breakdown(
        self,
        contract: ContractAnalysis,
        dev: DevProfile,
        metrics: OnChainMetrics,
        risk_score: RiskScore,
        llm_analysis: dict,
    ) -> TokenBreakdown:
        """Build the final token breakdown."""
        # Parse LLM pros/cons into Claim objects
        pros = [
            Claim(
                text=p.get("text", str(p)),
                confidence=p.get("confidence", 0.7),
                source=p.get("source", "analysis"),
                is_pro=True,
            )
            for p in llm_analysis.get("pros", [])
        ]

        cons = [
            Claim(
                text=c.get("text", str(c)),
                confidence=c.get("confidence", 0.7),
                source=c.get("source", "analysis"),
                is_pro=False,
            )
            for c in llm_analysis.get("cons", [])
        ]

        # Build DexScreener URL
        dexscreener_url = f"https://dexscreener.com/base/{contract.token_address}"

        # Build contract URL
        contract_url = f"https://basescan.org/token/{contract.token_address}"

        return TokenBreakdown(
            token_address=contract.token_address,
            analyzed_at=datetime.utcnow(),
            symbol=contract.symbol or "UNKNOWN",
            name=contract.name or "Unknown Token",
            fdv_usd=metrics.fdv_usd,
            fdv_display=format_fdv(metrics.fdv_usd),
            risk_rating=risk_score.rating,
            overall_confidence=llm_analysis.get("confidence_score", risk_score.confidence),
            dev_twitter_url=dev.twitter_url,
            dev_twitter_handle=dev.twitter_handle,
            pros=pros,
            cons=cons,
            dexscreener_url=dexscreener_url,
            contract_url=contract_url,
            contract_analysis=contract,
            dev_profile=dev,
            on_chain_metrics=metrics,
        )

    def _needs_human_review(
        self, breakdown: TokenBreakdown, risk_score: RiskScore
    ) -> bool:
        """Determine if human review is needed."""
        # Always review if below confidence threshold
        if breakdown.overall_confidence < self.settings.analysis.confidence_threshold:
            return True

        # Review RED ratings
        if risk_score.rating == RiskRating.RED:
            return True

        # Review if many low-confidence claims
        low_conf_claims = sum(
            1 for c in breakdown.pros + breakdown.cons if c.confidence < 0.6
        )
        if low_conf_claims > 2:
            return True

        # Review if dev has red flags but still not RED
        if breakdown.dev_profile and len(breakdown.dev_profile.red_flags) >= 2:
            return True

        return not self.settings.analysis.enable_human_approval

    def _get_review_reasons(
        self, breakdown: TokenBreakdown, risk_score: RiskScore
    ) -> list[str]:
        """Get reasons why human review is needed."""
        reasons = []

        if breakdown.overall_confidence < self.settings.analysis.confidence_threshold:
            reasons.append(
                f"Low confidence score: {breakdown.overall_confidence:.2f}"
            )

        if risk_score.rating == RiskRating.RED:
            reasons.append(f"RED rating: {risk_score.primary_reason}")

        low_conf_claims = [
            c.text for c in breakdown.pros + breakdown.cons if c.confidence < 0.6
        ]
        if low_conf_claims:
            reasons.append(f"Low confidence claims: {len(low_conf_claims)}")

        if breakdown.dev_profile and breakdown.dev_profile.red_flags:
            reasons.append(f"Dev red flags: {', '.join(breakdown.dev_profile.red_flags[:2])}")

        return reasons


# Import for type hint
from src.constants import RiskRating
