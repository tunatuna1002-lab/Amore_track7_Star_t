"""
Amazon US Best Sellers collector.
"""

import logging
from typing import List

from src.compliance.guard import ComplianceGuard
from src.config.settings import CategoryConfig
from src.parsers.amazon_parser import AmazonParser
from src.parsers.selector_loader import SelectorLoader
from .base_collector import BaseCollector, CollectionResult

logger = logging.getLogger(__name__)


class AmazonCollector(BaseCollector):
    """
    Collector for Amazon US Best Sellers pages.

    Iterates through configured Amazon category URLs,
    handles pagination where available, and collects
    ranking data up to the configured top_n_target.
    """

    MARKET = "amazon_us"

    def __init__(
        self,
        compliance_guard: ComplianceGuard,
        selector_loader: SelectorLoader = None,
        top_n_target: int = 100,
        run_id: str = ""
    ):
        """
        Initialize Amazon collector.

        Args:
            compliance_guard: ComplianceGuard for compliant fetching
            selector_loader: SelectorLoader for parsing selectors
            top_n_target: Target number of items per category
            run_id: Current run ID
        """
        selector_loader = selector_loader or SelectorLoader()
        parser = AmazonParser(selector_loader)

        super().__init__(
            compliance_guard=compliance_guard,
            parser=parser,
            top_n_target=top_n_target,
            run_id=run_id
        )

        logger.info(f"AmazonCollector initialized (top_n={top_n_target})")

    def collect_all(self, categories: List[CategoryConfig]) -> List[CollectionResult]:
        """
        Collect ranking data from all Amazon categories.

        Processes categories sequentially (concurrency=1 per compliance).
        Stops if compliance guard triggers a stop condition.

        Args:
            categories: List of Amazon category configurations

        Returns:
            List of CollectionResult objects
        """
        results = []

        # Filter to only Amazon categories
        amazon_categories = [
            cat for cat in categories
            if cat.market == self.MARKET
        ]

        logger.info(f"Starting Amazon collection: {len(amazon_categories)} categories")

        for idx, category in enumerate(amazon_categories, 1):
            logger.info(
                f"Processing Amazon category {idx}/{len(amazon_categories)}: "
                f"{category.category_key}"
            )

            # Check if we should stop before starting
            if self.guard.is_stopped():
                reason = self.guard.get_stop_reason()
                logger.warning(f"Collection stopped before {category.category_key}: {reason}")
                break

            # Collect this category
            result = self.collect_category(category)
            results.append(result)

            # Log result
            if result.success:
                logger.info(
                    f"Category {category.category_key}: "
                    f"{result.items_collected} items collected"
                )
            else:
                logger.warning(
                    f"Category {category.category_key} failed: "
                    f"{result.error_message}"
                )

            # Check if we should stop after this category
            if self.guard.is_stopped():
                reason = self.guard.get_stop_reason()
                logger.warning(f"Collection stopped after {category.category_key}: {reason}")
                break

        # Summary
        total_items = sum(r.items_collected for r in results)
        successful = sum(1 for r in results if r.success)

        logger.info(
            f"Amazon collection complete: "
            f"{successful}/{len(amazon_categories)} categories successful, "
            f"{total_items} total items"
        )

        return results
