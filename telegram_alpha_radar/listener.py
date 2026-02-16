"""Telethon-based Telegram message listener.

Connects using a user account (MTProto) and listens to all incoming
messages from private chats, groups, and channels.
"""

import logging
import asyncio
from typing import Callable, Awaitable

from telethon import TelegramClient, events
from telethon.tl.types import Message
from telethon.errors import FloodWaitError

from .config import TelegramConfig, FilterConfig

logger = logging.getLogger(__name__)

# Type alias for the callback that processes each message
MessageCallback = Callable[[Message], Awaitable[None]]


class TelegramListener:
    """Listens to all incoming Telegram messages via a user account."""

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

    async def start(self) -> None:
        """Authenticate and register the event handler."""
        logger.info("Starting Telegram client (session=%s)", self._config.session_name)
        self._client = TelegramClient(
            self._config.session_name,
            self._config.api_id,
            self._config.api_hash,
            auto_reconnect=True,
            retry_delay=5,
        )

        await self._client.start(phone=self._config.phone)
        me = await self._client.get_me()
        logger.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)

        # Register handler for ALL new messages (incoming only)
        @self._client.on(events.NewMessage(incoming=True))
        async def _handler(event: events.NewMessage.Event) -> None:
            await self._handle_event(event)

        logger.info("Message handler registered — listening to all chats")

    async def _handle_event(self, event: events.NewMessage.Event) -> None:
        """Filter and dispatch incoming messages."""
        msg: Message = event.message

        # Skip empty messages
        if not msg.text:
            return

        # Optional: ignore forwarded messages
        if self._filters.ignore_forwarded and msg.forward is not None:
            logger.debug("Skipping forwarded message %s", msg.id)
            return

        # Optional: minimum message length
        if self._filters.min_message_length > 0:
            if len(msg.text) < self._filters.min_message_length:
                return

        try:
            await self._on_message(msg)
        except FloodWaitError as e:
            logger.warning("Flood wait: sleeping %s seconds", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception:
            logger.exception("Error processing message %s from chat %s", msg.id, msg.chat_id)

    async def run_until_disconnected(self) -> None:
        """Block until the client disconnects."""
        if self._client:
            logger.info("Listener running — press Ctrl+C to stop")
            await self._client.run_until_disconnected()

    async def stop(self) -> None:
        """Disconnect the Telegram client."""
        if self._client:
            await self._client.disconnect()
            logger.info("Telegram client disconnected")
