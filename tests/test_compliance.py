"""
Unit tests for compliance module.

Tests rate limiting, circuit breaker, and compliance guard logic.
"""

import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.compliance.rate_limiter import RateLimiter
from src.compliance.circuit_breaker import CircuitBreaker, CircuitState, StopReason


class TestRateLimiter:
    """Tests for rate limiter."""

    def test_initial_state(self):
        """Test initial state of rate limiter."""
        limiter = RateLimiter(delay_range_s=(1, 2), daily_budget=10)

        assert limiter.get_request_count() == 0
        assert limiter.get_remaining_budget() == 10
        assert not limiter.is_budget_exhausted()

    def test_increment_count(self):
        """Test request counting."""
        limiter = RateLimiter(delay_range_s=(1, 2), daily_budget=10)

        limiter.increment_count()
        assert limiter.get_request_count() == 1

        limiter.increment_count()
        assert limiter.get_request_count() == 2

    def test_budget_exhaustion(self):
        """Test budget exhaustion detection."""
        limiter = RateLimiter(delay_range_s=(1, 2), daily_budget=3)

        limiter.increment_count()
        limiter.increment_count()
        limiter.increment_count()

        assert limiter.is_budget_exhausted()
        assert limiter.get_remaining_budget() == 0

    def test_delay_calculation(self):
        """Test delay calculation."""
        limiter = RateLimiter(delay_range_s=(3, 8), daily_budget=10)

        delay = limiter.calculate_delay()

        # Should be within configured range
        assert 3 <= delay <= 8

    def test_robots_crawl_delay_respected(self):
        """Test that robots.txt Crawl-delay is respected."""
        limiter = RateLimiter(delay_range_s=(3, 5), daily_budget=10)

        # If robots specifies larger delay, use that
        delay = limiter.calculate_delay(robots_crawl_delay=10)
        assert delay == 10

        # If robots delay is smaller, use random delay
        delay = limiter.calculate_delay(robots_crawl_delay=1)
        assert delay >= 3


class TestCircuitBreaker:
    """Tests for circuit breaker."""

    def test_initial_state(self):
        """Test initial state is closed."""
        cb = CircuitBreaker(consecutive_failure_limit=3)

        assert cb.state == CircuitState.CLOSED
        assert cb.can_proceed()
        assert not cb.is_open

    def test_failure_counting(self):
        """Test failure counting."""
        cb = CircuitBreaker(consecutive_failure_limit=5)

        cb.record_failure("http://test.com", 500, "server_error")
        cb.record_failure("http://test.com", 500, "server_error")

        stats = cb.get_stats()
        assert stats["consecutive_failures"] == 2
        assert stats["total_failures"] == 2

    def test_success_resets_consecutive(self):
        """Test that success resets consecutive failures."""
        cb = CircuitBreaker(consecutive_failure_limit=5)

        cb.record_failure("http://test.com", 500, "error")
        cb.record_failure("http://test.com", 500, "error")
        cb.record_success()

        stats = cb.get_stats()
        assert stats["consecutive_failures"] == 0
        assert stats["total_failures"] == 2

    def test_circuit_opens_on_consecutive_failures(self):
        """Test circuit opens after consecutive failure limit."""
        cb = CircuitBreaker(consecutive_failure_limit=3)

        cb.record_failure("http://test.com", 500, "error")
        cb.record_failure("http://test.com", 500, "error")
        cb.record_failure("http://test.com", 500, "error")

        assert cb.is_open
        assert cb.stop_reason == StopReason.CONSECUTIVE_FAILURES
        assert not cb.can_proceed()

    def test_circuit_opens_on_403(self):
        """Test circuit opens immediately on 403 (blocked)."""
        cb = CircuitBreaker(consecutive_failure_limit=5)

        cb.record_failure("http://test.com", 403, "forbidden")

        assert cb.is_open
        assert cb.stop_reason == StopReason.BLOCKED_BY_SITE

    def test_should_retry_transient_errors(self):
        """Test retry logic for transient errors."""
        cb = CircuitBreaker(max_retries=3)

        # Should retry 429 and 503
        assert cb.should_retry(429, attempt=0)
        assert cb.should_retry(503, attempt=0)
        assert cb.should_retry(502, attempt=0)

        # Should not retry 404
        assert not cb.should_retry(404, attempt=0)

        # Should not retry after max attempts
        assert not cb.should_retry(429, attempt=3)

    def test_backoff_calculation(self):
        """Test exponential backoff calculation."""
        cb = CircuitBreaker(backoff_base_s=5, backoff_multiplier=2)

        assert cb.get_backoff_delay(0) == 5   # 5 * 2^0 = 5
        assert cb.get_backoff_delay(1) == 10  # 5 * 2^1 = 10
        assert cb.get_backoff_delay(2) == 20  # 5 * 2^2 = 20

    def test_reset(self):
        """Test circuit breaker reset."""
        cb = CircuitBreaker(consecutive_failure_limit=2)

        cb.record_failure("http://test.com", 500, "error")
        cb.record_failure("http://test.com", 500, "error")
        assert cb.is_open

        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.can_proceed()

    def test_budget_open(self):
        """Test opening circuit for budget exhaustion."""
        cb = CircuitBreaker()

        cb.open_for_budget()

        assert cb.is_open
        assert cb.stop_reason == StopReason.BUDGET_EXHAUSTED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
