"""Unit tests for Solana and EVM contract detectors."""

from __future__ import annotations

import pytest

from telegram_alpha_radar.detectors.solana_detector import SolanaDetector
from telegram_alpha_radar.detectors.evm_detector import EvmDetector


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def solana_detector() -> SolanaDetector:
    return SolanaDetector()


@pytest.fixture
def evm_detector() -> EvmDetector:
    return EvmDetector()


# ---------------------------------------------------------------
# Solana Detector Tests
# ---------------------------------------------------------------


class TestSolanaDetector:
    @pytest.mark.asyncio
    async def test_detects_valid_solana_address(
        self, solana_detector: SolanaDetector
    ) -> None:
        msg = "Check out this token: DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 1
        assert matches[0].contract == "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        assert matches[0].chain == "solana"

    @pytest.mark.asyncio
    async def test_ignores_common_words(
        self, solana_detector: SolanaDetector
    ) -> None:
        msg = "Bitcoin and Ethereum are going up today! Solana is great."
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_ignores_system_addresses(
        self, solana_detector: SolanaDetector
    ) -> None:
        msg = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_deduplicates_within_message(
        self, solana_detector: SolanaDetector
    ) -> None:
        addr = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
        msg = f"Buy {addr} now! I said {addr}!"
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_multiple_addresses(
        self, solana_detector: SolanaDetector
    ) -> None:
        msg = (
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 "
            "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
        )
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 2

    @pytest.mark.asyncio
    async def test_requires_mixed_case_and_digits(
        self, solana_detector: SolanaDetector
    ) -> None:
        # All lowercase — should be rejected
        msg = "aaaaaaaabbbbbbbbccccccccddddddddeeee"
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_too_short(
        self, solana_detector: SolanaDetector
    ) -> None:
        msg = "Short1Address2Here3"
        matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_chain_name(
        self, solana_detector: SolanaDetector
    ) -> None:
        assert solana_detector.chain_name == "solana"


# ---------------------------------------------------------------
# EVM Detector Tests
# ---------------------------------------------------------------


class TestEvmDetector:
    @pytest.mark.asyncio
    async def test_detects_valid_evm_address(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = "New token: 0xdAC17F958D2ee523a2206206994597C13D831ec7"
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 1
        assert (
            matches[0].contract
            == "0xdac17f958d2ee523a2206206994597c13d831ec7"
        )
        assert matches[0].chain == "evm"

    @pytest.mark.asyncio
    async def test_normalizes_to_lowercase(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = "0xDAC17F958D2EE523A2206206994597C13D831EC7"
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 1
        assert matches[0].contract == "0xdac17f958d2ee523a2206206994597c13d831ec7"

    @pytest.mark.asyncio
    async def test_ignores_zero_address(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = "0x0000000000000000000000000000000000000000"
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_ignores_dead_address(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = "0x000000000000000000000000000000000000dead"
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_deduplicates_case_insensitive(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = (
            "0xDAC17F958D2EE523A2206206994597C13D831EC7 "
            "0xdac17f958d2ee523a2206206994597c13d831ec7"
        )
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_multiple_evm_addresses(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = (
            "0xdAC17F958D2ee523a2206206994597C13D831ec7 and "
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        )
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 2

    @pytest.mark.asyncio
    async def test_rejects_short_hex(
        self, evm_detector: EvmDetector
    ) -> None:
        msg = "0x1234567890abcdef"  # only 16 hex chars
        matches = await evm_detector.detect(msg, chat_id=1, message_id=1)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_chain_name(
        self, evm_detector: EvmDetector
    ) -> None:
        assert evm_detector.chain_name == "evm"

    @pytest.mark.asyncio
    async def test_empty_message(
        self, evm_detector: EvmDetector
    ) -> None:
        matches = await evm_detector.detect("", chat_id=1, message_id=1)
        assert len(matches) == 0


# ---------------------------------------------------------------
# Cross-detector Tests
# ---------------------------------------------------------------


class TestDetectorInteraction:
    @pytest.mark.asyncio
    async def test_both_chains_in_one_message(
        self,
        solana_detector: SolanaDetector,
        evm_detector: EvmDetector,
    ) -> None:
        msg = (
            "SOL: DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 "
            "ETH: 0xdAC17F958D2ee523a2206206994597C13D831ec7"
        )
        sol_matches = await solana_detector.detect(msg, chat_id=1, message_id=1)
        evm_matches = await evm_detector.detect(msg, chat_id=1, message_id=1)

        assert len(sol_matches) >= 1
        assert len(evm_matches) == 1
        assert sol_matches[0].chain == "solana"
        assert evm_matches[0].chain == "evm"
