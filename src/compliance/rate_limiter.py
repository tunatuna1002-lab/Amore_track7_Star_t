"""
Rate limiter for compliance-first crawling.

Enforces delays between requests and respects Crawl-delay from robots.txt.
"""

import logging
import random
import time
from datetime import datetime, date
from typing import Optional, Tuple
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter that enforces:
    1. Random delay between requests (configurable range)
    2. Crawl-delay from robots.txt (if specified)
    3. Daily request budget (circuit breaker)
    """

    def __init__(
        self,
        delay_range_s: Tuple[float, float],
        daily_budget: int,
    ):
        """
        Initialize the rate limiter.

        Args:
            delay_range_s: (min, max) delay range in seconds
            daily_budget: Maximum requests per day (hard limit)
        """
        self.delay_min = delay_range_s[0]
        self.delay_max = delay_range_s[1]
        self.daily_budget = daily_budget

        # Request counter (reset daily)
        self._request_count = 0
        self._count_date = date.today()
        self._lock = Lock()

        # Last request timestamp
        self._last_request_time: Optional[datetime] = None

        logger.info(
            f"RateLimiter initialized: delay={delay_range_s}s, budget={daily_budget}/day"
        )

    def _reset_if_new_day(self):
        """Reset counter if it's a new day."""
        today = date.today()
        if today != self._count_date:
            logger.info(
                f"New day detected. Resetting request count from {self._request_count} to 0"
            )
            self._request_count = 0
            self._count_date = today

    def get_request_count(self) -> int:
        """Get current request count for today."""
        with self._lock:
            self._reset_if_new_day()
            return self._request_count

    def get_remaining_budget(self) -> int:
        """Get remaining request budget for today."""
        with self._lock:
            self._reset_if_new_day()
            return max(0, self.daily_budget - self._request_count)

    def is_budget_exhausted(self) -> bool:
        """Check if daily budget is exhausted."""
        return self.get_remaining_budget() <= 0

    def increment_count(self):
        """Increment the request counter."""
        with self._lock:
            self._reset_if_new_day()
            self._request_count += 1
            logger.debug(
                f"Request count: {self._request_count}/{self.daily_budget}"
            )

    def calculate_delay(self, robots_crawl_delay: Optional[float] = None) -> float:
        """
        Calculate the delay to wait before the next request.

        Uses the larger of:
        - Random delay from configured range
        - Crawl-delay from robots.txt (if specified)

        Args:
            robots_crawl_delay: Crawl-delay from robots.txt (seconds)

        Returns:
            Delay in seconds
        """
        # Random delay from configured range
        random_delay = random.uniform(self.delay_min, self.delay_max)

        # Use the larger of random delay or robots Crawl-delay
        if robots_crawl_delay is not None and robots_crawl_delay > random_delay:
            delay = robots_crawl_delay
            logger.debug(
                f"Using robots.txt Crawl-delay: {delay}s (random would be {random_delay:.2f}s)"
            )
        else:
            delay = random_delay
            logger.debug(f"Using random delay: {delay:.2f}s")

        return delay

    def wait(self, robots_crawl_delay: Optional[float] = None):
        """
        Wait the appropriate delay before the next request.

        Args:
            robots_crawl_delay: Crawl-delay from robots.txt (seconds)
        """
        delay = self.calculate_delay(robots_crawl_delay)

        # If we've made a request before, calculate time since last request
        if self._last_request_time is not None:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            remaining_delay = delay - elapsed

            if remaining_delay > 0:
                logger.debug(f"Waiting {remaining_delay:.2f}s before next request")
                time.sleep(remaining_delay)
        else:
            # First request of session, still apply delay for politeness
            logger.debug(f"First request, waiting {delay:.2f}s")
            time.sleep(delay)

        # Update last request time
        self._last_request_time = datetime.now()

    def record_request(self):
        """Record that a request was made (increment counter and update timestamp)."""
        self.increment_count()
        self._last_request_time = datetime.now()

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "requests_today": self.get_request_count(),
            "daily_budget": self.daily_budget,
            "remaining_budget": self.get_remaining_budget(),
            "budget_exhausted": self.is_budget_exhausted(),
            "count_date": str(self._count_date),
        }
