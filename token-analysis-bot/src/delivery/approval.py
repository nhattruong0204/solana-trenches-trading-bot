"""Human-in-the-loop approval manager."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from src.config import Settings
from src.models import AnalysisJob, AnalysisStatus, TokenBreakdown

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages human-in-the-loop approval workflow."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._pending_approvals: dict[str, AnalysisJob] = {}
        self._approval_callbacks: dict[str, asyncio.Event] = {}
        self._timeout_seconds = settings.analysis.approval_timeout_seconds

    def submit_for_approval(self, job: AnalysisJob) -> str:
        """Submit a job for human approval. Returns approval ID."""
        approval_id = f"approval_{job.job_id}"

        self._pending_approvals[approval_id] = job
        self._approval_callbacks[approval_id] = asyncio.Event()

        job.status = AnalysisStatus.AWAITING_APPROVAL
        job.updated_at = datetime.utcnow()

        logger.info(f"Job {job.job_id} submitted for approval: {approval_id}")
        return approval_id

    async def wait_for_approval(
        self, approval_id: str, timeout: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Wait for approval decision.

        Returns (approved, reason).
        If timeout occurs, returns (False, "timeout").
        """
        timeout = timeout or self._timeout_seconds
        event = self._approval_callbacks.get(approval_id)

        if not event:
            return False, "Invalid approval ID"

        try:
            # Wait for approval with timeout
            await asyncio.wait_for(event.wait(), timeout=timeout)

            job = self._pending_approvals.get(approval_id)
            if not job:
                return False, "Job not found"

            if job.status == AnalysisStatus.APPROVED:
                return True, None
            elif job.status == AnalysisStatus.REJECTED:
                return False, job.error_message or "Rejected by admin"
            else:
                return False, "Unknown status"

        except asyncio.TimeoutError:
            logger.warning(f"Approval timeout for {approval_id}")
            self._cleanup_approval(approval_id)
            return False, "Approval timeout"

    def approve(self, approval_id: str, admin_id: Optional[int] = None) -> bool:
        """Approve a pending job."""
        job = self._pending_approvals.get(approval_id)
        if not job:
            logger.warning(f"Approval not found: {approval_id}")
            return False

        job.status = AnalysisStatus.APPROVED
        job.updated_at = datetime.utcnow()

        # Trigger the event
        event = self._approval_callbacks.get(approval_id)
        if event:
            event.set()

        logger.info(f"Job {job.job_id} approved by admin {admin_id}")
        return True

    def reject(
        self, approval_id: str, reason: str = "Rejected", admin_id: Optional[int] = None
    ) -> bool:
        """Reject a pending job."""
        job = self._pending_approvals.get(approval_id)
        if not job:
            logger.warning(f"Approval not found: {approval_id}")
            return False

        job.status = AnalysisStatus.REJECTED
        job.error_message = reason
        job.updated_at = datetime.utcnow()

        # Trigger the event
        event = self._approval_callbacks.get(approval_id)
        if event:
            event.set()

        logger.info(f"Job {job.job_id} rejected by admin {admin_id}: {reason}")
        return True

    def get_pending_approvals(self) -> list[tuple[str, AnalysisJob]]:
        """Get all pending approvals."""
        return [
            (approval_id, job)
            for approval_id, job in self._pending_approvals.items()
            if job.status == AnalysisStatus.AWAITING_APPROVAL
        ]

    def get_approval_job(self, approval_id: str) -> Optional[AnalysisJob]:
        """Get job by approval ID."""
        return self._pending_approvals.get(approval_id)

    def _cleanup_approval(self, approval_id: str) -> None:
        """Clean up approval data."""
        self._pending_approvals.pop(approval_id, None)
        self._approval_callbacks.pop(approval_id, None)

    async def cleanup_expired(self) -> int:
        """Clean up expired approvals. Returns count of cleaned items."""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self._timeout_seconds * 2)

        expired = []
        for approval_id, job in self._pending_approvals.items():
            if job.updated_at < cutoff:
                expired.append(approval_id)

        for approval_id in expired:
            self._cleanup_approval(approval_id)
            logger.debug(f"Cleaned up expired approval: {approval_id}")

        return len(expired)
