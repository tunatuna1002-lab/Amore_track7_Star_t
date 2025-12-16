"""
Robots.txt handler for compliance-first crawling.

Fetches, parses, and enforces robots.txt rules per domain.
"""

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)


class RobotsHandler:
    """
    Handles robots.txt fetching, parsing, and compliance checks.

    Caches robots.txt per domain to avoid repeated fetches.
    """

    # Cache expiry time for robots.txt (1 hour)
    CACHE_EXPIRY_HOURS = 1

    def __init__(self, user_agent: str, request_timeout: int = 10):
        """
        Initialize the robots handler.

        Args:
            user_agent: User-Agent string for robots.txt matching
            request_timeout: Timeout for fetching robots.txt
        """
        self.user_agent = user_agent
        self.request_timeout = request_timeout

        # Cache: domain -> (RobotFileParser, fetch_time)
        self._cache: Dict[str, Tuple[RobotFileParser, datetime]] = {}

        # Crawl-delay cache: domain -> delay_seconds
        self._crawl_delays: Dict[str, Optional[float]] = {}

    def _get_robots_url(self, url: str) -> str:
        """Get the robots.txt URL for a given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    def _is_cache_valid(self, domain: str) -> bool:
        """Check if cached robots.txt is still valid."""
        if domain not in self._cache:
            return False

        _, fetch_time = self._cache[domain]
        expiry = fetch_time + timedelta(hours=self.CACHE_EXPIRY_HOURS)
        return datetime.now() < expiry

    def _fetch_robots(self, url: str) -> Tuple[RobotFileParser, Optional[float]]:
        """
        Fetch and parse robots.txt for a URL.

        Returns:
            Tuple of (RobotFileParser, crawl_delay_seconds or None)
        """
        domain = self._get_domain(url)
        robots_url = self._get_robots_url(url)

        rp = RobotFileParser()
        rp.set_url(robots_url)

        crawl_delay = None

        try:
            # Fetch robots.txt manually to extract Crawl-delay
            response = requests.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.request_timeout
            )

            if response.status_code == 200:
                # Parse with RobotFileParser
                rp.parse(response.text.splitlines())

                # Extract Crawl-delay (not directly supported by RobotFileParser)
                crawl_delay = self._extract_crawl_delay(response.text)

                logger.info(f"Fetched robots.txt for {domain}: allowed={rp.can_fetch(self.user_agent, url)}, crawl_delay={crawl_delay}")

            elif response.status_code == 404:
                # No robots.txt means everything is allowed
                logger.info(f"No robots.txt for {domain} (404)")

            else:
                # Treat other errors as restrictive
                logger.warning(f"Error fetching robots.txt for {domain}: {response.status_code}")

        except requests.RequestException as e:
            # Network error - be conservative, assume restrictions
            logger.warning(f"Failed to fetch robots.txt for {domain}: {e}")

        return rp, crawl_delay

    def _extract_crawl_delay(self, robots_text: str) -> Optional[float]:
        """
        Extract Crawl-delay directive from robots.txt content.

        Looks for Crawl-delay that applies to our user-agent or to *.
        """
        lines = robots_text.lower().splitlines()
        current_agent_applies = False
        crawl_delay = None

        user_agent_lower = self.user_agent.lower()

        for line in lines:
            line = line.strip()

            # Check for User-agent directive
            if line.startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                # Check if this section applies to us
                current_agent_applies = (
                    agent == "*" or
                    agent in user_agent_lower or
                    user_agent_lower.startswith(agent)
                )

            # Check for Crawl-delay in applicable section
            elif line.startswith("crawl-delay:") and current_agent_applies:
                try:
                    delay_str = line.split(":", 1)[1].strip()
                    delay = float(delay_str)
                    # Take the largest delay if multiple are specified
                    if crawl_delay is None or delay > crawl_delay:
                        crawl_delay = delay
                except ValueError:
                    pass

        return crawl_delay

    def get_robots_parser(self, url: str) -> RobotFileParser:
        """
        Get RobotFileParser for a URL, using cache if available.

        Args:
            url: The URL to check

        Returns:
            RobotFileParser instance
        """
        domain = self._get_domain(url)

        # Return cached if valid
        if self._is_cache_valid(domain):
            return self._cache[domain][0]

        # Fetch fresh
        rp, crawl_delay = self._fetch_robots(url)

        # Update cache
        self._cache[domain] = (rp, datetime.now())
        self._crawl_delays[domain] = crawl_delay

        return rp

    def can_fetch(self, url: str) -> bool:
        """
        Check if we're allowed to fetch a URL according to robots.txt.

        Args:
            url: The URL to check

        Returns:
            True if allowed, False if disallowed
        """
        rp = self.get_robots_parser(url)
        allowed = rp.can_fetch(self.user_agent, url)

        if not allowed:
            logger.warning(f"robots.txt disallows: {url}")

        return allowed

    def get_crawl_delay(self, url: str) -> Optional[float]:
        """
        Get the Crawl-delay for a URL's domain.

        Args:
            url: The URL to check

        Returns:
            Crawl-delay in seconds, or None if not specified
        """
        domain = self._get_domain(url)

        # Ensure robots.txt is fetched
        if not self._is_cache_valid(domain):
            self.get_robots_parser(url)

        return self._crawl_delays.get(domain)

    def clear_cache(self):
        """Clear the robots.txt cache."""
        self._cache.clear()
        self._crawl_delays.clear()
        logger.debug("Robots.txt cache cleared")
