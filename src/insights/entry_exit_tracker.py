"""
New Entry / Exit tracker for ranking insights.

Identifies products that:
- First entered TopN within the lookback period
- Dropped out of TopN within the lookback period
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EntryEvent:
    """Information about a TopN entry event."""
    product_name: str
    product_url: str
    market: str
    category_key: str
    entry_date: str
    entry_rank: int
    top_n_threshold: int
    current_rank: int


@dataclass
class ExitEvent:
    """Information about a TopN exit event."""
    product_name: str
    product_url: str
    market: str
    category_key: str
    exit_date: str
    last_rank_in_top_n: int
    top_n_threshold: int
    days_in_top_n: int


class EntryExitTracker:
    """
    Tracks new entries and exits from TopN rankings.

    - New Entry: First time a product appears in TopN within lookback period
    - Exit: Product was in TopN but no longer is in most recent data
    """

    def __init__(
        self,
        top_n_thresholds: List[int] = None,
        lookback_days: int = 7
    ):
        """
        Initialize the tracker.

        Args:
            top_n_thresholds: List of TopN thresholds to track
            lookback_days: Number of days to look back for new entries
        """
        self.top_n_thresholds = top_n_thresholds or [5, 10, 100]
        self.lookback_days = lookback_days
        logger.debug(
            f"EntryExitTracker initialized: thresholds={self.top_n_thresholds}, "
            f"lookback={lookback_days} days"
        )

    def find_new_entries(self, rank_history: List[dict]) -> List[EntryEvent]:
        """
        Find products that first entered TopN within the lookback period.

        Args:
            rank_history: List of ranking dictionaries from storage

        Returns:
            List of EntryEvent objects
        """
        if not rank_history:
            return []

        # Get date range
        dates = self._get_sorted_dates(rank_history)
        if not dates:
            return []

        latest_date = dates[-1]
        cutoff_date = self._get_cutoff_date(latest_date)

        # Group by product
        product_history = self._group_by_product(rank_history)

        entries = []

        for (product_url, market, category_key), history in product_history.items():
            for threshold in self.top_n_thresholds:
                entry = self._check_new_entry(
                    history, threshold, cutoff_date, latest_date,
                    market, category_key
                )
                if entry:
                    entries.append(entry)

        # Sort by entry date descending
        entries.sort(key=lambda e: e.entry_date, reverse=True)

        logger.info(f"Found {len(entries)} new TopN entries")
        return entries

    def find_exits(self, rank_history: List[dict]) -> List[ExitEvent]:
        """
        Find products that exited TopN within the lookback period.

        Args:
            rank_history: List of ranking dictionaries from storage

        Returns:
            List of ExitEvent objects
        """
        if not rank_history:
            return []

        # Get date range
        dates = self._get_sorted_dates(rank_history)
        if not dates:
            return []

        latest_date = dates[-1]
        cutoff_date = self._get_cutoff_date(latest_date)

        # Group by product
        product_history = self._group_by_product(rank_history)

        exits = []

        for (product_url, market, category_key), history in product_history.items():
            for threshold in self.top_n_thresholds:
                exit_event = self._check_exit(
                    history, threshold, cutoff_date, latest_date,
                    market, category_key
                )
                if exit_event:
                    exits.append(exit_event)

        # Sort by exit date descending
        exits.sort(key=lambda e: e.exit_date, reverse=True)

        logger.info(f"Found {len(exits)} TopN exits")
        return exits

    def _get_sorted_dates(self, rank_history: List[dict]) -> List[str]:
        """Get sorted unique dates from history."""
        dates = set()
        for entry in rank_history:
            date = entry.get("date_kst", "")
            if date:
                dates.add(date)
        return sorted(dates)

    def _get_cutoff_date(self, latest_date: str) -> str:
        """Calculate cutoff date based on lookback period."""
        try:
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
            cutoff_dt = latest_dt - timedelta(days=self.lookback_days)
            return cutoff_dt.strftime("%Y-%m-%d")
        except ValueError:
            return "2000-01-01"

    def _group_by_product(
        self,
        rank_history: List[dict]
    ) -> Dict[Tuple[str, str, str], List[dict]]:
        """Group ranking history by product."""
        grouped = defaultdict(list)

        for entry in rank_history:
            key = (
                entry.get("product_url", ""),
                entry.get("market", ""),
                entry.get("category_key", "")
            )
            grouped[key].append(entry)

        # Sort each product's history by date
        for key in grouped:
            grouped[key].sort(key=lambda x: x.get("date_kst", ""))

        return grouped

    def _check_new_entry(
        self,
        history: List[dict],
        threshold: int,
        cutoff_date: str,
        latest_date: str,
        market: str,
        category_key: str
    ) -> EntryEvent | None:
        """Check if product is a new entry to TopN."""
        if not history:
            return None

        # Find first appearance in TopN
        first_in_top_n = None
        first_rank = None

        for entry in history:
            date = entry.get("date_kst", "")
            try:
                rank = int(entry.get("rank"))
            except (ValueError, TypeError):
                continue

            if rank <= threshold:
                if first_in_top_n is None:
                    first_in_top_n = date
                    first_rank = rank
                break

        if first_in_top_n is None:
            return None

        # Check if first entry is within lookback period
        if first_in_top_n < cutoff_date:
            return None  # Not a new entry, was already in TopN before

        # Get current rank
        latest = history[-1]
        try:
            current_rank = int(latest.get("rank"))
        except (ValueError, TypeError):
            current_rank = 0

        # Verify still in TopN on latest date
        if latest.get("date_kst") != latest_date or current_rank > threshold:
            return None  # Not currently in TopN

        return EntryEvent(
            product_name=latest.get("product_name_raw", ""),
            product_url=latest.get("product_url", ""),
            market=market,
            category_key=category_key,
            entry_date=first_in_top_n,
            entry_rank=first_rank,
            top_n_threshold=threshold,
            current_rank=current_rank
        )

    def _check_exit(
        self,
        history: List[dict],
        threshold: int,
        cutoff_date: str,
        latest_date: str,
        market: str,
        category_key: str
    ) -> ExitEvent | None:
        """Check if product exited TopN within lookback period."""
        if not history:
            return None

        # Get most recent entry
        latest = history[-1]
        latest_entry_date = latest.get("date_kst", "")

        try:
            current_rank = int(latest.get("rank"))
        except (ValueError, TypeError):
            return None

        # If still in TopN on latest date, not an exit
        if latest_entry_date == latest_date and current_rank <= threshold:
            return None

        # Find when they were last in TopN
        last_in_top_n = None
        last_rank_in_top_n = None
        days_in_top_n = 0

        for entry in history:
            date = entry.get("date_kst", "")
            try:
                rank = int(entry.get("rank"))
            except (ValueError, TypeError):
                continue

            if rank <= threshold:
                last_in_top_n = date
                last_rank_in_top_n = rank
                days_in_top_n += 1

        if last_in_top_n is None:
            return None  # Was never in TopN

        # Check if exit is within lookback period
        if last_in_top_n < cutoff_date:
            return None  # Exited before lookback period

        return ExitEvent(
            product_name=latest.get("product_name_raw", ""),
            product_url=latest.get("product_url", ""),
            market=market,
            category_key=category_key,
            exit_date=last_in_top_n,
            last_rank_in_top_n=last_rank_in_top_n,
            top_n_threshold=threshold,
            days_in_top_n=days_in_top_n
        )
