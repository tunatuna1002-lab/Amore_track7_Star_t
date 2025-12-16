"""
Base parser with common parsing functionality.
"""

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .selector_loader import SelectorLoader

logger = logging.getLogger(__name__)


class ParseStatus(Enum):
    """Status of parsing operation."""
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class RankingItem:
    """A single ranking item extracted from a page."""
    rank: int
    product_name_raw: str
    product_url: str
    brand_raw: Optional[str] = None
    notes: str = ""


@dataclass
class ParseResult:
    """Result of parsing a ranking page."""
    status: ParseStatus
    items: List[RankingItem] = field(default_factory=list)
    next_page_url: Optional[str] = None
    error_message: Optional[str] = None
    notes: str = ""


class BaseParser(ABC):
    """
    Abstract base parser for ranking pages.

    Provides common functionality for:
    - HTML parsing with BeautifulSoup
    - Selector-based extraction with fallbacks
    - Heuristic fallback when selectors fail
    """

    # Market identifier for selector lookup
    MARKET: str = ""

    def __init__(self, selector_loader: SelectorLoader = None):
        """
        Initialize the parser.

        Args:
            selector_loader: SelectorLoader instance. If None, creates new one.
        """
        self.selector_loader = selector_loader or SelectorLoader()

    def parse(self, html_content: str, base_url: str, top_n: int = 100) -> ParseResult:
        """
        Parse HTML content and extract ranking items.

        Args:
            html_content: Raw HTML content
            base_url: Base URL for resolving relative links
            top_n: Maximum number of items to extract

        Returns:
            ParseResult with extracted items
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # Try primary selectors first
            items = self._parse_with_selectors(soup, base_url, 'primary', top_n)

            if items:
                logger.info(f"Primary selectors extracted {len(items)} items")
                next_page = self._extract_next_page(soup, base_url, 'primary')
                return ParseResult(
                    status=ParseStatus.OK,
                    items=items[:top_n],
                    next_page_url=next_page
                )

            # Try fallback selectors
            logger.warning("Primary selectors failed, trying fallback")
            items = self._parse_with_selectors(soup, base_url, 'fallback', top_n)

            if items:
                logger.info(f"Fallback selectors extracted {len(items)} items")
                next_page = self._extract_next_page(soup, base_url, 'fallback')
                return ParseResult(
                    status=ParseStatus.PARTIAL,
                    items=items[:top_n],
                    next_page_url=next_page,
                    notes="Used fallback selectors"
                )

            # Try heuristic parsing
            logger.warning("Fallback selectors failed, trying heuristic parsing")
            items = self._parse_with_heuristics(soup, base_url, top_n)

            if items:
                logger.info(f"Heuristic parsing extracted {len(items)} items")
                return ParseResult(
                    status=ParseStatus.PARTIAL,
                    items=items[:top_n],
                    notes="Used heuristic parsing"
                )

            # All methods failed
            logger.error("All parsing methods failed")
            return ParseResult(
                status=ParseStatus.FAILED,
                error_message="Could not extract ranking items with any method",
                notes="All selectors and heuristics failed"
            )

        except Exception as e:
            logger.exception(f"Parsing error: {e}")
            return ParseResult(
                status=ParseStatus.FAILED,
                error_message=str(e)
            )

    def _parse_with_selectors(
        self,
        soup: BeautifulSoup,
        base_url: str,
        selector_type: str,
        top_n: int
    ) -> List[RankingItem]:
        """
        Parse using configured selectors.

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving links
            selector_type: 'primary' or 'fallback'
            top_n: Maximum items to extract

        Returns:
            List of RankingItem objects
        """
        items = []

        # Get selectors
        if selector_type == 'primary':
            get_selector = lambda name: self.selector_loader.get_primary(self.MARKET, name)
        else:
            get_selector = lambda name: self.selector_loader.get_fallback(self.MARKET, name)

        # Find product cards
        card_selector = get_selector('product_card')
        if not card_selector:
            logger.debug(f"No {selector_type} product_card selector")
            return []

        cards = soup.select(card_selector)
        if not cards:
            logger.debug(f"No elements found with selector: {card_selector}")
            return []

        logger.debug(f"Found {len(cards)} product cards")

        for idx, card in enumerate(cards[:top_n]):
            try:
                item = self._extract_item_from_card(
                    card, base_url, selector_type, idx + 1
                )
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Error extracting item {idx + 1}: {e}")

        return items

    @abstractmethod
    def _extract_item_from_card(
        self,
        card,
        base_url: str,
        selector_type: str,
        position: int
    ) -> Optional[RankingItem]:
        """
        Extract a ranking item from a product card element.

        Must be implemented by subclasses for market-specific logic.

        Args:
            card: BeautifulSoup element for the product card
            base_url: Base URL for resolving links
            selector_type: 'primary' or 'fallback'
            position: Position in the list (1-indexed)

        Returns:
            RankingItem or None if extraction failed
        """
        pass

    @abstractmethod
    def _parse_with_heuristics(
        self,
        soup: BeautifulSoup,
        base_url: str,
        top_n: int
    ) -> List[RankingItem]:
        """
        Parse using structural heuristics when selectors fail.

        Must be implemented by subclasses for market-specific logic.

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving links
            top_n: Maximum items to extract

        Returns:
            List of RankingItem objects
        """
        pass

    def _extract_next_page(
        self,
        soup: BeautifulSoup,
        base_url: str,
        selector_type: str
    ) -> Optional[str]:
        """
        Extract the next page URL for pagination.

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving links
            selector_type: 'primary' or 'fallback'

        Returns:
            Next page URL or None
        """
        market_selectors = self.selector_loader.get_market_selectors(self.MARKET)
        selectors = market_selectors.get(selector_type, {})
        pagination = selectors.get('pagination', {})

        next_page_selector = pagination.get('next_page_css')
        if not next_page_selector:
            return None

        next_link = soup.select_one(next_page_selector)
        if not next_link:
            return None

        attr = pagination.get('next_page_attr', 'href')
        href = next_link.get(attr)

        if href:
            return urljoin(base_url, href)

        return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by removing extra whitespace."""
        if not text:
            return ""
        return ' '.join(text.split())

    def _extract_rank_number(self, text: str) -> Optional[int]:
        """
        Extract rank number from text like "#1", "1位", "1", etc.

        Args:
            text: Text containing rank number

        Returns:
            Integer rank or None
        """
        if not text:
            return None

        # Remove common prefixes and suffixes
        text = text.strip()

        # Try patterns
        patterns = [
            r'#(\d+)',      # #1
            r'(\d+)位',     # 1位 (Japanese)
            r'(\d+)등',     # 1등 (Korean)
            r'^(\d+)$',     # Plain number
            r'(\d+)',       # Any number (last resort)
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))

        return None

    def _resolve_url(self, url: str, base_url: str) -> str:
        """Resolve a potentially relative URL."""
        if not url:
            return ""
        return urljoin(base_url, url)
