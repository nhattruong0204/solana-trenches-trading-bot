"""Solana contract address detector."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from telegram_alpha_radar.core.models import TokenMatch
from telegram_alpha_radar.core.types import Chain
from telegram_alpha_radar.core.utils import utcnow
from telegram_alpha_radar.detectors.base_detector import BaseDetector

logger = logging.getLogger(__name__)

# Base58 alphabet (no 0, O, I, l)
_BASE58_PATTERN = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")

# Known false-positive words that match Base58 pattern
_FALSE_POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "Bitcoin",
        "bitcoin",
        "Ethereum",
        "ethereum",
        "Solana",
        "solana",
        "Polygon",
        "polygon",
        "Avalanche",
        "avalanche",
        "Cardano",
        "cardano",
        "Polkadot",
        "polkadot",
        "Chainlink",
        "chainlink",
        "Uniswap",
        "uniswap",
        "Airdrop",
        "airdrop",
        "Binance",
        "binance",
        "Coinbase",
        "coinbase",
        "Bullish",
        "bullish",
        "Bearish",
        "bearish",
        "Moonshot",
        "moonshot",
        "Diamond",
        "diamond",
        "Phantom",
        "phantom",
        "Jupiter",
        "jupiter",
        "Raydium",
        "raydium",
        "Meteora",
        "meteora",
        "Telegram",
        "telegram",
        "channel",
        "Channel",
        "private",
        "Private",
        "Welcome",
        "welcome",
        "Trading",
        "trading",
        "profits",
        "Profits",
        "million",
        "Million",
        "billion",
        "Billion",
    }
)

# System program addresses to ignore
_SYSTEM_ADDRESSES: frozenset[str] = frozenset(
    {
        "11111111111111111111111111111111",
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "So11111111111111111111111111111111111111112",
        "SysvarC1ock11111111111111111111111111111111",
        "SysvarRent111111111111111111111111111111111",
        "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
        "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
    }
)


class SolanaDetector(BaseDetector):
    """Detect Solana contract addresses (Base58, 32-44 chars)."""

    _chain: ClassVar[str] = str(Chain.SOLANA)

    @property
    def chain_name(self) -> str:
        return self._chain

    async def detect(
        self,
        message: str,
        chat_id: int,
        message_id: int,
    ) -> list[TokenMatch]:
        matches: list[TokenMatch] = []
        seen: set[str] = set()
        now = utcnow()

        for m in _BASE58_PATTERN.finditer(message):
            candidate = m.group(1)

            # Length guard
            if len(candidate) < 32 or len(candidate) > 44:
                continue

            # Dedup within same message
            if candidate in seen:
                continue

            # False-positive word list
            if candidate in _FALSE_POSITIVE_WORDS:
                continue

            # System addresses
            if candidate in _SYSTEM_ADDRESSES:
                continue

            # Heuristic: real Solana addresses contain a mix of
            # uppercase, lowercase, and digits
            has_upper = any(c.isupper() for c in candidate)
            has_lower = any(c.islower() for c in candidate)
            has_digit = any(c.isdigit() for c in candidate)
            if not (has_upper and has_lower and has_digit):
                continue

            seen.add(candidate)
            matches.append(
                TokenMatch(
                    contract=candidate,
                    chain=self._chain,
                    chat_id=chat_id,
                    message_id=message_id,
                    timestamp=now,
                )
            )

        if matches:
            logger.debug(
                "Solana detector found %d contract(s) in chat=%d msg=%d",
                len(matches),
                chat_id,
                message_id,
            )

        return matches
