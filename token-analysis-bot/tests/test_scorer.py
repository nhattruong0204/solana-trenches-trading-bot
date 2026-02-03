"""Tests for risk scoring engine."""

from datetime import datetime

import pytest

from src.constants import ConfidenceLevel, RiskRating
from src.models import ContractAnalysis, DevProfile, OnChainMetrics
from src.synthesis.scorer import RiskScorer


@pytest.fixture
def risk_scorer():
    """Create risk scorer instance."""
    return RiskScorer()


class TestRiskScorer:
    """Tests for RiskScorer."""

    def test_green_rating_good_metrics(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test green rating with good metrics."""
        # Improve metrics for green rating
        sample_onchain_metrics.liquidity_usd = 100000
        sample_onchain_metrics.holder_count = 500
        sample_onchain_metrics.top_10_holder_pct = 8.0
        sample_dev_profile.twitter_followers = 15000
        sample_dev_profile.twitter_verified = True
        sample_contract_analysis.is_renounced = True

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert score.rating == RiskRating.GREEN
        assert score.overall_score >= 75

    def test_red_rating_honeypot(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test red rating for honeypot."""
        sample_contract_analysis.is_honeypot = True

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert score.rating == RiskRating.RED
        assert "honeypot" in score.primary_reason.lower()

    def test_red_rating_scammer_dev(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test red rating for known scammer."""
        sample_dev_profile.red_flags = ["Known scammer", "Prior rug pulls"]

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert score.rating == RiskRating.RED
        assert len(score.negative_factors) >= 2

    def test_yellow_rating_moderate_metrics(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test yellow rating with moderate metrics."""
        sample_onchain_metrics.liquidity_usd = 25000
        sample_onchain_metrics.holder_count = 150
        sample_onchain_metrics.top_10_holder_pct = 15.0

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert score.rating in [RiskRating.YELLOW, RiskRating.GREEN]

    def test_orange_rating_low_liquidity(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test orange rating with low liquidity."""
        sample_onchain_metrics.liquidity_usd = 6000
        sample_onchain_metrics.holder_count = 60
        sample_dev_profile.is_anonymous = True

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert score.rating in [RiskRating.ORANGE, RiskRating.YELLOW]

    def test_liquidity_scoring(self, risk_scorer):
        """Test liquidity score calculation."""
        metrics_high = OnChainMetrics(
            token_address="0x123",
            pair_address="0x456",
            fetched_at=datetime.utcnow(),
            liquidity_usd=100000,
        )
        metrics_low = OnChainMetrics(
            token_address="0x123",
            pair_address="0x456",
            fetched_at=datetime.utcnow(),
            liquidity_usd=3000,
        )

        high_score = risk_scorer._score_liquidity(metrics_high)
        low_score = risk_scorer._score_liquidity(metrics_low)

        assert high_score > low_score
        assert high_score >= 80
        assert low_score <= 20

    def test_holder_scoring(self, risk_scorer):
        """Test holder score calculation."""
        metrics_good = OnChainMetrics(
            token_address="0x123",
            pair_address="0x456",
            fetched_at=datetime.utcnow(),
            holder_count=500,
            top_10_holder_pct=8.0,
        )
        metrics_bad = OnChainMetrics(
            token_address="0x123",
            pair_address="0x456",
            fetched_at=datetime.utcnow(),
            holder_count=30,
            top_10_holder_pct=45.0,
        )

        good_score = risk_scorer._score_holders(metrics_good)
        bad_score = risk_scorer._score_holders(metrics_bad)

        assert good_score > bad_score

    def test_contract_scoring(self, risk_scorer):
        """Test contract score calculation."""
        contract_safe = ContractAnalysis(
            token_address="0x123",
            deployer_address="0x456",
            analyzed_at=datetime.utcnow(),
            is_honeypot=False,
            is_renounced=True,
            has_mint_function=False,
            has_blacklist=False,
        )
        contract_risky = ContractAnalysis(
            token_address="0x123",
            deployer_address="0x456",
            analyzed_at=datetime.utcnow(),
            is_honeypot=False,
            is_renounced=False,
            has_mint_function=True,
            has_blacklist=True,
        )

        safe_score = risk_scorer._score_contract(contract_safe)
        risky_score = risk_scorer._score_contract(contract_risky)

        assert safe_score > risky_score
        assert safe_score >= 90

    def test_dev_scoring(self, risk_scorer):
        """Test dev score calculation."""
        dev_good = DevProfile(
            token_address="0x123",
            analyzed_at=datetime.utcnow(),
            twitter_handle="good_dev",
            twitter_followers=20000,
            twitter_verified=True,
            twitter_account_age_days=500,
            is_anonymous=False,
            red_flags=[],
        )
        dev_bad = DevProfile(
            token_address="0x123",
            analyzed_at=datetime.utcnow(),
            twitter_handle=None,
            twitter_followers=0,
            is_anonymous=True,
            red_flags=["New account", "Fake followers"],
        )

        good_score = risk_scorer._score_dev(dev_good)
        bad_score = risk_scorer._score_dev(dev_bad)

        assert good_score > bad_score
        assert good_score >= 70

    def test_positive_factors_collected(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test that positive factors are collected."""
        sample_onchain_metrics.liquidity_usd = 100000
        sample_contract_analysis.is_renounced = True

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert len(score.positive_factors) > 0

    def test_negative_factors_collected(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test that negative factors are collected."""
        sample_contract_analysis.has_mint_function = True
        sample_dev_profile.is_anonymous = True

        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert len(score.negative_factors) > 0

    def test_confidence_calculation(
        self,
        risk_scorer,
        sample_contract_analysis,
        sample_dev_profile,
        sample_onchain_metrics,
    ):
        """Test confidence score calculation."""
        score = risk_scorer.calculate_risk(
            sample_contract_analysis, sample_dev_profile, sample_onchain_metrics
        )

        assert 0 <= score.confidence <= 1
