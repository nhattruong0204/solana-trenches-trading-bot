"""Telegram MTProto listener using Telethon user session."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from telegram_alpha_radar.config import FilterConfig, TelegramConfig

logger = logging.getLogger(__name__)

# Type for the async callback the app registers
MessageCallback = Callable[[events.NewMessage.Event], Awaitable[None]]


class TelegramListener:
    """Connects via Telethon user account and dispatches every incoming message.

    Handles:
    * Auto-reconnect
    * Flood-wait backoff
    * Message filtering (length, forwarded)
    """

    def __init__(
        self,
        config: TelegramConfig,
        filters: FilterConfig,
        on_message: MessageCallback,
    ) -> None:
        self._config = config
        self._filters = filters
        self._on_message = on_message
        self._client: TelegramClient | None = None

    @property
    def client(self) -> TelegramClient | None:
        return self._client

    async def start(self) -> TelegramClient:
        """Authenticate and begin listening."""
        self._client = TelegramClient(
            self._config.session_name,
            self._config.api_id,
            self._config.api_hash,
            auto_reconnect=True,
            retry_delay=5,
            connection_retries=10,
        )

        await self._client.start(phone=self._config.phone)
        me = await self._client.get_me()
        logger.info(
            "Authenticated as %s (id=%d)",
            me.username or me.first_name,
            me.id,
        )

        # Register handler for ALL incoming messages
        # (private, groups, channels)
        self._client.add_event_handler(
            self._handle_event,
            events.NewMessage(incoming=True),
        )

        logger.info("Listener registered — monitoring all incoming messages")
        return self._client

    async def _handle_event(self, event: events.NewMessage.Event) -> None:
        """Filter and dispatch a single incoming message."""
        try:
            text = event.raw_text
            if not text:
                return

            # Optional: skip forwarded messages
            if self._filters.ignore_forwarded and event.message.forward:
                return

            # Optional: minimum length
            if len(text) < self._filters.min_message_length:
                return

            await self._on_message(event)

        except FloodWaitError as e:
            logger.warning(
                "Telegram flood-wait: sleeping %d seconds", e.seconds
            )
            import asyncio

            await asyncio.sleep(e.seconds)

        except Exception:
            logger.exception("Error handling message event")

    async def run_until_disconnected(self) -> None:
        """Block until the client disconnects."""
        if self._client:
            await self._client.run_until_disconnected()

    async def stop(self) -> None:
        """Gracefully disconnect."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            logger.info("Telegram client disconnected")
