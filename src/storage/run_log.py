"""
Run log tracking for collection runs.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.utils.time_utils import get_kst_now, format_kst_datetime

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of a collection run."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    STOPPED_BY_ROBOTS = "stopped_by_robots"
    STOPPED_BY_BUDGET = "stopped_by_budget"
    BLOCKED = "blocked"


@dataclass
class RunLog:
    """
    Log entry for a collection run.

    Tracks:
    - Run timing
    - Status
    - Request counts
    - Blocking information
    """
    run_id: str
    started_at_kst: str = field(default_factory=lambda: format_kst_datetime())
    ended_at_kst: Optional[str] = None
    status: RunStatus = RunStatus.SUCCESS
    requests_used: int = 0
    blocked_reason: Optional[str] = None
    notes: str = ""

    def start(self):
        """Mark the run as started."""
        self.started_at_kst = format_kst_datetime()
        logger.info(f"Run {self.run_id} started at {self.started_at_kst}")

    def end(self, status: RunStatus, notes: str = ""):
        """
        Mark the run as ended.

        Args:
            status: Final status of the run
            notes: Additional notes
        """
        self.ended_at_kst = format_kst_datetime()
        self.status = status

        if notes:
            self.notes = f"{self.notes}; {notes}" if self.notes else notes

        logger.info(
            f"Run {self.run_id} ended at {self.ended_at_kst} "
            f"with status {status.value}"
        )

    def record_block(self, reason: str):
        """
        Record a blocking event.

        Args:
            reason: Reason for blocking
        """
        self.blocked_reason = reason
        logger.warning(f"Run {self.run_id} blocked: {reason}")

    def update_requests(self, count: int):
        """
        Update request count.

        Args:
            count: New request count
        """
        self.requests_used = count

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "run_id": self.run_id,
            "started_at_kst": self.started_at_kst,
            "ended_at_kst": self.ended_at_kst,
            "status": self.status.value,
            "requests_used": self.requests_used,
            "blocked_reason": self.blocked_reason or "",
            "notes": self.notes
        }

    def to_row(self) -> list:
        """Convert to row for Excel storage."""
        return [
            self.run_id,
            self.started_at_kst,
            self.ended_at_kst or "",
            self.status.value,
            self.requests_used,
            self.blocked_reason or "",
            self.notes
        ]

    @classmethod
    def get_columns(cls) -> list:
        """Get column names for the run_log sheet."""
        return [
            "run_id",
            "started_at_kst",
            "ended_at_kst",
            "status",
            "requests_used",
            "blocked_reason",
            "notes"
        ]
