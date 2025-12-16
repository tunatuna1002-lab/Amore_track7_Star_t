"""
Selector loader for externalized CSS/XPath selectors.
"""

import logging
from typing import Any, Dict, Optional

import yaml

from src.utils.config_loader import get_project_root

logger = logging.getLogger(__name__)


class SelectorLoader:
    """
    Loads and provides access to selectors from selectors.yaml.

    Supports:
    - Primary selectors
    - Fallback selectors
    - Heuristic patterns
    """

    def __init__(self, selectors_path: str = None):
        """
        Initialize the selector loader.

        Args:
            selectors_path: Path to selectors.yaml. If None, uses project root.
        """
        if selectors_path is None:
            selectors_path = get_project_root() / "selectors.yaml"

        self.selectors_path = selectors_path
        self._selectors: Dict[str, Any] = {}
        self._load_selectors()

    def _load_selectors(self):
        """Load selectors from YAML file."""
        try:
            with open(self.selectors_path, 'r', encoding='utf-8') as f:
                self._selectors = yaml.safe_load(f)
            logger.info(f"Loaded selectors from {self.selectors_path}")
        except Exception as e:
            logger.error(f"Failed to load selectors: {e}")
            self._selectors = {}

    def reload(self):
        """Reload selectors from file."""
        self._load_selectors()

    def get_market_selectors(self, market: str) -> Dict[str, Any]:
        """
        Get all selectors for a market.

        Args:
            market: Market key (amazon_us, cosme_jp)

        Returns:
            Selectors dictionary for the market
        """
        return self._selectors.get(market, {})

    def get_primary(self, market: str, selector_name: str) -> Optional[str]:
        """
        Get a primary selector.

        Args:
            market: Market key
            selector_name: Name of the selector (e.g., 'product_card', 'rank')

        Returns:
            CSS selector string or None
        """
        market_selectors = self.get_market_selectors(market)
        primary = market_selectors.get('primary', {})

        selector_config = primary.get(selector_name)

        if selector_config is None:
            return None

        # Handle both string and dict selector configs
        if isinstance(selector_config, str):
            return selector_config

        if isinstance(selector_config, dict):
            return selector_config.get('css') or selector_config.get('alt_css')

        return None

    def get_fallback(self, market: str, selector_name: str) -> Optional[str]:
        """
        Get a fallback selector.

        Args:
            market: Market key
            selector_name: Name of the selector

        Returns:
            CSS selector string or None
        """
        market_selectors = self.get_market_selectors(market)
        fallback = market_selectors.get('fallback', {})

        selector_config = fallback.get(selector_name)

        if selector_config is None:
            return None

        if isinstance(selector_config, str):
            return selector_config

        if isinstance(selector_config, dict):
            return selector_config.get('css') or selector_config.get('alt_css')

        return None

    def get_heuristic(self, market: str, pattern_name: str) -> Optional[str]:
        """
        Get a heuristic pattern.

        Args:
            market: Market key
            pattern_name: Name of the pattern

        Returns:
            Pattern string or None
        """
        market_selectors = self.get_market_selectors(market)
        heuristic = market_selectors.get('heuristic', {})
        return heuristic.get(pattern_name)

    def get_selector_with_fallback(
        self,
        market: str,
        selector_name: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get both primary and fallback selectors.

        Args:
            market: Market key
            selector_name: Name of the selector

        Returns:
            Tuple of (primary_selector, fallback_selector)
        """
        return (
            self.get_primary(market, selector_name),
            self.get_fallback(market, selector_name)
        )

    def get_attribute(
        self,
        market: str,
        selector_name: str,
        selector_type: str = 'primary'
    ) -> Optional[str]:
        """
        Get the attribute to extract for a selector.

        Args:
            market: Market key
            selector_name: Name of the selector
            selector_type: 'primary' or 'fallback'

        Returns:
            Attribute name or None (None means use text content)
        """
        market_selectors = self.get_market_selectors(market)
        selectors = market_selectors.get(selector_type, {})

        selector_config = selectors.get(selector_name)

        if isinstance(selector_config, dict):
            return selector_config.get('attr')

        return None

    def get_common_patterns(self) -> Dict[str, Any]:
        """Get common patterns used across markets."""
        return self._selectors.get('common', {})

    def get_validation_rules(self) -> Dict[str, Any]:
        """Get validation rules."""
        return self._selectors.get('validation', {})
