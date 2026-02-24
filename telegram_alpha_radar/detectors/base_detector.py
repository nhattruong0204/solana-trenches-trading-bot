"""Abstract base class for chain-specific contract detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from telegram_alpha_radar.core.models import TokenMatch


class BaseDetector(ABC):
    """Every chain detector must implement ``detect``.

    To add a new chain:
        1. Create ``mychain_detector.py`` in this package.
        2. Subclass ``BaseDetector``.
        3. Implement ``detect()`` and ``chain_name``.
        4. Register the detector in ``app.py``.
    """

    @property
    @abstractmethod
    def chain_name(self) -> str:
        """Return the canonical chain identifier (e.g. 'solana', 'evm')."""
        ...

    @abstractmethod
    async def detect(
        self,
        message: str,
        chat_id: int,
        message_id: int,
    ) -> list[TokenMatch]:
        """Extract all token contract addresses from *message*.

        Parameters
        ----------
        message:
            Raw message text.
        chat_id:
            Telegram chat the message belongs to.
        message_id:
            Telegram message id within the chat.

        Returns
        -------
        list[TokenMatch]
            Zero or more matches found in the message.
        """
        ...
