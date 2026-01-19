#!/usr/bin/env python3
"""
Main entry point for the Solana Trading Bot.

This script serves as the application entry point, providing
backward compatibility with the original trading_bot.py interface.
"""

import sys
from pathlib import Path

# Ensure src package is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
