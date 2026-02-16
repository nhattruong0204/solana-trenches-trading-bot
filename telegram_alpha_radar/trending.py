"""Trending token detection logic.

Periodically queries the storage layer to find tokens that exceed
the configured mention and unique-chat thresholds within a rolling
time window. Optionally computes velocity (current vs. previous window).
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

from .config import TrendingConfig, DexscreenerConfig
from .storage import Storage, TrendingToken

logger = logging.getLogger(__name__)


def _compute_score(token: TrendingToken) -> float:
    """Simple scoring formula: mentions * unique_chats * (1 + velocity_ratio).

    This prioritises tokens that appear across many distinct groups
    with an acceleration factor from velocity.
    """
    base = token.mention_count * token.unique_chats
    velocity_boost = 1.0 + token.velocity_ratio
    return base * velocity_boost


async def _check_liquidity(
    contract: str,
    chain: str,
    config: DexscreenerConfig,
    session: aiohttp.ClientSession,
) -> bool:
    """Validate token liquidity via Dexscreener API.

    Returns True if liquidity meets the threshold or if the check is disabled/fails.
    """
    url = f"{config.api_base_url}/{contract}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning(
                    "Dexscreener returned %s for %s — skipping liquidity check",
                    resp.status,
                    contract,
                )
                return True  # fail open
            data = await resp.json()
    except Exception:
        logger.warning("Dexscreener request failed for %s — skipping check", contract)
        return True  # fail open

    pairs = data.get("pairs") or []
    if not pairs:
        logger.debug("No pairs found on Dexscreener for %s", contract)
        return False

    # Check if any pair meets the liquidity threshold
    for pair in pairs:
        liquidity = pair.get("liquidity", {}).get("usd", 0)
        if liquidity and float(liquidity) >= config.min_liquidity_usd:
            logger.debug(
                "Contract %s has sufficient liquidity ($%.0f)", contract, liquidity
            )
            return True

    max_liq = max(
        (float(p.get("liquidity", {}).get("usd", 0) or 0) for p in pairs), default=0
    )
    logger.info(
        "Contract %s rejected — max liquidity $%.0f < $%.0f threshold",
        contract,
        max_liq,
        config.min_liquidity_usd,
    )
    return False


async def detect_trending_tokens(
    storage: Storage,
    trending_config: TrendingConfig,
    dex_config: Optional[DexscreenerConfig] = None,
) -> list[TrendingToken]:
    """Detect currently trending tokens.

    Steps:
        1. Query mentions within the current time window.
        2. Compute velocity vs. previous window.
        3. Score and rank tokens.
        4. Optionally filter by Dexscreener liquidity.

    Returns:
        Ranked list of TrendingToken sorted by score descending.
    """
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=trending_config.window_minutes)
    since = now - window

    # Step 1: Get candidates
    candidates = await storage.get_trending(
        since=since,
        min_mentions=trending_config.min_mentions,
        min_unique_chats=trending_config.min_unique_chats,
    )

    if not candidates:
        return []

    # Step 2: Compute velocity ratio for each candidate
    prev_window_start = since - window
    prev_window_end = since
    for token in candidates:
        prev_count = await storage.get_mention_count_in_range(
            token.contract, prev_window_start, prev_window_end
        )
        if prev_count > 0:
            token.velocity_ratio = (token.mention_count - prev_count) / prev_count
        else:
            # First appearance → high velocity signal
            token.velocity_ratio = float(token.mention_count)

    # Step 3: Score
    for token in candidates:
        token.score = _compute_score(token)

    # Step 4: Liquidity filter
    if dex_config and dex_config.enabled:
        filtered: list[TrendingToken] = []
        async with aiohttp.ClientSession() as session:
            for token in candidates:
                passes = await _check_liquidity(
                    token.contract, token.chain, dex_config, session
                )
                if passes:
                    filtered.append(token)
                else:
                    logger.info(
                        "Filtered out %s (%s) — insufficient liquidity",
                        token.contract,
                        token.chain,
                    )
        candidates = filtered

    # Sort by score descending
    candidates.sort(key=lambda t: t.score, reverse=True)

    logger.info("Detected %d trending token(s)", len(candidates))
    for t in candidates[:5]:
        logger.info(
            "  %s (%s) — mentions=%d chats=%d velocity=%.2f score=%.1f",
            t.contract[:12] + "…",
            t.chain,
            t.mention_count,
            t.unique_chats,
            t.velocity_ratio,
            t.score,
        )

    return candidates
