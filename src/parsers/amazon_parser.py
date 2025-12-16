"""
Amazon Best Sellers page parser.

TODO: Selectors must be verified against live Amazon pages before production use.
"""

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base_parser import BaseParser, RankingItem, ParseStatus
from .selector_loader import SelectorLoader

logger = logging.getLogger(__name__)


class AmazonParser(BaseParser):
    """
    Parser for Amazon US Best Sellers pages.

    Handles:
    - Product ranking extraction
    - Pagination
    - Multiple selector fallback strategies
    """

    MARKET = "amazon_us"

    def __init__(self, selector_loader: SelectorLoader = None):
        """Initialize Amazon parser."""
        super().__init__(selector_loader)
        logger.debug("AmazonParser initialized")

    def _extract_item_from_card(
        self,
        card,
        base_url: str,
        selector_type: str,
        position: int
    ) -> Optional[RankingItem]:
        """
        Extract ranking item from an Amazon product card.

        Args:
            card: BeautifulSoup element for the product card
            base_url: Base URL for resolving links
            selector_type: 'primary' or 'fallback'
            position: Position in the list (1-indexed)

        Returns:
            RankingItem or None
        """
        market_selectors = self.selector_loader.get_market_selectors(self.MARKET)
        selectors = market_selectors.get(selector_type, {})

        # Extract rank
        rank = self._extract_rank(card, selectors, position)

        # Extract product name
        product_name = self._extract_product_name(card, selectors)
        if not product_name:
            logger.debug(f"Could not extract product name for position {position}")
            return None

        # Extract product URL
        product_url = self._extract_product_url(card, selectors, base_url)
        if not product_url:
            logger.debug(f"Could not extract product URL for position {position}")
            return None

        # Extract brand (optional)
        brand = self._extract_brand(card, selectors)

        return RankingItem(
            rank=rank,
            product_name_raw=product_name,
            product_url=product_url,
            brand_raw=brand
        )

    def _extract_rank(self, card, selectors: dict, fallback_position: int) -> int:
        """Extract rank number from product card."""
        rank_config = selectors.get('rank', {})

        # Try CSS selector
        css = rank_config.get('css') if isinstance(rank_config, dict) else rank_config
        if css:
            rank_elem = card.select_one(css)
            if rank_elem:
                rank_text = self._clean_text(rank_elem.get_text())
                rank_num = self._extract_rank_number(rank_text)
                if rank_num:
                    return rank_num

        # Try data attribute
        attr = rank_config.get('attr') if isinstance(rank_config, dict) else None
        if attr:
            rank_val = card.get(attr)
            if rank_val:
                rank_num = self._extract_rank_number(str(rank_val))
                if rank_num:
                    return rank_num

        # Fallback to position
        return fallback_position

    def _extract_product_name(self, card, selectors: dict) -> Optional[str]:
        """Extract product name from card."""
        name_config = selectors.get('product_name', {})

        # Try primary CSS
        css = name_config.get('css') if isinstance(name_config, dict) else name_config
        if css:
            name_elem = card.select_one(css)
            if name_elem:
                return self._clean_text(name_elem.get_text())

        # Try alternative CSS
        alt_css = name_config.get('alt_css') if isinstance(name_config, dict) else None
        if alt_css:
            name_elem = card.select_one(alt_css)
            if name_elem:
                return self._clean_text(name_elem.get_text())

        # Try any link text as fallback
        link = card.select_one('a')
        if link:
            text = self._clean_text(link.get_text())
            if text and len(text) > 5:
                return text

        return None

    def _extract_product_url(self, card, selectors: dict, base_url: str) -> Optional[str]:
        """Extract product URL from card."""
        url_config = selectors.get('product_url', {})

        css = url_config.get('css') if isinstance(url_config, dict) else url_config
        attr = url_config.get('attr', 'href') if isinstance(url_config, dict) else 'href'

        if css:
            link = card.select_one(css)
            if link:
                href = link.get(attr)
                if href:
                    return self._resolve_url(href, base_url)

        # Fallback: any link with /dp/ (Amazon product page pattern)
        for link in card.select('a[href]'):
            href = link.get('href', '')
            if '/dp/' in href:
                return self._resolve_url(href, base_url)

        return None

    def _extract_brand(self, card, selectors: dict) -> Optional[str]:
        """Extract brand name from card (optional field)."""
        brand_config = selectors.get('brand', {})

        if brand_config.get('optional') is False:
            return None

        css = brand_config.get('css') if isinstance(brand_config, dict) else brand_config
        if css:
            brand_elem = card.select_one(css)
            if brand_elem:
                return self._clean_text(brand_elem.get_text())

        return None

    def _parse_with_heuristics(
        self,
        soup: BeautifulSoup,
        base_url: str,
        top_n: int
    ) -> List[RankingItem]:
        """
        Parse using structural heuristics when selectors fail.

        Looks for common Amazon page patterns:
        - Elements with data-asin attribute (product identifiers)
        - Links containing /dp/ (product detail pages)
        - Badge elements with rank numbers
        """
        items = []
        heuristics = self.selector_loader.get_market_selectors(self.MARKET).get('heuristic', {})

        # Find elements with data-asin (Amazon product identifier)
        container_attr = heuristics.get('container_attr', 'data-asin')
        products = soup.select(f'[{container_attr}]')

        if not products:
            # Try finding any div with product links
            products = soup.select('div:has(a[href*="/dp/"])')

        logger.debug(f"Heuristic: found {len(products)} potential products")

        for idx, product in enumerate(products[:top_n]):
            try:
                # Find product link
                link = product.select_one('a[href*="/dp/"]')
                if not link:
                    continue

                href = link.get('href', '')
                product_url = self._resolve_url(href, base_url)

                # Extract product name from link text or nearby elements
                product_name = None

                # Try link text
                link_text = self._clean_text(link.get_text())
                if link_text and len(link_text) > 5:
                    product_name = link_text

                # Try title/alt attributes
                if not product_name:
                    for attr in ['title', 'alt']:
                        val = link.get(attr)
                        if val:
                            product_name = self._clean_text(val)
                            break

                # Try nearby text elements
                if not product_name:
                    for elem in product.select('span, div'):
                        text = self._clean_text(elem.get_text())
                        if text and len(text) > 10 and len(text) < 200:
                            product_name = text
                            break

                if not product_name:
                    continue

                # Try to extract rank from badge
                rank = idx + 1
                rank_pattern = heuristics.get('rank_pattern', r'#(\d+)')
                badge = product.select_one('[class*="badge"], [class*="rank"]')
                if badge:
                    badge_text = badge.get_text()
                    match = re.search(rank_pattern, badge_text)
                    if match:
                        rank = int(match.group(1))

                items.append(RankingItem(
                    rank=rank,
                    product_name_raw=product_name,
                    product_url=product_url,
                    brand_raw=None,
                    notes="heuristic_extraction"
                ))

            except Exception as e:
                logger.debug(f"Heuristic extraction error for item {idx}: {e}")

        return items
