"""
ComplianceGuard - The central gate for ALL HTTP requests.

This module ensures every request goes through compliance checks:
1. robots.txt verification
2. Rate limiting (random delay + Crawl-delay)
3. Daily budget enforcement
4. Circuit breaker for failures

Use the @compliance_check decorator or call guard.fetch() for compliant requests.
"""

import functools
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Tuple, Any
from urllib.parse import urlparse

import requests
import yaml

from .robots_handler import RobotsHandler
from .rate_limiter import RateLimiter
from .circuit_breaker import CircuitBreaker, StopReason

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a compliant fetch operation."""
    success: bool
    url: str
    status_code: Optional[int] = None
    content: Optional[str] = None
    error: Optional[str] = None
    blocked_reason: Optional[str] = None
    response_time_ms: Optional[float] = None
    attempts: int = 1


class ComplianceGuard:
    """
    Central compliance gate for all HTTP requests.

    EVERY request must go through this guard to ensure:
    - robots.txt compliance
    - Rate limiting
    - Daily budget enforcement
    - Circuit breaker protection
    """

    def __init__(
        self,
        user_agent: str,
        delay_range_s: Tuple[float, float],
        daily_budget: int,
        consecutive_failure_limit: int = 5,
        max_retries: int = 3,
        backoff_base_s: float = 5.0,
        backoff_multiplier: float = 2.0,
        request_timeout: int = 30,
        selectors_path: str = "selectors.yaml",
    ):
        """
        Initialize the ComplianceGuard.

        Args:
            user_agent: User-Agent string for requests
            delay_range_s: (min, max) delay range in seconds
            daily_budget: Maximum requests per day
            consecutive_failure_limit: Max failures before circuit opens
            max_retries: Max retries for transient errors
            backoff_base_s: Base delay for exponential backoff
            backoff_multiplier: Multiplier for exponential backoff
            request_timeout: HTTP request timeout in seconds
            selectors_path: Path to selectors.yaml for CAPTCHA detection patterns
        """
        self.user_agent = user_agent
        self.request_timeout = request_timeout

        # Initialize components
        self.robots = RobotsHandler(user_agent, request_timeout)
        self.rate_limiter = RateLimiter(delay_range_s, daily_budget)
        self.circuit_breaker = CircuitBreaker(
            consecutive_failure_limit,
            max_retries,
            backoff_base_s,
            backoff_multiplier
        )

        # Load CAPTCHA/blocking indicators from selectors.yaml
        self._load_blocking_patterns(selectors_path)

        # Statistics
        self._total_requests = 0
        self._successful_requests = 0
        self._blocked_requests = 0

        logger.info("ComplianceGuard initialized")

    def _load_blocking_patterns(self, selectors_path: str):
        """Load CAPTCHA and blocking patterns from selectors.yaml."""
        try:
            with open(selectors_path, 'r', encoding='utf-8') as f:
                selectors = yaml.safe_load(f)

            common = selectors.get('common', {})
            self.blocking_status_codes = set(
                common.get('blocking_status_codes', [403, 429, 503])
            )
            self.captcha_indicators = common.get('captcha_indicators', [
                'captcha', 'robot', 'verify you are human', 'access denied'
            ])
            self.suspicious_redirect_patterns = common.get(
                'suspicious_redirect_patterns', ['/errors/', '/blocked']
            )

        except Exception as e:
            logger.warning(f"Could not load selectors.yaml: {e}. Using defaults.")
            self.blocking_status_codes = {403, 429, 503}
            self.captcha_indicators = [
                'captcha', 'robot', 'verify you are human', 'access denied'
            ]
            self.suspicious_redirect_patterns = ['/errors/', '/blocked']

    def _extract_body_content(self, html: str) -> str:
        """
        Extract body content from HTML to avoid false positives from scripts/headers.

        Args:
            html: Full HTML response

        Returns:
            Body content (or full HTML if body tag not found)
        """
        html_lower = html.lower()
        body_start_idx = html_lower.find('<body')
        body_end_idx = html_lower.rfind('</body>')

        if body_start_idx != -1 and body_end_idx != -1:
            # Extract from <body to </body>
            actual_body_start = html.find('>', body_start_idx)
            if actual_body_start != -1:
                return html[actual_body_start + 1:body_end_idx]

        # Fallback: return full HTML if body tags not found
        return html

    def _check_for_blocking(self, response: requests.Response) -> Optional[str]:
        """
        Check if response indicates blocking/CAPTCHA.

        Args:
            response: HTTP response to check

        Returns:
            Blocking reason string if blocked, None otherwise
        """
        # Check status code
        if response.status_code in self.blocking_status_codes:
            return f"blocking_status_code_{response.status_code}"

        # Check for suspicious redirects
        if response.history:
            for r in response.history:
                for pattern in self.suspicious_redirect_patterns:
                    if pattern in r.url:
                        return f"suspicious_redirect:{pattern}"

        # Check content for CAPTCHA indicators (body content only)
        # Extract body to avoid false positives from JavaScript code
        body_content = self._extract_body_content(response.text)
        content_lower = body_content.lower()

        for indicator in self.captcha_indicators:
            if indicator in content_lower:
                return f"captcha_indicator:{indicator}"

        return None

    def can_fetch(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Check if we're allowed to fetch a URL.

        Performs all compliance checks without making a request.

        Args:
            url: URL to check

        Returns:
            Tuple of (allowed: bool, reason: str if not allowed)
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open:
            reason = self.circuit_breaker.stop_reason.value
            return False, f"circuit_open:{reason}"

        # Check daily budget
        if self.rate_limiter.is_budget_exhausted():
            self.circuit_breaker.open_for_budget()
            return False, "budget_exhausted"

        # Check robots.txt
        if not self.robots.can_fetch(url):
            return False, "robots_disallowed"

        return True, None

    def fetch(self, url: str) -> FetchResult:
        """
        Perform a compliant HTTP GET request.

        This is the ONLY method that should be used for fetching URLs.
        It enforces all compliance rules.

        Args:
            url: URL to fetch

        Returns:
            FetchResult with success status and content or error
        """
        start_time = datetime.now()

        # Pre-flight compliance checks
        allowed, reason = self.can_fetch(url)
        if not allowed:
            logger.warning(f"Fetch blocked by compliance: {url} - {reason}")
            self._blocked_requests += 1
            return FetchResult(
                success=False,
                url=url,
                error=f"Blocked by compliance: {reason}",
                blocked_reason=reason
            )

        # Get crawl delay for this domain
        crawl_delay = self.robots.get_crawl_delay(url)

        # Wait for rate limit
        self.rate_limiter.wait(crawl_delay)

        # Attempt the request with retries
        attempt = 0
        last_error = None
        last_status = None

        while attempt <= self.circuit_breaker.max_retries:
            try:
                self._total_requests += 1

                logger.debug(f"Fetching (attempt {attempt + 1}): {url}")

                response = requests.get(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5,ja;q=0.3",
                        "Accept-Encoding": "gzip, deflate",
                        "Connection": "keep-alive",
                    },
                    timeout=self.request_timeout,
                    allow_redirects=True
                )

                last_status = response.status_code

                # Check for blocking
                blocking_reason = self._check_for_blocking(response)
                if blocking_reason:
                    logger.warning(f"Blocking detected: {blocking_reason}")

                    # Record failure
                    self.circuit_breaker.record_failure(
                        url, response.status_code, blocking_reason
                    )

                    # Check if we should retry
                    if self.circuit_breaker.should_retry(response.status_code, attempt):
                        self.circuit_breaker.wait_for_backoff(attempt)
                        attempt += 1
                        continue

                    # No retry - return failure
                    self._blocked_requests += 1
                    return FetchResult(
                        success=False,
                        url=url,
                        status_code=response.status_code,
                        error=f"Blocked: {blocking_reason}",
                        blocked_reason=blocking_reason,
                        attempts=attempt + 1
                    )

                # Success!
                self.rate_limiter.record_request()
                self.circuit_breaker.record_success()
                self._successful_requests += 1

                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

                logger.info(
                    f"Fetch success: {url} ({response.status_code}) - "
                    f"{len(response.content)} bytes in {elapsed_ms:.0f}ms"
                )

                return FetchResult(
                    success=True,
                    url=url,
                    status_code=response.status_code,
                    content=response.text,
                    response_time_ms=elapsed_ms,
                    attempts=attempt + 1
                )

            except requests.Timeout as e:
                last_error = f"timeout:{e}"
                logger.warning(f"Request timeout: {url}")

            except requests.ConnectionError as e:
                last_error = f"connection_error:{e}"
                logger.warning(f"Connection error: {url} - {e}")

            except requests.RequestException as e:
                last_error = f"request_error:{e}"
                logger.warning(f"Request error: {url} - {e}")

            # Record failure and check retry
            self.circuit_breaker.record_failure(url, last_status, last_error or "unknown")

            if attempt < self.circuit_breaker.max_retries:
                self.circuit_breaker.wait_for_backoff(attempt)

            attempt += 1

        # All retries exhausted
        logger.error(f"All retries exhausted for: {url}")
        return FetchResult(
            success=False,
            url=url,
            status_code=last_status,
            error=last_error,
            attempts=attempt
        )

    def get_stats(self) -> dict:
        """Get comprehensive compliance statistics."""
        return {
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "blocked_requests": self._blocked_requests,
            "rate_limiter": self.rate_limiter.get_stats(),
            "circuit_breaker": self.circuit_breaker.get_stats(),
        }

    def is_stopped(self) -> bool:
        """Check if collection should stop."""
        return (
            self.circuit_breaker.is_open or
            self.rate_limiter.is_budget_exhausted()
        )

    def get_stop_reason(self) -> Optional[str]:
        """Get the reason for stopping, if stopped."""
        if self.circuit_breaker.is_open:
            return self.circuit_breaker.stop_reason.value
        if self.rate_limiter.is_budget_exhausted():
            return StopReason.BUDGET_EXHAUSTED.value
        return None


def compliance_check(guard: ComplianceGuard):
    """
    Decorator for functions that need compliance checking.

    Usage:
        @compliance_check(guard)
        def my_fetch_function(url):
            return guard.fetch(url)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if we can proceed
            if guard.is_stopped():
                reason = guard.get_stop_reason()
                logger.error(f"Compliance check failed - stopped: {reason}")
                raise ComplianceError(f"Collection stopped: {reason}")

            return func(*args, **kwargs)

        return wrapper

    return decorator


class ComplianceError(Exception):
    """Exception raised when compliance rules prevent an operation."""
    pass
