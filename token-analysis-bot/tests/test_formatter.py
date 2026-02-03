"""Tests for message formatter."""

import pytest

from src.constants import RiskRating
from src.delivery.formatter import MessageFormatter
from src.models import Claim, TokenBreakdown
from src.synthesis.prompts import format_fdv, format_pros_cons


class TestMessageFormatter:
    """Tests for MessageFormatter."""

    def test_format_breakdown(self, sample_breakdown):
        """Test formatting a token breakdown."""
        message = MessageFormatter.format_breakdown(sample_breakdown)

        assert "$TEST" in message
        assert "1.0M" in message
        assert "test_dev" in message
        assert "dexscreener.com" in message

    def test_format_includes_pros(self, sample_breakdown):
        """Test that pros are included."""
        message = MessageFormatter.format_breakdown(sample_breakdown)

        assert "+" in message
        assert "Good liquidity" in message

    def test_format_includes_cons(self, sample_breakdown):
        """Test that cons are included."""
        message = MessageFormatter.format_breakdown(sample_breakdown)

        assert "-" in message

    def test_format_compact(self, sample_breakdown):
        """Test compact format."""
        message = MessageFormatter.format_compact(sample_breakdown)

        assert "$TEST" in message
        assert "FDV" in message
        assert "Liq:" in message

    def test_format_alert(self, sample_breakdown):
        """Test alert format."""
        message = MessageFormatter.format_alert(sample_breakdown, "New listing")

        assert "New Token Detected" in message
        assert "New listing" in message

    def test_format_approval_request(self, sample_breakdown):
        """Test approval request format."""
        reasons = ["Low confidence", "New developer"]
        message = MessageFormatter.format_approval_request(sample_breakdown, reasons)

        assert "APPROVAL REQUIRED" in message
        assert "Low confidence" in message
        assert "/approve" in message

    def test_format_stats(self):
        """Test stats format."""
        stats = {
            "total_analyzed": 100,
            "published": 80,
            "rejected": 15,
            "pending_approval": 5,
            "green": 30,
            "yellow": 40,
            "orange": 8,
            "red": 2,
        }
        message = MessageFormatter.format_stats(stats)

        assert "100" in message
        assert "GREEN: 30" in message

    def test_escape_markdown(self):
        """Test markdown escaping."""
        text = "Test_with_underscores and *asterisks*"
        escaped = MessageFormatter._escape_markdown(text)

        assert "\\_" in escaped
        assert "\\*" in escaped

    def test_truncate_text(self):
        """Test text truncation."""
        long_text = "a" * 100
        truncated = MessageFormatter._truncate_text(long_text, 50)

        assert len(truncated) == 50
        assert truncated.endswith("...")

    def test_truncate_short_text(self):
        """Test that short text is not truncated."""
        short_text = "Short text"
        result = MessageFormatter._truncate_text(short_text, 50)

        assert result == short_text


class TestFormatHelpers:
    """Tests for format helper functions."""

    def test_format_fdv_billions(self):
        """Test FDV formatting for billions."""
        assert format_fdv(1_500_000_000) == "1.5B"
        assert format_fdv(10_000_000_000) == "10.0B"

    def test_format_fdv_millions(self):
        """Test FDV formatting for millions."""
        assert format_fdv(1_500_000) == "1.5M"
        assert format_fdv(500_000) == "0.5M"

    def test_format_fdv_thousands(self):
        """Test FDV formatting for thousands."""
        assert format_fdv(50_000) == "50.0K"
        assert format_fdv(1_500) == "1.5K"

    def test_format_fdv_small(self):
        """Test FDV formatting for small numbers."""
        assert format_fdv(500) == "500"
        assert format_fdv(99) == "99"

    def test_format_pros_cons_list(self):
        """Test formatting pros/cons list."""
        items = [
            {"text": "Good liquidity", "confidence": 0.9},
            {"text": "Active developer", "confidence": 0.8},
        ]

        pros = format_pros_cons(items, is_pro=True)
        assert "+ Good liquidity" in pros
        assert "+ Active developer" in pros

        cons = format_pros_cons(items, is_pro=False)
        assert "- Good liquidity" in cons


class TestRiskEmoji:
    """Tests for risk rating emojis."""

    def test_green_emoji(self):
        """Test green rating emoji."""
        assert RiskRating.GREEN.emoji == "\U0001F7E9"

    def test_yellow_emoji(self):
        """Test yellow rating emoji."""
        assert RiskRating.YELLOW.emoji == "\U0001F7E8"

    def test_orange_emoji(self):
        """Test orange rating emoji."""
        assert RiskRating.ORANGE.emoji == "\U0001F7E7"

    def test_red_emoji(self):
        """Test red rating emoji."""
        assert RiskRating.RED.emoji == "\U0001F7E5"
