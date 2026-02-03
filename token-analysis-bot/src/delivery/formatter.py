"""Message formatter for Telegram delivery."""

import re
from typing import Optional

from src.constants import TELEGRAM_MAX_MESSAGE_LENGTH, TOKEN_BREAKDOWN_TEMPLATE
from src.models import Claim, TokenBreakdown
from src.synthesis.prompts import format_fdv


class MessageFormatter:
    """Formats token breakdowns for Telegram."""

    @staticmethod
    def format_breakdown(breakdown: TokenBreakdown) -> str:
        """Format a token breakdown for Telegram."""
        # Format pros
        pros_lines = []
        for pro in breakdown.pros[:5]:  # Max 5 pros
            text = MessageFormatter._escape_markdown(pro.text)
            if pro.confidence < 0.7:
                text += " (unverified)"
            pros_lines.append(f"+ {text}")
        pros_formatted = "\n".join(pros_lines) if pros_lines else "+ No clear pros identified"

        # Format cons
        cons_lines = []
        for con in breakdown.cons[:4]:  # Max 4 cons
            text = MessageFormatter._escape_markdown(con.text)
            if con.confidence < 0.7:
                text += " (unverified)"
            cons_lines.append(f"- {text}")
        cons_formatted = "\n".join(cons_lines) if cons_lines else "- No significant cons found"

        # Format dev link
        if breakdown.dev_twitter_url:
            dev_link = breakdown.dev_twitter_url
        elif breakdown.dev_twitter_handle:
            dev_link = f"https://twitter.com/{breakdown.dev_twitter_handle}"
        else:
            dev_link = "Anonymous"

        # Build message
        message = TOKEN_BREAKDOWN_TEMPLATE.format(
            risk_emoji=breakdown.risk_rating.emoji,
            symbol=MessageFormatter._escape_markdown(breakdown.symbol),
            fdv_display=breakdown.fdv_display,
            dev_link=dev_link,
            pros_list=pros_formatted,
            cons_list=cons_formatted,
            contract_address=breakdown.token_address,
            dexscreener_url=breakdown.dexscreener_url,
        )

        # Truncate if too long
        if len(message) > TELEGRAM_MAX_MESSAGE_LENGTH:
            message = message[: TELEGRAM_MAX_MESSAGE_LENGTH - 100] + "\n\n[Truncated]"

        return message

    @staticmethod
    def format_compact(breakdown: TokenBreakdown) -> str:
        """Format a compact version of the breakdown."""
        return (
            f"{breakdown.risk_rating.emoji} ${breakdown.symbol} - "
            f"${breakdown.fdv_display} FDV | "
            f"Liq: ${breakdown.on_chain_metrics.liquidity_usd:,.0f} | "
            f"Holders: {breakdown.on_chain_metrics.holder_count}\n"
            f"{breakdown.dexscreener_url}"
        )

    @staticmethod
    def format_alert(breakdown: TokenBreakdown, reason: str) -> str:
        """Format an alert message for new token."""
        return (
            f"New Token Detected\n\n"
            f"{breakdown.risk_rating.emoji} ${breakdown.symbol}\n"
            f"FDV: ${breakdown.fdv_display}\n"
            f"Liquidity: ${breakdown.on_chain_metrics.liquidity_usd:,.0f}\n"
            f"Reason: {reason}\n\n"
            f"Contract: `{breakdown.token_address}`"
        )

    @staticmethod
    def format_approval_request(breakdown: TokenBreakdown, reasons: list[str]) -> str:
        """Format an approval request for admins."""
        message = (
            f"APPROVAL REQUIRED\n\n"
            f"{MessageFormatter.format_breakdown(breakdown)}\n\n"
            f"Review reasons:\n"
        )
        for reason in reasons:
            message += f"- {reason}\n"

        message += "\n/approve or /reject"
        return message

    @staticmethod
    def format_stats(stats: dict) -> str:
        """Format analysis statistics."""
        return (
            f"Token Analysis Stats\n\n"
            f"Total analyzed: {stats.get('total_analyzed', 0)}\n"
            f"Published: {stats.get('published', 0)}\n"
            f"Rejected: {stats.get('rejected', 0)}\n"
            f"Pending approval: {stats.get('pending_approval', 0)}\n\n"
            f"By rating:\n"
            f"  GREEN: {stats.get('green', 0)}\n"
            f"  YELLOW: {stats.get('yellow', 0)}\n"
            f"  ORANGE: {stats.get('orange', 0)}\n"
            f"  RED: {stats.get('red', 0)}"
        )

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape special markdown characters for Telegram."""
        # Characters that need escaping in MarkdownV2
        special_chars = r"_*[]()~`>#+-=|{}.!"

        # Escape each special character
        for char in special_chars:
            text = text.replace(char, f"\\{char}")

        return text

    @staticmethod
    def _truncate_text(text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
