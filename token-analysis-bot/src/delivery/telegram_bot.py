"""Telegram bot for delivering token breakdowns."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import Settings
from src.delivery.approval import ApprovalManager
from src.delivery.formatter import MessageFormatter
from src.models import AnalysisJob, AnalysisStatus, TokenBreakdown

logger = logging.getLogger(__name__)


class TelegramDeliveryBot:
    """Telegram bot for publishing token breakdowns."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.formatter = MessageFormatter()
        self.approval_manager = ApprovalManager(settings)

        self._bot: Optional[Bot] = None
        self._app: Optional[Application] = None
        self._running = False

        # Rate limiting
        self._last_post_time: Optional[datetime] = None
        self._posts_this_hour = 0
        self._hour_start: Optional[datetime] = None

        # Stats
        self._stats = {
            "total_published": 0,
            "total_rejected": 0,
            "by_rating": {"green": 0, "yellow": 0, "orange": 0, "red": 0},
        }

    async def initialize(self) -> None:
        """Initialize the Telegram bot."""
        if not self.settings.telegram.bot_token:
            raise ValueError("Telegram bot token not configured")

        # Create bot instance
        self._bot = Bot(token=self.settings.telegram.bot_token)

        # Create application for handling commands
        self._app = (
            Application.builder()
            .token(self.settings.telegram.bot_token)
            .build()
        )

        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("stats", self._cmd_stats))
        self._app.add_handler(CommandHandler("pending", self._cmd_pending))
        self._app.add_handler(CommandHandler("approve", self._cmd_approve))
        self._app.add_handler(CommandHandler("reject", self._cmd_reject))
        self._app.add_handler(CommandHandler("analyze", self._cmd_analyze))

        # Verify bot
        me = await self._bot.get_me()
        logger.info(f"Telegram bot initialized: @{me.username}")

    async def start(self) -> None:
        """Start the bot (for handling commands)."""
        if self._app:
            await self._app.initialize()
            await self._app.start()
            self._running = True
            logger.info("Telegram bot started")

    async def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        if self._app:
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def publish_breakdown(
        self, breakdown: TokenBreakdown, job: Optional[AnalysisJob] = None
    ) -> Optional[int]:
        """
        Publish a token breakdown to the target channel.

        Returns message ID if successful, None otherwise.
        """
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        # Check rate limits
        if not self._check_rate_limit():
            logger.warning("Rate limit exceeded, skipping post")
            return None

        # Check if human approval needed
        if breakdown.requires_human_review and self.settings.analysis.enable_human_approval:
            return await self._handle_approval_workflow(breakdown, job)

        # Format message
        message = self.formatter.format_breakdown(breakdown)

        try:
            # Send to channel
            result = await self._bot.send_message(
                chat_id=self.settings.telegram.target_channel,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=False,
            )

            # Update stats
            self._update_stats(breakdown)
            self._last_post_time = datetime.utcnow()

            # Update job if provided
            if job:
                job.status = AnalysisStatus.PUBLISHED
                job.telegram_message_id = result.message_id
                job.published_at = datetime.utcnow()
                job.updated_at = datetime.utcnow()

            logger.info(
                f"Published breakdown for ${breakdown.symbol} "
                f"(msg_id: {result.message_id})"
            )

            return result.message_id

        except Exception as e:
            logger.error(f"Failed to publish breakdown: {e}")
            if job:
                job.status = AnalysisStatus.FAILED
                job.error_message = str(e)
                job.updated_at = datetime.utcnow()
            return None

    async def _handle_approval_workflow(
        self, breakdown: TokenBreakdown, job: Optional[AnalysisJob]
    ) -> Optional[int]:
        """Handle human approval workflow."""
        if not job:
            # Create temporary job for approval
            job = AnalysisJob(
                job_id=f"temp_{breakdown.token_address[:8]}",
                token_address=breakdown.token_address,
                status=AnalysisStatus.AWAITING_APPROVAL,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                breakdown=breakdown,
            )

        # Submit for approval
        approval_id = self.approval_manager.submit_for_approval(job)

        # Notify admins
        await self._notify_admins_for_approval(breakdown, job, approval_id)

        # Wait for approval
        approved, reason = await self.approval_manager.wait_for_approval(approval_id)

        if approved:
            # Publish after approval
            breakdown.requires_human_review = False
            return await self.publish_breakdown(breakdown, job)
        else:
            logger.info(f"Breakdown rejected: {reason}")
            self._stats["total_rejected"] += 1
            return None

    async def _notify_admins_for_approval(
        self, breakdown: TokenBreakdown, job: AnalysisJob, approval_id: str
    ) -> None:
        """Send approval request to admin users."""
        message = self.formatter.format_approval_request(
            breakdown, breakdown.human_review_reasons
        )
        message += f"\n\nApproval ID: `{approval_id}`"

        for admin_id in self.settings.telegram.admin_users:
            try:
                await self._bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.utcnow()

        # Reset hourly counter
        if self._hour_start is None or (now - self._hour_start).seconds >= 3600:
            self._hour_start = now
            self._posts_this_hour = 0

        # Check hourly limit
        if self._posts_this_hour >= self.settings.analysis.max_analyses_per_hour:
            return False

        # Check cooldown
        if self._last_post_time:
            elapsed = (now - self._last_post_time).seconds
            if elapsed < self.settings.analysis.cooldown_between_posts_seconds:
                return False

        self._posts_this_hour += 1
        return True

    def _update_stats(self, breakdown: TokenBreakdown) -> None:
        """Update publishing statistics."""
        self._stats["total_published"] += 1
        rating = breakdown.risk_rating.value
        self._stats["by_rating"][rating] = self._stats["by_rating"].get(rating, 0) + 1

    # Command handlers

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "Token Analysis Bot\n\n"
            "Use /help to see available commands."
        )

    async def _cmd_help(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        help_text = (
            "Available Commands:\n\n"
            "/status - Check bot status\n"
            "/stats - View analysis statistics\n"
            "/pending - List pending approvals\n"
            "/approve <id> - Approve a pending analysis\n"
            "/reject <id> <reason> - Reject a pending analysis\n"
            "/analyze <address> - Manually analyze a token"
        )
        await update.message.reply_text(help_text)

    async def _cmd_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /status command."""
        pending_count = len(self.approval_manager.get_pending_approvals())
        status = (
            f"Status: {'Running' if self._running else 'Stopped'}\n"
            f"Pending approvals: {pending_count}\n"
            f"Posts this hour: {self._posts_this_hour}"
        )
        await update.message.reply_text(status)

    async def _cmd_stats(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /stats command."""
        stats = {
            "total_analyzed": self._stats["total_published"] + self._stats["total_rejected"],
            "published": self._stats["total_published"],
            "rejected": self._stats["total_rejected"],
            "pending_approval": len(self.approval_manager.get_pending_approvals()),
            **self._stats["by_rating"],
        }
        message = self.formatter.format_stats(stats)
        await update.message.reply_text(message)

    async def _cmd_pending(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /pending command."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only command")
            return

        pending = self.approval_manager.get_pending_approvals()
        if not pending:
            await update.message.reply_text("No pending approvals")
            return

        message = "Pending Approvals:\n\n"
        for approval_id, job in pending:
            symbol = job.breakdown.symbol if job.breakdown else "UNKNOWN"
            message += f"- {approval_id}: ${symbol}\n"

        await update.message.reply_text(message)

    async def _cmd_approve(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /approve command."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only command")
            return

        if not context.args:
            await update.message.reply_text("Usage: /approve <approval_id>")
            return

        approval_id = context.args[0]
        success = self.approval_manager.approve(
            approval_id, admin_id=update.effective_user.id
        )

        if success:
            await update.message.reply_text(f"Approved: {approval_id}")
        else:
            await update.message.reply_text(f"Failed to approve: {approval_id}")

    async def _cmd_reject(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /reject command."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only command")
            return

        if not context.args:
            await update.message.reply_text("Usage: /reject <approval_id> [reason]")
            return

        approval_id = context.args[0]
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Rejected by admin"

        success = self.approval_manager.reject(
            approval_id, reason=reason, admin_id=update.effective_user.id
        )

        if success:
            await update.message.reply_text(f"Rejected: {approval_id}")
        else:
            await update.message.reply_text(f"Failed to reject: {approval_id}")

    async def _cmd_analyze(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /analyze command - triggers manual analysis."""
        if not self._is_admin(update.effective_user.id):
            await update.message.reply_text("Admin only command")
            return

        if not context.args:
            await update.message.reply_text("Usage: /analyze <token_address>")
            return

        token_address = context.args[0]
        await update.message.reply_text(
            f"Analysis requested for: `{token_address}`\n"
            "This will be processed by the orchestrator.",
            parse_mode="Markdown",
        )

        # Note: The actual analysis would be triggered through the orchestrator
        # This command just acknowledges the request

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.settings.telegram.admin_users

    def get_stats(self) -> dict:
        """Get bot statistics."""
        return {
            **self._stats,
            "pending_approvals": len(self.approval_manager.get_pending_approvals()),
            "posts_this_hour": self._posts_this_hour,
        }
