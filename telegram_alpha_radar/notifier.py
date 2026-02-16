"""Notification system — sends trending token alerts to the user via Telegram.

Uses the same Telethon user client to send messages to "Saved Messages"
(i.e., to yourself). Implements a cooldown window to avoid duplicate alerts.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from telethon import TelegramClient

from .config import TrendingConfig
from .storage import TrendingToken

logger = logging.getLogger(__name__)


class Notifier:
    """Sends formatted trending-token alerts and manages cooldowns."""

    def __init__(self, client: TelegramClient, config: TrendingConfig) -> None:
        self._client = client
        self._config = config
        # contract -> last alert timestamp
        self._cooldowns: dict[str, datetime] = {}

    def _is_on_cooldown(self, contract: str) -> bool:
        """Check if an alert for this contract is still within the cooldown window."""
        last_alert = self._cooldowns.get(contract)
        if last_alert is None:
            return False
        elapsed = datetime.now(timezone.utc) - last_alert
        return elapsed < timedelta(minutes=self._config.alert_cooldown_minutes)

    def _set_cooldown(self, contract: str) -> None:
        """Record the current time as the last alert time for a contract."""
        self._cooldowns[contract] = datetime.now(timezone.utc)

    def _format_alert(self, token: TrendingToken) -> str:
        """Build the alert message text."""
        chain_label = token.chain.upper()
        if token.chain == "evm":
            chain_label = "EVM"
        elif token.chain == "solana":
            chain_label = "Solana"

        return (
            f"\U0001f525 **Trending Token Detected**\n\n"
            f"**Contract:** `{token.contract}`\n"
            f"**Chain:** {chain_label}\n"
            f"**Mentions ({self._config.window_minutes}m):** {token.mention_count}\n"
            f"**Unique Groups:** {token.unique_chats}\n"
            f"**Velocity:** {token.velocity_ratio:.2f}x\n"
            f"**Score:** {token.score:.1f}"
        )

    async def notify(self, tokens: list[TrendingToken]) -> int:
        """Send alerts for trending tokens that are not on cooldown.

        Args:
            tokens: List of trending tokens to potentially alert on.

        Returns:
            Number of alerts actually sent.
        """
        sent = 0
        for token in tokens:
            if self._is_on_cooldown(token.contract):
                logger.debug(
                    "Skipping alert for %s — on cooldown", token.contract[:16]
                )
                continue

            message = self._format_alert(token)
            try:
                # Send to "Saved Messages" (yourself)
                await self._client.send_message("me", message, parse_mode="md")
                self._set_cooldown(token.contract)
                sent += 1
                logger.info(
                    "Alert sent for %s (%s) — score=%.1f",
                    token.contract[:16],
                    token.chain,
                    token.score,
                )
            except Exception:
                logger.exception("Failed to send alert for %s", token.contract[:16])

        if sent:
            logger.info("Sent %d alert(s) out of %d trending token(s)", sent, len(tokens))
        return sent

    def cleanup_expired_cooldowns(self) -> None:
        """Remove cooldown entries that have expired — prevents unbounded memory growth."""
        now = datetime.now(timezone.utc)
        cutoff = timedelta(minutes=self._config.alert_cooldown_minutes)
        expired = [k for k, v in self._cooldowns.items() if now - v > cutoff]
        for k in expired:
            del self._cooldowns[k]
        if expired:
            logger.debug("Cleaned up %d expired cooldown(s)", len(expired))
