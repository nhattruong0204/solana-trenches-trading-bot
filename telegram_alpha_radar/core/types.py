"""Shared type aliases and enumerations."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram_alpha_radar.detectors.base_detector import BaseDetector


class Chain(str, Enum):
    """Supported blockchain networks."""

    SOLANA = "solana"
    EVM = "evm"
    # Future chains — add here:
    # BASE = "base"
    # SUI = "sui"
    # TON = "ton"

    def __str__(self) -> str:
        return self.value


# A registry is simply a list of detector instances the listener iterates.
DetectorRegistry = list["BaseDetector"]
