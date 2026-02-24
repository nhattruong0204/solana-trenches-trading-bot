"""EVM contract address detector (Ethereum, BSC, Polygon, Base, Arbitrum, etc.)."""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from telegram_alpha_radar.core.models import TokenMatch
from telegram_alpha_radar.core.types import Chain
from telegram_alpha_radar.core.utils import utcnow
from telegram_alpha_radar.detectors.base_detector import BaseDetector

logger = logging.getLogger(__name__)

# Standard EVM address: 0x followed by exactly 40 hex characters
_EVM_PATTERN = re.compile(r"\b(0x[0-9a-fA-F]{40})\b")

# Known burn / zero addresses
_BLACKLISTED_ADDRESSES: frozenset[str] = frozenset(
    {
        "0x0000000000000000000000000000000000000000",
        "0xffffffffffffffffffffffffffffffffffffffff",
        "0x000000000000000000000000000000000000dead",
        "0xdead000000000000000000000000000000000000",
    }
)


class EvmDetector(BaseDetector):
    """Detect EVM-compatible contract addresses (0x + 40 hex)."""

    _chain: ClassVar[str] = str(Chain.EVM)

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

        for m in _EVM_PATTERN.finditer(message):
            raw = m.group(1)
            # Normalize to lowercase (EVM addresses are case-insensitive)
            normalized = raw.lower()

            if normalized in seen:
                continue

            if normalized in _BLACKLISTED_ADDRESSES:
                continue

            seen.add(normalized)
            matches.append(
                TokenMatch(
                    contract=normalized,
                    chain=self._chain,
                    chat_id=chat_id,
                    message_id=message_id,
                    timestamp=now,
                )
            )

        if matches:
            logger.debug(
                "EVM detector found %d contract(s) in chat=%d msg=%d",
                len(matches),
                chat_id,
                message_id,
            )

        return matches
