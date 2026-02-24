"""Send trending-token alerts to Telegram Saved Messages with cooldown."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from telethon import TelegramClient

from telegram_alpha_radar.config import TrendingConfig
from telegram_alpha_radar.core.models import TrendingToken
from telegram_alpha_radar.core.utils import utcnow

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Formats and sends alerts, respecting a per-contract cooldown window."""

    def __init__(
        self,
        client: TelegramClient,
        config: TrendingConfig,
        dry_run: bool = False,
    ) -> None:
        self._client = client
        self._config = config
        self._dry_run = dry_run
        # contract -> last alert time
        self._cooldowns: dict[str, datetime] = {}

    def is_on_cooldown(self, contract: str) -> bool:
        """Check if the contract was alerted within the cooldown window."""
        last = self._cooldowns.get(contract)
        if last is None:
            return False
        elapsed = utcnow() - last
        return elapsed < timedelta(minutes=self._config.cooldown_minutes)

    async def notify(self, tokens: list[TrendingToken]) -> int:
        """Send alerts for tokens not on cooldown. Returns count sent."""
        sent = 0

        for token in tokens:
            if self.is_on_cooldown(token.contract):
                logger.debug(
                    "Skipping %s — on cooldown", token.contract[:12]
                )
                continue

            msg = self._format_alert(token)

            if self._dry_run:
                logger.info("[DRY-RUN] Would send alert:\n%s", msg)
            else:
                try:
                    await self._client.send_message("me", msg)
                    logger.info(
                        "Alert sent for %s (%s, score=%.1f)",
                        token.contract[:12],
                        token.chain,
                        token.score,
                    )
                except Exception:
                    logger.exception(
                        "Failed to send alert for %s", token.contract[:12]
                    )
                    continue

            self._cooldowns[token.contract] = utcnow()
            sent += 1

        return sent

    def cleanup_expired_cooldowns(self) -> int:
        """Remove expired entries to prevent memory bloat."""
        now = utcnow()
        limit = timedelta(minutes=self._config.cooldown_minutes)
        expired = [
            k for k, v in self._cooldowns.items() if (now - v) >= limit
        ]
        for k in expired:
            del self._cooldowns[k]
        return len(expired)

    @staticmethod
    def _format_alert(token: TrendingToken) -> str:
        chain_display = token.chain.upper()
        velocity_pct = f"{token.velocity * 100:+.0f}%" if token.velocity else "NEW"

        return (
            f"**TRENDING TOKEN DETECTED**\n"
            f"\n"
            f"**Chain:** {chain_display}\n"
            f"**Contract:** `{token.contract}`\n"
            f"**Mentions (5m):** {token.mention_count}\n"
            f"**Unique Groups:** {token.unique_chats}\n"
            f"**Velocity:** {velocity_pct}\n"
            f"**Score:** {token.score:.1f}\n"
        )
