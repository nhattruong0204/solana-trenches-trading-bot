"""Contract address detection from message text.

Detects Solana (Base58, 32-44 chars) and EVM (0x + 40 hex) contract addresses.
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# EVM: 0x followed by exactly 40 hex characters
_EVM_PATTERN = re.compile(r"\b(0x[0-9a-fA-F]{40})\b")

# Solana: Base58 characters, 32-44 characters long.
# Base58 alphabet: 123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz
_SOLANA_PATTERN = re.compile(
    r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b"
)

# Common false-positive strings for Solana pattern
_SOLANA_FALSE_POSITIVES: set[str] = {
    # Common English words / abbreviations that happen to match Base58
    "Bitcoin",
    "Ethereum",
    "Solana",
    "Polygon",
    "Avalanche",
    "Arbitrum",
    "Optimism",
    # Common Solana program IDs and system addresses to skip
    "11111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "So11111111111111111111111111111111111111112",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "SysvarRent111111111111111111111111111111111",
    "SysvarC1ock11111111111111111111111111111111",
    # Pump.fun related
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
}

# Zero address for EVM
_EVM_FALSE_POSITIVES: set[str] = {
    "0x0000000000000000000000000000000000000000",
    "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "0xffffffffffffffffffffffffffffffffffffffff",
}


@dataclass(frozen=True)
class DetectedContract:
    """A contract address extracted from a message."""

    address: str
    chain: str  # "solana" or "evm"


def extract_contracts(text: str) -> list[DetectedContract]:
    """Extract unique contract addresses from message text.

    Args:
        text: The raw message text to parse.

    Returns:
        Deduplicated list of detected contracts.
    """
    if not text:
        return []

    seen: set[str] = set()
    results: list[DetectedContract] = []

    # --- EVM detection ---
    for match in _EVM_PATTERN.finditer(text):
        raw = match.group(1)
        normalized = raw.lower()
        if normalized in _EVM_FALSE_POSITIVES:
            continue
        if normalized not in seen:
            seen.add(normalized)
            results.append(DetectedContract(address=normalized, chain="evm"))

    # --- Solana detection ---
    for match in _SOLANA_PATTERN.finditer(text):
        raw = match.group(1)
        if raw in _SOLANA_FALSE_POSITIVES:
            continue
        # Additional heuristics: must contain both uppercase and lowercase,
        # and at least one digit to reduce false positives on plain words.
        has_upper = any(c.isupper() for c in raw)
        has_lower = any(c.islower() for c in raw)
        has_digit = any(c.isdigit() for c in raw)
        if not (has_upper and has_lower and has_digit):
            continue
        # Skip if it looks like a URL path component or common word
        if len(raw) < 32:
            continue
        if raw not in seen:
            seen.add(raw)
            results.append(DetectedContract(address=raw, chain="solana"))

    if results:
        logger.debug("Extracted %d contract(s) from message", len(results))

    return results
