"""Tests for data models."""

from datetime import datetime

import pytest

from src.constants import ConfidenceLevel, RiskRating
from src.models import (
    AnalysisJob,
    AnalysisStatus,
    Claim,
    ContractAnalysis,
    DevProfile,
    EventSource,
    OnChainMetrics,
    TokenBreakdown,
    TokenEvent,
)


class TestTokenEvent:
    """Tests for TokenEvent model."""

    def test_create_token_event(self):
        """Test creating a token event."""
        event = TokenEvent(
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            pair_address="0xabcdef1234567890abcdef1234567890abcdef12",
            source=EventSource.CHAIN,
            detected_at=datetime.utcnow(),
        )

        assert event.token_address == "0x1234567890abcdef1234567890abcdef12345678"
        assert event.source == EventSource.CHAIN
        assert event.chain_id == 8453  # Default

    def test_token_event_hash(self):
        """Test token event hashing for deduplication."""
        event1 = TokenEvent(
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            pair_address=None,
            source=EventSource.CHAIN,
            detected_at=datetime.utcnow(),
        )
        event2 = TokenEvent(
            token_address="0x1234567890ABCDEF1234567890ABCDEF12345678",  # Same, different case
            pair_address=None,
            source=EventSource.MOLTBOOK,
            detected_at=datetime.utcnow(),
        )

        assert hash(event1) == hash(event2)


class TestContractAnalysis:
    """Tests for ContractAnalysis model."""

    def test_create_contract_analysis(self, sample_contract_analysis):
        """Test creating contract analysis."""
        assert sample_contract_analysis.symbol == "TEST"
        assert sample_contract_analysis.is_renounced is True
        assert sample_contract_analysis.is_honeypot is False

    def test_honeypot_detection(self):
        """Test honeypot flag."""
        analysis = ContractAnalysis(
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            deployer_address="0xdeployer",
            analyzed_at=datetime.utcnow(),
            is_honeypot=True,
            honeypot_reason="Cannot sell",
        )

        assert analysis.is_honeypot is True
        assert analysis.honeypot_reason == "Cannot sell"


class TestDevProfile:
    """Tests for DevProfile model."""

    def test_create_dev_profile(self, sample_dev_profile):
        """Test creating dev profile."""
        assert sample_dev_profile.twitter_handle == "test_dev"
        assert sample_dev_profile.twitter_followers == 5000
        assert sample_dev_profile.is_anonymous is False

    def test_anonymous_dev(self):
        """Test anonymous developer profile."""
        profile = DevProfile(
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            analyzed_at=datetime.utcnow(),
            is_anonymous=True,
        )

        assert profile.is_anonymous is True
        assert profile.twitter_handle is None


class TestOnChainMetrics:
    """Tests for OnChainMetrics model."""

    def test_create_metrics(self, sample_onchain_metrics):
        """Test creating on-chain metrics."""
        assert sample_onchain_metrics.fdv_usd == 1_000_000
        assert sample_onchain_metrics.liquidity_usd == 50_000
        assert sample_onchain_metrics.holder_count == 500

    def test_low_liquidity_detection(self):
        """Test detecting low liquidity."""
        metrics = OnChainMetrics(
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            pair_address="0xpair",
            fetched_at=datetime.utcnow(),
            liquidity_usd=1000,  # Very low
        )

        assert metrics.liquidity_usd < 5000


class TestTokenBreakdown:
    """Tests for TokenBreakdown model."""

    def test_create_breakdown(self, sample_breakdown):
        """Test creating token breakdown."""
        assert sample_breakdown.symbol == "TEST"
        assert sample_breakdown.risk_rating == RiskRating.YELLOW
        assert len(sample_breakdown.pros) == 2
        assert len(sample_breakdown.cons) == 1

    def test_breakdown_confidence(self, sample_breakdown):
        """Test breakdown confidence scoring."""
        assert sample_breakdown.overall_confidence == 0.75

    def test_human_review_flag(self, sample_breakdown):
        """Test human review flag."""
        sample_breakdown.requires_human_review = True
        sample_breakdown.human_review_reasons = ["Low confidence"]

        assert sample_breakdown.requires_human_review is True
        assert len(sample_breakdown.human_review_reasons) == 1


class TestAnalysisJob:
    """Tests for AnalysisJob model."""

    def test_create_job(self):
        """Test creating analysis job."""
        job = AnalysisJob(
            job_id="test_job_123",
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            status=AnalysisStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        assert job.job_id == "test_job_123"
        assert job.status == AnalysisStatus.PENDING

    def test_job_status_transitions(self):
        """Test job status transitions."""
        job = AnalysisJob(
            job_id="test_job_123",
            token_address="0x1234567890abcdef1234567890abcdef12345678",
            status=AnalysisStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Transition through states
        job.status = AnalysisStatus.ENRICHING
        assert job.status == AnalysisStatus.ENRICHING

        job.status = AnalysisStatus.SYNTHESIZING
        assert job.status == AnalysisStatus.SYNTHESIZING

        job.status = AnalysisStatus.PUBLISHED
        assert job.status == AnalysisStatus.PUBLISHED


class TestClaim:
    """Tests for Claim model."""

    def test_create_claim(self):
        """Test creating a claim."""
        claim = Claim(
            text="Good liquidity",
            confidence=0.9,
            source="DexScreener",
            is_pro=True,
        )

        assert claim.text == "Good liquidity"
        assert claim.confidence == 0.9
        assert claim.is_pro is True

    def test_low_confidence_claim(self):
        """Test low confidence claim."""
        claim = Claim(
            text="Developer may be experienced",
            confidence=0.4,
            source="OSINT",
            is_pro=True,
        )

        assert claim.confidence < 0.5
