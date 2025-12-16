"""
Circuit breaker for compliance-first crawling.

Implements:
1. Daily budget hard stop
2. Consecutive failure detection and kill-switch
3. Retry with exponential backoff for transient errors
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Stopped - too many failures
    HALF_OPEN = "half_open" # Testing if service recovered


class StopReason(Enum):
    """Reasons for stopping collection."""
    NONE = "none"
    BUDGET_EXHAUSTED = "stopped_by_budget"
    CONSECUTIVE_FAILURES = "stopped_by_failures"
    ROBOTS_BLOCKED = "stopped_by_robots"
    BLOCKED_BY_SITE = "blocked"
    MANUAL_STOP = "manual_stop"


@dataclass
class FailureRecord:
    """Record of a failure event."""
    timestamp: datetime
    url: str
    status_code: Optional[int]
    reason: str


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    stop_reason: StopReason = StopReason.NONE
    consecutive_failures: int = 0
    total_failures: int = 0
    failure_history: List[FailureRecord] = field(default_factory=list)
    last_failure_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None


class CircuitBreaker:
    """
    Circuit breaker for safe, compliant crawling.

    Opens the circuit (stops requests) when:
    1. Daily budget is exhausted
    2. Too many consecutive failures occur
    3. Site actively blocks us (403, CAPTCHA detection)
    """

    # HTTP status codes that indicate blocking
    BLOCKING_CODES = {403, 429, 503}

    # Transient error codes that should be retried
    TRANSIENT_CODES = {429, 503, 502, 504}

    def __init__(
        self,
        consecutive_failure_limit: int = 5,
        max_retries: int = 3,
        backoff_base_s: float = 5.0,
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize the circuit breaker.

        Args:
            consecutive_failure_limit: Max consecutive failures before opening circuit
            max_retries: Max retries for transient errors
            backoff_base_s: Base delay for exponential backoff
            backoff_multiplier: Multiplier for exponential backoff
        """
        self.consecutive_failure_limit = consecutive_failure_limit
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_multiplier = backoff_multiplier

        self._state = CircuitBreakerState()

        logger.info(
            f"CircuitBreaker initialized: failure_limit={consecutive_failure_limit}, "
            f"max_retries={max_retries}"
        )

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (stopped)."""
        return self._state.state == CircuitState.OPEN

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state.state

    @property
    def stop_reason(self) -> StopReason:
        """Get the reason for stopping, if any."""
        return self._state.stop_reason

    def can_proceed(self) -> bool:
        """Check if we can proceed with a request."""
        if self.is_open:
            logger.warning(
                f"Circuit is OPEN - cannot proceed. Reason: {self._state.stop_reason.value}"
            )
            return False
        return True

    def record_success(self):
        """Record a successful request."""
        # Reset consecutive failures on success
        if self._state.consecutive_failures > 0:
            logger.debug(
                f"Success after {self._state.consecutive_failures} consecutive failures"
            )
        self._state.consecutive_failures = 0

        # If half-open, close the circuit
        if self._state.state == CircuitState.HALF_OPEN:
            logger.info("Circuit closing after successful request in half-open state")
            self._state.state = CircuitState.CLOSED

    def record_failure(
        self,
        url: str,
        status_code: Optional[int] = None,
        reason: str = "unknown"
    ):
        """
        Record a failed request.

        Args:
            url: URL that failed
            status_code: HTTP status code (if applicable)
            reason: Reason for failure
        """
        now = datetime.now()

        # Record the failure
        failure = FailureRecord(
            timestamp=now,
            url=url,
            status_code=status_code,
            reason=reason
        )
        self._state.failure_history.append(failure)
        self._state.total_failures += 1
        self._state.consecutive_failures += 1
        self._state.last_failure_time = now

        logger.warning(
            f"Failure recorded: url={url}, status={status_code}, "
            f"reason={reason}, consecutive={self._state.consecutive_failures}"
        )

        # Check if we should open the circuit
        self._check_and_open_circuit(status_code, reason)

    def _check_and_open_circuit(
        self,
        status_code: Optional[int],
        reason: str
    ):
        """Check if circuit should be opened based on failure."""
        # Check for immediate blocking (403 usually means we're blocked)
        if status_code == 403:
            self._open_circuit(StopReason.BLOCKED_BY_SITE)
            return

        # Check for CAPTCHA or blocking indicators
        if "captcha" in reason.lower() or "blocked" in reason.lower():
            self._open_circuit(StopReason.BLOCKED_BY_SITE)
            return

        # Check for robots.txt blocking
        if "robots" in reason.lower():
            self._open_circuit(StopReason.ROBOTS_BLOCKED)
            return

        # Check consecutive failure limit
        if self._state.consecutive_failures >= self.consecutive_failure_limit:
            logger.error(
                f"Consecutive failure limit reached ({self.consecutive_failure_limit})"
            )
            self._open_circuit(StopReason.CONSECUTIVE_FAILURES)
            return

    def _open_circuit(self, reason: StopReason):
        """Open the circuit (stop requests)."""
        self._state.state = CircuitState.OPEN
        self._state.stop_reason = reason
        self._state.opened_at = datetime.now()

        logger.error(f"CIRCUIT OPENED - Stop reason: {reason.value}")

    def open_for_budget(self):
        """Open circuit due to budget exhaustion."""
        self._open_circuit(StopReason.BUDGET_EXHAUSTED)

    def manual_stop(self, reason: str = "manual"):
        """Manually stop the circuit breaker."""
        self._state.stop_reason = StopReason.MANUAL_STOP
        self._open_circuit(StopReason.MANUAL_STOP)
        logger.info(f"Manual stop triggered: {reason}")

    def reset(self):
        """Reset the circuit breaker to initial state."""
        logger.info("Circuit breaker reset")
        self._state = CircuitBreakerState()

    def should_retry(self, status_code: Optional[int], attempt: int) -> bool:
        """
        Check if we should retry a request.

        Args:
            status_code: HTTP status code
            attempt: Current attempt number (0-indexed)

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_retries:
            logger.debug(f"Max retries ({self.max_retries}) reached")
            return False

        if status_code in self.TRANSIENT_CODES:
            return True

        return False

    def get_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = self.backoff_base_s * (self.backoff_multiplier ** attempt)
        logger.debug(f"Backoff delay for attempt {attempt}: {delay}s")
        return delay

    def wait_for_backoff(self, attempt: int):
        """Wait for the backoff delay."""
        delay = self.get_backoff_delay(attempt)
        logger.info(f"Backing off for {delay}s (attempt {attempt + 1}/{self.max_retries})")
        time.sleep(delay)

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "state": self._state.state.value,
            "stop_reason": self._state.stop_reason.value,
            "consecutive_failures": self._state.consecutive_failures,
            "total_failures": self._state.total_failures,
            "last_failure_time": (
                self._state.last_failure_time.isoformat()
                if self._state.last_failure_time else None
            ),
            "opened_at": (
                self._state.opened_at.isoformat()
                if self._state.opened_at else None
            ),
            "recent_failures": [
                {
                    "url": f.url,
                    "status_code": f.status_code,
                    "reason": f.reason,
                    "timestamp": f.timestamp.isoformat()
                }
                for f in self._state.failure_history[-5:]  # Last 5 failures
            ]
        }
