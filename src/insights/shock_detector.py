"""
Rank Shock detector for ranking insights.

Identifies products with significant day-to-day rank changes.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RankShock:
    """Information about a rank shock event."""
    product_name: str
    product_url: str
    market: str
    category_key: str
    date: str
    previous_date: str
    previous_rank: int
    new_rank: int
    change: int  # Positive = improved (went up), Negative = dropped
    change_type: str  # "improved" or "dropped"


class ShockDetector:
    """
    Detects significant rank changes between consecutive days.

    A "shock" is defined as an absolute rank change >= threshold.
    """

    def __init__(self, threshold: int = 3):
        """
        Initialize the detector.

        Args:
            threshold: Minimum absolute rank change to be considered a shock
        """
        self.threshold = threshold
        logger.debug(f"ShockDetector initialized with threshold: {threshold}")

    def detect(self, rank_history: List[dict]) -> List[RankShock]:
        """
        Detect rank shocks in ranking history.

        Args:
            rank_history: List of ranking dictionaries from storage

        Returns:
            List of RankShock objects
        """
        if not rank_history:
            return []

        # Group by product
        product_history = self._group_by_product(rank_history)

        shocks = []

        for (product_url, market, category_key), history in product_history.items():
            product_shocks = self._detect_product_shocks(
                history, market, category_key
            )
            shocks.extend(product_shocks)

        # Sort by absolute change magnitude descending, then by date
        shocks.sort(key=lambda s: (-abs(s.change), s.date))

        logger.info(f"Detected {len(shocks)} rank shocks (threshold={self.threshold})")
        return shocks

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

    def _detect_product_shocks(
        self,
        history: List[dict],
        market: str,
        category_key: str
    ) -> List[RankShock]:
        """Detect shocks for a single product."""
        if len(history) < 2:
            return []

        shocks = []
        prev_entry = None

        for entry in history:
            if prev_entry is None:
                prev_entry = entry
                continue

            prev_date = prev_entry.get("date_kst", "")
            curr_date = entry.get("date_kst", "")

            try:
                prev_rank = int(prev_entry.get("rank"))
                curr_rank = int(entry.get("rank"))
            except (ValueError, TypeError):
                prev_entry = entry
                continue

            # Check if consecutive days (or close)
            try:
                prev_dt = datetime.strptime(prev_date, "%Y-%m-%d")
                curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
                days_diff = (curr_dt - prev_dt).days

                # Only consider consecutive or near-consecutive days
                if days_diff > 2:
                    prev_entry = entry
                    continue

            except ValueError:
                prev_entry = entry
                continue

            # Calculate change
            # Lower rank number = better position
            # change > 0 means improved (moved up in rankings)
            # change < 0 means dropped (moved down in rankings)
            change = prev_rank - curr_rank

            if abs(change) >= self.threshold:
                change_type = "improved" if change > 0 else "dropped"

                shock = RankShock(
                    product_name=entry.get("product_name_raw", ""),
                    product_url=entry.get("product_url", ""),
                    market=market,
                    category_key=category_key,
                    date=curr_date,
                    previous_date=prev_date,
                    previous_rank=prev_rank,
                    new_rank=curr_rank,
                    change=change,
                    change_type=change_type
                )
                shocks.append(shock)

            prev_entry = entry

        return shocks

    def get_recent_shocks(
        self,
        rank_history: List[dict],
        days: int = 7
    ) -> List[RankShock]:
        """Get shocks from the last N days."""
        all_shocks = self.detect(rank_history)

        if not all_shocks:
            return []

        # Get most recent date
        dates = [s.date for s in all_shocks]
        latest_date = max(dates)

        try:
            latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
            cutoff_dt = latest_dt - timedelta(days=days)
            cutoff_date = cutoff_dt.strftime("%Y-%m-%d")
        except ValueError:
            return all_shocks

        return [s for s in all_shocks if s.date >= cutoff_date]

    def get_improvements(self, rank_history: List[dict]) -> List[RankShock]:
        """Get only improvements (rank went up)."""
        all_shocks = self.detect(rank_history)
        return [s for s in all_shocks if s.change_type == "improved"]

    def get_drops(self, rank_history: List[dict]) -> List[RankShock]:
        """Get only drops (rank went down)."""
        all_shocks = self.detect(rank_history)
        return [s for s in all_shocks if s.change_type == "dropped"]


# Import timedelta for get_recent_shocks
from datetime import timedelta
