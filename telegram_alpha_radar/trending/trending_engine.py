"""Trending detection engine with velocity scoring and optional liquidity filter."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from telegram_alpha_radar.config import DexscreenerConfig, TrendingConfig
from telegram_alpha_radar.core.models import TrendingToken
from telegram_alpha_radar.core.utils import utcnow
from telegram_alpha_radar.storage.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class TrendingEngine:
    """Detects trending tokens across all chains or per-chain.

    Scoring formula:
        score = mentions * 2 + unique_chats * 3 + velocity * 5

    Velocity is computed by comparing the current window with the
    previous window of the same length.
    """

    def __init__(
        self,
        repository: BaseRepository,
        trending_config: TrendingConfig,
        dexscreener_config: DexscreenerConfig | None = None,
    ) -> None:
        self._repo = repository
        self._cfg = trending_config
        self._dex = dexscreener_config

    async def detect(
        self,
        chain: str | None = None,
    ) -> list[TrendingToken]:
        """Return scored and ranked trending tokens.

        Parameters
        ----------
        chain:
            If provided, only consider tokens from this chain.
            Pass ``None`` to rank all chains together.
        """
        now = utcnow()
        window = timedelta(minutes=self._cfg.window_minutes)
        since = now - window

        # Step 1: get tokens meeting threshold
        tokens = await self._repo.get_trending(
            since=since,
            min_mentions=self._cfg.min_mentions,
            min_unique_chats=self._cfg.min_unique_chats,
            chain=chain,
        )

        if not tokens:
            return []

        # Step 2: compute velocity for each token
        prev_start = since - window
        prev_end = since

        for token in tokens:
            prev_count = await self._repo.get_mention_count(
                contract=token.contract,
                since=prev_start,
                until=prev_end,
            )
            if prev_count == 0:
                # First appearance — velocity equals current count
                token.velocity = float(token.mention_count)
            else:
                token.velocity = (
                    (token.mention_count - prev_count) / prev_count
                )

        # Step 3: compute score
        for token in tokens:
            token.compute_score()

        # Step 4: optional Dexscreener liquidity filter
        if self._dex and self._dex.enabled:
            tokens = await self._filter_by_liquidity(tokens)

        # Step 5: sort by score descending
        tokens.sort(key=lambda t: t.score, reverse=True)

        if tokens:
            top = tokens[:5]
            logger.info(
                "Trending tokens (top %d): %s",
                len(top),
                ", ".join(
                    f"{t.contract[:8]}..({t.chain} s={t.score:.1f})"
                    for t in top
                ),
            )

        return tokens

    async def detect_by_chain(self) -> dict[str, list[TrendingToken]]:
        """Return trending tokens grouped by chain (independent ranking)."""
        from telegram_alpha_radar.core.types import Chain

        results: dict[str, list[TrendingToken]] = {}
        for chain in Chain:
            tokens = await self.detect(chain=str(chain))
            if tokens:
                results[str(chain)] = tokens
        return results

    # ------------------------------------------------------------------
    # Dexscreener liquidity check
    # ------------------------------------------------------------------

    async def _filter_by_liquidity(
        self,
        tokens: list[TrendingToken],
    ) -> list[TrendingToken]:
        """Remove tokens that don't meet minimum liquidity on Dexscreener."""
        assert self._dex is not None
        passed: list[TrendingToken] = []

        for token in tokens:
            if await self._check_liquidity(token.contract):
                passed.append(token)
            else:
                logger.debug(
                    "Filtered out %s — below liquidity threshold",
                    token.contract[:12],
                )

        return passed

    async def _check_liquidity(self, contract: str) -> bool:
        """Query Dexscreener for token liquidity. Fail-open on errors."""
        assert self._dex is not None
        url = f"{self._dex.api_url}/{contract}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Dexscreener returned %d for %s — passing through",
                            resp.status,
                            contract[:12],
                        )
                        return True
                    data = await resp.json()

            pairs = data.get("pairs") or []
            for pair in pairs:
                liquidity = pair.get("liquidity", {})
                usd = liquidity.get("usd", 0)
                if usd and float(usd) >= self._dex.min_liquidity_usd:
                    return True

            return len(pairs) == 0  # no pairs found — pass through

        except Exception:
            logger.warning(
                "Dexscreener lookup failed for %s — passing through",
                contract[:12],
            )
            return True
