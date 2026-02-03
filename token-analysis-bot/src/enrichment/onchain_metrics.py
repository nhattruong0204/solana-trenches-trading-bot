"""On-chain metrics agent - fetches trading metrics from DEX APIs."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from src.config import Settings
from src.constants import ConfidenceLevel, WETH_BASE
from src.models import OnChainMetrics, TokenEvent

logger = logging.getLogger(__name__)


class OnChainMetricsAgent:
    """Fetches on-chain trading metrics."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._http_client: Optional[httpx.AsyncClient] = None

        # API endpoints
        self.dexscreener_url = "https://api.dexscreener.com/latest"
        self.geckoterminal_url = "https://api.geckoterminal.com/api/v2"

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "TokenAnalysisBot/1.0",
            },
        )
        logger.info("On-chain metrics agent initialized")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()

    async def fetch_metrics(self, event: TokenEvent) -> OnChainMetrics:
        """Fetch comprehensive on-chain metrics."""
        logger.info(f"Fetching metrics for: {event.token_address}")

        metrics = OnChainMetrics(
            token_address=event.token_address,
            pair_address=event.pair_address or "",
            fetched_at=datetime.utcnow(),
        )

        try:
            # Fetch from multiple sources in parallel
            dexscreener_task = self._fetch_dexscreener(event.token_address)
            geckoterminal_task = self._fetch_geckoterminal(event.token_address)
            holders_task = self._fetch_holder_data(event.token_address)

            results = await asyncio.gather(
                dexscreener_task,
                geckoterminal_task,
                holders_task,
                return_exceptions=True,
            )

            # Process DexScreener data (primary source)
            if not isinstance(results[0], Exception) and results[0]:
                dex_data = results[0]
                self._apply_dexscreener_data(metrics, dex_data)

            # Process GeckoTerminal data (backup/additional)
            if not isinstance(results[1], Exception) and results[1]:
                gecko_data = results[1]
                self._apply_geckoterminal_data(metrics, gecko_data)

            # Process holder data
            if not isinstance(results[2], Exception) and results[2]:
                holder_data = results[2]
                self._apply_holder_data(metrics, holder_data)

            # Calculate derived metrics
            self._calculate_derived_metrics(metrics)

            # Set confidence based on data completeness
            if metrics.liquidity_usd > 0 and metrics.holder_count > 0:
                metrics.confidence = ConfidenceLevel.HIGH
            elif metrics.price_usd > 0:
                metrics.confidence = ConfidenceLevel.MEDIUM
            else:
                metrics.confidence = ConfidenceLevel.LOW

            logger.info(
                f"Metrics fetched: FDV=${metrics.fdv_usd:,.0f}, "
                f"Liq=${metrics.liquidity_usd:,.0f}, "
                f"Holders={metrics.holder_count}"
            )

        except Exception as e:
            logger.error(f"Error fetching metrics: {e}")
            metrics.confidence = ConfidenceLevel.UNVERIFIED

        return metrics

    async def _fetch_dexscreener(self, token_address: str) -> Optional[dict[str, Any]]:
        """Fetch data from DexScreener API."""
        try:
            response = await self._http_client.get(
                f"{self.dexscreener_url}/dex/tokens/{token_address}"
            )
            response.raise_for_status()
            data = response.json()

            pairs = data.get("pairs", [])
            if not pairs:
                return None

            # Return the most liquid pair (usually first)
            # Filter for Base chain
            base_pairs = [p for p in pairs if p.get("chainId") == "base"]
            if base_pairs:
                return base_pairs[0]

            return pairs[0]

        except Exception as e:
            logger.error(f"DexScreener API error: {e}")
            return None

    async def _fetch_geckoterminal(self, token_address: str) -> Optional[dict[str, Any]]:
        """Fetch data from GeckoTerminal API."""
        try:
            response = await self._http_client.get(
                f"{self.geckoterminal_url}/networks/base/tokens/{token_address}"
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("attributes", {})

        except Exception as e:
            logger.debug(f"GeckoTerminal API error: {e}")
            return None

    async def _fetch_holder_data(self, token_address: str) -> Optional[dict[str, Any]]:
        """Fetch holder distribution data."""
        # Using Basescan API for holder data
        # Note: Requires API key for production use
        try:
            response = await self._http_client.get(
                "https://api.basescan.org/api",
                params={
                    "module": "token",
                    "action": "tokenholderlist",
                    "contractaddress": token_address,
                    "page": 1,
                    "offset": 20,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1":
                holders = data.get("result", [])
                return {
                    "holders": holders,
                    "count": len(holders),
                }

        except Exception as e:
            logger.debug(f"Holder data fetch error: {e}")

        return None

    def _apply_dexscreener_data(
        self, metrics: OnChainMetrics, data: dict[str, Any]
    ) -> None:
        """Apply DexScreener data to metrics."""
        # Price
        metrics.price_usd = float(data.get("priceUsd") or 0)
        metrics.price_native = float(data.get("priceNative") or 0)

        # Pair info
        metrics.pair_address = data.get("pairAddress", metrics.pair_address)

        # Valuation
        metrics.fdv_usd = float(data.get("fdv") or 0)
        metrics.market_cap_usd = float(data.get("marketCap") or 0)

        # Liquidity
        liquidity = data.get("liquidity", {})
        metrics.liquidity_usd = float(liquidity.get("usd") or 0)
        metrics.liquidity_native = float(liquidity.get("base") or 0)

        # Volume
        volume = data.get("volume", {})
        metrics.volume_24h_usd = float(volume.get("h24") or 0)
        metrics.volume_1h_usd = float(volume.get("h1") or 0)

        # Transactions
        txns = data.get("txns", {})
        h24_txns = txns.get("h24", {})
        metrics.buys_24h = int(h24_txns.get("buys") or 0)
        metrics.sells_24h = int(h24_txns.get("sells") or 0)

        # Price changes
        price_change = data.get("priceChange", {})
        metrics.price_change_1h = float(price_change.get("h1") or 0)
        metrics.price_change_6h = float(price_change.get("h6") or 0)
        metrics.price_change_24h = float(price_change.get("h24") or 0)

        # Pair creation time
        pair_created = data.get("pairCreatedAt")
        if pair_created:
            try:
                metrics.pair_created_at = datetime.fromtimestamp(pair_created / 1000)
                age_seconds = (datetime.utcnow() - metrics.pair_created_at).total_seconds()
                metrics.token_age_hours = age_seconds / 3600
            except (ValueError, TypeError):
                pass

    def _apply_geckoterminal_data(
        self, metrics: OnChainMetrics, data: dict[str, Any]
    ) -> None:
        """Apply GeckoTerminal data to metrics (fills gaps)."""
        # Only fill if not already set
        if metrics.price_usd == 0:
            metrics.price_usd = float(data.get("price_usd") or 0)

        if metrics.fdv_usd == 0:
            metrics.fdv_usd = float(data.get("fdv_usd") or 0)

        if metrics.market_cap_usd == 0:
            metrics.market_cap_usd = float(data.get("market_cap_usd") or 0)

        if metrics.volume_24h_usd == 0:
            metrics.volume_24h_usd = float(data.get("volume_usd", {}).get("h24") or 0)

    def _apply_holder_data(
        self, metrics: OnChainMetrics, data: dict[str, Any]
    ) -> None:
        """Apply holder data to metrics."""
        holders = data.get("holders", [])
        metrics.holder_count = data.get("count", len(holders))

        # Calculate top 10 holder percentage
        if holders:
            total_balance = sum(
                float(h.get("TokenHolderQuantity", 0)) for h in holders[:20]
            )
            top_10_balance = sum(
                float(h.get("TokenHolderQuantity", 0)) for h in holders[:10]
            )

            if total_balance > 0:
                metrics.top_10_holder_pct = (top_10_balance / total_balance) * 100

    def _calculate_derived_metrics(self, metrics: OnChainMetrics) -> None:
        """Calculate derived metrics."""
        # Circulating supply estimation
        if metrics.price_usd > 0 and metrics.market_cap_usd > 0:
            metrics.circulating_supply = int(metrics.market_cap_usd / metrics.price_usd)

        # Slippage estimation based on liquidity
        if metrics.liquidity_usd > 0:
            # Rough estimation: slippage % = trade_size / (2 * liquidity) * 100
            # For 1% slippage with $X liquidity, max trade = 2% of liquidity
            metrics.slippage_1_pct_buy = min(
                metrics.liquidity_usd * 0.02, 50000
            )  # Max $50k
            metrics.slippage_2_pct_buy = min(metrics.liquidity_usd * 0.04, 100000)
            metrics.slippage_5_pct_buy = min(metrics.liquidity_usd * 0.10, 250000)

    async def get_smart_wallet_activity(
        self, token_address: str
    ) -> dict[str, Any]:
        """Check for smart wallet/whale activity on the token."""
        result = {
            "smart_wallet_count": 0,
            "smart_wallet_addresses": [],
            "whale_holdings_pct": 0.0,
        }

        try:
            # This would integrate with a smart wallet database
            # Common sources: Nansen, Arkham, DeBank, etc.
            # Placeholder implementation

            # Check DexScreener for whale trades
            response = await self._http_client.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            )

            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])

                if pairs:
                    # Look for large transactions
                    # This is a simplified check
                    txns = pairs[0].get("txns", {}).get("h24", {})
                    buys = txns.get("buys", 0)
                    sells = txns.get("sells", 0)

                    # If buy/sell ratio is very skewed, might indicate whale activity
                    if buys > 0 and sells > 0:
                        ratio = buys / sells
                        if ratio > 5 or ratio < 0.2:
                            result["smart_wallet_count"] = 1

        except Exception as e:
            logger.debug(f"Smart wallet check error: {e}")

        return result

    async def refresh_metrics(
        self, metrics: OnChainMetrics
    ) -> OnChainMetrics:
        """Refresh metrics just before posting (to get latest data)."""
        event = TokenEvent(
            token_address=metrics.token_address,
            pair_address=metrics.pair_address,
            source=EventSource.MANUAL,
            detected_at=datetime.utcnow(),
        )
        return await self.fetch_metrics(event)


# Import for type hint
from src.models import EventSource
