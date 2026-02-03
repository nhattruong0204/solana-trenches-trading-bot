"""Pytest configuration and fixtures."""

import asyncio
from datetime import datetime
from typing import Generator

import pytest

from src.config import Settings
from src.models import (
    ContractAnalysis,
    DevProfile,
    EventSource,
    OnChainMetrics,
    TokenBreakdown,
    TokenEvent,
)
from src.constants import ConfidenceLevel, RiskRating


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        database=Settings.DatabaseSettings(url="postgresql://localhost/test"),
        telegram=Settings.TelegramSettings(
            bot_token="test_token",
            target_channel="-1001234567890",
            admin_users=[123456789],
        ),
        llm=Settings.LLMSettings(
            provider="anthropic",
            anthropic_api_key="test_key",
        ),
    )


@pytest.fixture
def sample_token_event() -> TokenEvent:
    """Create a sample token event."""
    return TokenEvent(
        token_address="0x1234567890abcdef1234567890abcdef12345678",
        pair_address="0xabcdef1234567890abcdef1234567890abcdef12",
        source=EventSource.CHAIN,
        detected_at=datetime.utcnow(),
        chain_id=8453,
        token_symbol="TEST",
        token_name="Test Token",
        source_metadata={"factory": "uniswap_v2"},
    )


@pytest.fixture
def sample_contract_analysis() -> ContractAnalysis:
    """Create a sample contract analysis."""
    return ContractAnalysis(
        token_address="0x1234567890abcdef1234567890abcdef12345678",
        deployer_address="0xdeployer1234567890abcdef1234567890abcd",
        analyzed_at=datetime.utcnow(),
        name="Test Token",
        symbol="TEST",
        decimals=18,
        total_supply=1_000_000_000 * 10**18,
        is_honeypot=False,
        has_mint_function=False,
        has_blacklist=False,
        is_renounced=True,
        deployer_balance_pct=5.0,
        confidence=ConfidenceLevel.HIGH,
    )


@pytest.fixture
def sample_dev_profile() -> DevProfile:
    """Create a sample dev profile."""
    return DevProfile(
        token_address="0x1234567890abcdef1234567890abcdef12345678",
        analyzed_at=datetime.utcnow(),
        twitter_handle="test_dev",
        twitter_url="https://twitter.com/test_dev",
        twitter_followers=5000,
        twitter_account_age_days=365,
        twitter_verified=False,
        is_anonymous=False,
        red_flags=[],
        reputation_score=70.0,
        confidence=ConfidenceLevel.MEDIUM,
    )


@pytest.fixture
def sample_onchain_metrics() -> OnChainMetrics:
    """Create sample on-chain metrics."""
    return OnChainMetrics(
        token_address="0x1234567890abcdef1234567890abcdef12345678",
        pair_address="0xabcdef1234567890abcdef1234567890abcdef12",
        fetched_at=datetime.utcnow(),
        price_usd=0.001,
        fdv_usd=1_000_000,
        market_cap_usd=500_000,
        liquidity_usd=50_000,
        volume_24h_usd=100_000,
        holder_count=500,
        top_10_holder_pct=15.0,
        token_age_hours=24.0,
        confidence=ConfidenceLevel.HIGH,
    )


@pytest.fixture
def sample_breakdown(
    sample_contract_analysis: ContractAnalysis,
    sample_dev_profile: DevProfile,
    sample_onchain_metrics: OnChainMetrics,
) -> TokenBreakdown:
    """Create a sample token breakdown."""
    from src.models import Claim

    return TokenBreakdown(
        token_address="0x1234567890abcdef1234567890abcdef12345678",
        analyzed_at=datetime.utcnow(),
        symbol="TEST",
        name="Test Token",
        fdv_usd=1_000_000,
        fdv_display="1.0M",
        risk_rating=RiskRating.YELLOW,
        overall_confidence=0.75,
        dev_twitter_url="https://twitter.com/test_dev",
        dev_twitter_handle="test_dev",
        pros=[
            Claim(text="Good liquidity", confidence=0.9, source="DexScreener", is_pro=True),
            Claim(text="Active developer", confidence=0.8, source="Twitter", is_pro=True),
        ],
        cons=[
            Claim(text="New token (<24h)", confidence=0.95, source="Chain", is_pro=False),
        ],
        dexscreener_url="https://dexscreener.com/base/0x1234567890abcdef1234567890abcdef12345678",
        contract_analysis=sample_contract_analysis,
        dev_profile=sample_dev_profile,
        on_chain_metrics=sample_onchain_metrics,
    )
