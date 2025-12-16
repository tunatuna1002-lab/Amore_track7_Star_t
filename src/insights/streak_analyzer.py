"""
TopN Streak analyzer for ranking insights.

Identifies products with consecutive days/weeks inside TopN.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StreakInfo:
    """Information about a TopN streak."""
    product_name: str
    product_url: str
    market: str
    category_key: str
    top_n_threshold: int
    streak_days: int
    streak_start: str
    streak_end: str
    current_rank: Optional[int] = None
    is_active: bool = True  # Still in streak as of latest date


class StreakAnalyzer:
    """
    Analyzes TopN streaks for products.

    A streak is consecutive days a product remains in TopN.
    """

    def __init__(self, top_n_thresholds: List[int] = None):
        """
        Initialize the analyzer.

        Args:
            top_n_thresholds: List of TopN thresholds to track (e.g., [5, 10, 100])
        """
        self.top_n_thresholds = top_n_thresholds or [5, 10, 100]
        logger.debug(f"StreakAnalyzer initialized with thresholds: {self.top_n_thresholds}")

    def analyze(self, rank_history: List[dict]) -> List[StreakInfo]:
        """
        Analyze ranking history for TopN streaks.

        Args:
            rank_history: List of ranking dictionaries from storage

        Returns:
            List of StreakInfo objects
        """
        if not rank_history:
            return []

        # Group by product (using product_url as key)
        product_history = self._group_by_product(rank_history)

        streaks = []

        for (product_url, market, category_key), history in product_history.items():
            for threshold in self.top_n_thresholds:
                streak = self._calculate_streak(
                    history,
                    threshold,
                    market,
                    category_key
                )
                if streak and streak.streak_days > 0:
                    streaks.append(streak)

        # Sort by streak length descending
        streaks.sort(key=lambda s: s.streak_days, reverse=True)

        logger.info(f"Found {len(streaks)} TopN streaks")
        return streaks

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

    def _calculate_streak(
        self,
        history: List[dict],
        threshold: int,
        market: str,
        category_key: str
    ) -> Optional[StreakInfo]:
        """
        Calculate the current/longest streak for a product at a threshold.

        Args:
            history: Sorted list of ranking entries for one product
            threshold: TopN threshold
            market: Market identifier
            category_key: Category identifier

        Returns:
            StreakInfo or None
        """
        if not history:
            return None

        # Get product info from most recent entry
        latest = history[-1]
        product_name = latest.get("product_name_raw", "")
        product_url = latest.get("product_url", "")

        # Find streaks
        current_streak_start = None
        current_streak_days = 0
        longest_streak_start = None
        longest_streak_end = None
        longest_streak_days = 0

        prev_date = None

        for entry in history:
            date_str = entry.get("date_kst", "")
            rank = entry.get("rank")

            if not date_str or rank is None:
                continue

            try:
                rank = int(rank)
            except (ValueError, TypeError):
                continue

            in_top_n = rank <= threshold

            if in_top_n:
                if current_streak_start is None:
                    # Start new streak
                    current_streak_start = date_str
                    current_streak_days = 1
                else:
                    # Check if consecutive day
                    try:
                        prev_dt = datetime.strptime(prev_date, "%Y-%m-%d")
                        curr_dt = datetime.strptime(date_str, "%Y-%m-%d")
                        days_diff = (curr_dt - prev_dt).days

                        if days_diff <= 1:
                            # Consecutive, extend streak
                            current_streak_days += 1
                        else:
                            # Gap in data, check if longest
                            if current_streak_days > longest_streak_days:
                                longest_streak_days = current_streak_days
                                longest_streak_start = current_streak_start
                                longest_streak_end = prev_date

                            # Start new streak
                            current_streak_start = date_str
                            current_streak_days = 1

                    except ValueError:
                        # Date parsing error, start fresh
                        current_streak_start = date_str
                        current_streak_days = 1

                prev_date = date_str

            else:
                # Dropped out of TopN
                if current_streak_days > longest_streak_days:
                    longest_streak_days = current_streak_days
                    longest_streak_start = current_streak_start
                    longest_streak_end = prev_date

                current_streak_start = None
                current_streak_days = 0
                prev_date = date_str

        # Check final streak
        is_active = current_streak_start is not None

        if current_streak_days > longest_streak_days:
            longest_streak_days = current_streak_days
            longest_streak_start = current_streak_start
            longest_streak_end = prev_date

        if longest_streak_days == 0:
            return None

        # Get current rank if still active
        current_rank = None
        if is_active:
            try:
                current_rank = int(latest.get("rank"))
            except (ValueError, TypeError):
                pass

        return StreakInfo(
            product_name=product_name,
            product_url=product_url,
            market=market,
            category_key=category_key,
            top_n_threshold=threshold,
            streak_days=longest_streak_days,
            streak_start=longest_streak_start or "",
            streak_end=longest_streak_end or "",
            current_rank=current_rank,
            is_active=is_active
        )

    def get_active_streaks(self, rank_history: List[dict]) -> List[StreakInfo]:
        """Get only currently active streaks."""
        all_streaks = self.analyze(rank_history)
        return [s for s in all_streaks if s.is_active]
