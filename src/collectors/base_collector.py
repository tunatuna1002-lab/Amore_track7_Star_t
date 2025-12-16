"""
Base collector with common collection functionality.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from src.compliance.guard import ComplianceGuard, FetchResult
from src.config.settings import CategoryConfig
from src.parsers.base_parser import BaseParser, ParseResult, ParseStatus, RankingItem
from src.utils.time_utils import format_kst_date

logger = logging.getLogger(__name__)


@dataclass
class RankingSnapshot:
    """A single ranking entry ready for storage."""
    date_kst: str
    market: str
    category_key: str
    category_url: str
    rank: int
    product_name_raw: str
    brand_raw: Optional[str]
    product_url: str
    run_id: str
    parse_status: str
    notes: str = ""


@dataclass
class CollectionResult:
    """Result of collecting data from a category."""
    category_key: str
    success: bool
    snapshots: List[RankingSnapshot] = field(default_factory=list)
    pages_fetched: int = 0
    items_collected: int = 0
    error_message: Optional[str] = None
    parse_status: ParseStatus = ParseStatus.OK


class BaseCollector(ABC):
    """
    Abstract base collector for ranking data.

    Provides common functionality for:
    - Compliant fetching via ComplianceGuard
    - Pagination handling
    - Snapshot creation
    """

    # Market identifier
    MARKET: str = ""

    def __init__(
        self,
        compliance_guard: ComplianceGuard,
        parser: BaseParser,
        top_n_target: int = 100,
        run_id: str = ""
    ):
        """
        Initialize the collector.

        Args:
            compliance_guard: ComplianceGuard for compliant fetching
            parser: Parser for the market
            top_n_target: Target number of items to collect
            run_id: Current run ID
        """
        self.guard = compliance_guard
        self.parser = parser
        self.top_n_target = top_n_target
        self.run_id = run_id

    def collect_category(self, category: CategoryConfig) -> CollectionResult:
        """
        Collect ranking data for a single category.

        Args:
            category: Category configuration

        Returns:
            CollectionResult with snapshots
        """
        logger.info(f"Collecting: {category.category_key} from {category.market}")

        snapshots = []
        pages_fetched = 0
        items_collected = 0
        overall_status = ParseStatus.OK
        current_url = category.url

        while items_collected < self.top_n_target and current_url:
            # Check if we should stop
            if self.guard.is_stopped():
                reason = self.guard.get_stop_reason()
                logger.warning(f"Collection stopped: {reason}")
                return CollectionResult(
                    category_key=category.category_key,
                    success=False,
                    snapshots=snapshots,
                    pages_fetched=pages_fetched,
                    items_collected=items_collected,
                    error_message=f"Stopped: {reason}",
                    parse_status=overall_status
                )

            # Fetch the page
            fetch_result = self.guard.fetch(current_url)

            if not fetch_result.success:
                logger.warning(f"Fetch failed: {current_url} - {fetch_result.error}")

                if pages_fetched == 0:
                    # First page failed - category collection failed
                    return CollectionResult(
                        category_key=category.category_key,
                        success=False,
                        snapshots=snapshots,
                        pages_fetched=pages_fetched,
                        items_collected=items_collected,
                        error_message=fetch_result.error,
                        parse_status=ParseStatus.FAILED
                    )
                else:
                    # Subsequent page failed - return what we have
                    overall_status = ParseStatus.PARTIAL
                    break

            pages_fetched += 1

            # Parse the page
            parse_result = self.parser.parse(
                fetch_result.content,
                current_url,
                self.top_n_target - items_collected
            )

            if parse_result.status == ParseStatus.FAILED:
                logger.warning(f"Parse failed: {current_url}")
                if pages_fetched == 1:
                    return CollectionResult(
                        category_key=category.category_key,
                        success=False,
                        snapshots=snapshots,
                        pages_fetched=pages_fetched,
                        items_collected=items_collected,
                        error_message=parse_result.error_message,
                        parse_status=ParseStatus.FAILED
                    )
                else:
                    overall_status = ParseStatus.PARTIAL
                    break

            if parse_result.status == ParseStatus.PARTIAL:
                overall_status = ParseStatus.PARTIAL

            # Convert items to snapshots
            date_kst = format_kst_date()
            for item in parse_result.items:
                snapshot = self._create_snapshot(
                    item=item,
                    category=category,
                    date_kst=date_kst,
                    parse_status=parse_result.status.value,
                    notes=parse_result.notes
                )
                snapshots.append(snapshot)
                items_collected += 1

            logger.info(
                f"Page {pages_fetched}: extracted {len(parse_result.items)} items, "
                f"total: {items_collected}"
            )

            # Check for next page
            current_url = parse_result.next_page_url

            # Stop if we have enough items
            if items_collected >= self.top_n_target:
                break

            # Stop if no more pages
            if not current_url:
                break

        success = items_collected > 0 and overall_status != ParseStatus.FAILED

        logger.info(
            f"Category {category.category_key} complete: "
            f"{items_collected} items from {pages_fetched} pages, "
            f"status={overall_status.value}"
        )

        return CollectionResult(
            category_key=category.category_key,
            success=success,
            snapshots=snapshots,
            pages_fetched=pages_fetched,
            items_collected=items_collected,
            parse_status=overall_status
        )

    def _create_snapshot(
        self,
        item: RankingItem,
        category: CategoryConfig,
        date_kst: str,
        parse_status: str,
        notes: str = ""
    ) -> RankingSnapshot:
        """Create a ranking snapshot from a parsed item."""
        combined_notes = item.notes
        if notes:
            combined_notes = f"{notes}; {item.notes}" if item.notes else notes

        return RankingSnapshot(
            date_kst=date_kst,
            market=category.market,
            category_key=category.category_key,
            category_url=category.url,
            rank=item.rank,
            product_name_raw=item.product_name_raw,
            brand_raw=item.brand_raw,
            product_url=item.product_url,
            run_id=self.run_id,
            parse_status=parse_status,
            notes=combined_notes
        )

    @abstractmethod
    def collect_all(self, categories: List[CategoryConfig]) -> List[CollectionResult]:
        """
        Collect data from all categories.

        Must be implemented by subclasses.

        Args:
            categories: List of category configurations

        Returns:
            List of CollectionResult objects
        """
        pass
