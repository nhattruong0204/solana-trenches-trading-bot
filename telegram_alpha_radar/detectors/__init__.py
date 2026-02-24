"""Pluggable contract detectors."""

from telegram_alpha_radar.detectors.base_detector import BaseDetector
from telegram_alpha_radar.detectors.solana_detector import SolanaDetector
from telegram_alpha_radar.detectors.evm_detector import EvmDetector

__all__ = ["BaseDetector", "SolanaDetector", "EvmDetector"]
