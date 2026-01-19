"""
Solana Trading Bot - Professional Auto-Trading System

A production-ready trading bot for Solana tokens that monitors
Telegram signals and executes trades via GMGN bot.
"""

__version__ = "1.0.0"
__author__ = "Truong Nguyen"
__email__ = "contact@example.com"

from src.config import Settings
from src.bot import TradingBot

__all__ = ["Settings", "TradingBot", "__version__"]
