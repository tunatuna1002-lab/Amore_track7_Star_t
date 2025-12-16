"""
Main insights generator combining all insight types.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from src.storage.excel_storage import ExcelStorage
from .streak_analyzer import StreakAnalyzer, StreakInfo
from .shock_detector import ShockDetector, RankShock
from .entry_exit_tracker import EntryExitTracker, EntryEvent, ExitEvent

logger = logging.getLogger(__name__)


@dataclass
class InsightsSummary:
    """Summary of all insights for a run."""
    # TopN Streaks
    active_streaks: List[StreakInfo] = field(default_factory=list)
    longest_streaks: List[StreakInfo] = field(default_factory=list)

    # Rank Shocks
    recent_shocks: List[RankShock] = field(default_factory=list)
    biggest_improvements: List[RankShock] = field(default_factory=list)
    biggest_drops: List[RankShock] = field(default_factory=list)

    # New Entries / Exits
    new_entries: List[EntryEvent] = field(default_factory=list)
    recent_exits: List[ExitEvent] = field(default_factory=list)


class RankingInsights:
    """
    Main insights generator for ranking data.

    Combines:
    - TopN Streak analysis
    - Rank Shock detection
    - New Entry / Exit tracking
    """

    def __init__(
        self,
        storage: ExcelStorage,
        top_n_thresholds: List[int] = None,
        shock_threshold: int = 3,
        lookback_days: int = 7
    ):
        """
        Initialize the insights generator.

        Args:
            storage: ExcelStorage instance for data access
            top_n_thresholds: List of TopN thresholds (default: [5, 10, 100])
            shock_threshold: Minimum rank change for shock detection
            lookback_days: Lookback period for new entries/exits
        """
        self.storage = storage
        self.top_n_thresholds = top_n_thresholds or [5, 10, 100]
        self.shock_threshold = shock_threshold
        self.lookback_days = lookback_days

        # Initialize analyzers
        self.streak_analyzer = StreakAnalyzer(self.top_n_thresholds)
        self.shock_detector = ShockDetector(self.shock_threshold)
        self.entry_exit_tracker = EntryExitTracker(
            self.top_n_thresholds, self.lookback_days
        )

        logger.info(
            f"RankingInsights initialized: thresholds={self.top_n_thresholds}, "
            f"shock_threshold={shock_threshold}, lookback={lookback_days} days"
        )

    def generate(
        self,
        market: Optional[str] = None,
        category_key: Optional[str] = None
    ) -> InsightsSummary:
        """
        Generate all insights for the ranking data.

        Args:
            market: Optional filter by market
            category_key: Optional filter by category

        Returns:
            InsightsSummary with all insights
        """
        logger.info("Generating ranking insights...")

        # Get ranking history
        rank_history = self.storage.get_rank_history(
            market=market,
            category_key=category_key
        )

        if not rank_history:
            logger.warning("No ranking history found")
            return InsightsSummary()

        logger.info(f"Analyzing {len(rank_history)} ranking entries")

        # Generate insights
        summary = InsightsSummary()

        # TopN Streaks
        all_streaks = self.streak_analyzer.analyze(rank_history)
        summary.active_streaks = [s for s in all_streaks if s.is_active][:20]
        summary.longest_streaks = all_streaks[:20]

        # Rank Shocks
        all_shocks = self.shock_detector.detect(rank_history)
        summary.recent_shocks = self.shock_detector.get_recent_shocks(
            rank_history, days=self.lookback_days
        )[:20]
        summary.biggest_improvements = [
            s for s in all_shocks if s.change > 0
        ][:10]
        summary.biggest_drops = [
            s for s in all_shocks if s.change < 0
        ][:10]

        # New Entries / Exits
        summary.new_entries = self.entry_exit_tracker.find_new_entries(rank_history)[:20]
        summary.recent_exits = self.entry_exit_tracker.find_exits(rank_history)[:20]

        logger.info(
            f"Insights generated: "
            f"{len(summary.active_streaks)} active streaks, "
            f"{len(summary.recent_shocks)} recent shocks, "
            f"{len(summary.new_entries)} new entries, "
            f"{len(summary.recent_exits)} exits"
        )

        return summary

    def format_report(self, summary: InsightsSummary) -> str:
        """
        Format insights as a text report.

        Args:
            summary: InsightsSummary object

        Returns:
            Formatted text report
        """
        lines = []
        lines.append("=" * 60)
        lines.append("RANKING INSIGHTS REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Active Streaks
        lines.append("--- TOP N ACTIVE STREAKS ---")
        if summary.active_streaks:
            for streak in summary.active_streaks[:10]:
                lines.append(
                    f"  [{streak.market}] {streak.product_name[:40]}..."
                )
                lines.append(
                    f"    Top{streak.top_n_threshold} for {streak.streak_days} days "
                    f"(current rank: #{streak.current_rank})"
                )
        else:
            lines.append("  No active streaks found")
        lines.append("")

        # Recent Rank Shocks
        lines.append("--- RECENT RANK SHOCKS ---")
        if summary.recent_shocks:
            for shock in summary.recent_shocks[:10]:
                direction = "+" if shock.change > 0 else ""
                lines.append(
                    f"  [{shock.market}] {shock.product_name[:40]}..."
                )
                lines.append(
                    f"    {shock.date}: #{shock.previous_rank} -> #{shock.new_rank} "
                    f"({direction}{shock.change})"
                )
        else:
            lines.append("  No recent rank shocks found")
        lines.append("")

        # New Entries
        lines.append("--- NEW TOP N ENTRIES ---")
        if summary.new_entries:
            for entry in summary.new_entries[:10]:
                lines.append(
                    f"  [{entry.market}] {entry.product_name[:40]}..."
                )
                lines.append(
                    f"    Entered Top{entry.top_n_threshold} on {entry.entry_date} "
                    f"at #{entry.entry_rank} (now #{entry.current_rank})"
                )
        else:
            lines.append("  No new entries found")
        lines.append("")

        # Recent Exits
        lines.append("--- RECENT TOP N EXITS ---")
        if summary.recent_exits:
            for exit_event in summary.recent_exits[:10]:
                lines.append(
                    f"  [{exit_event.market}] {exit_event.product_name[:40]}..."
                )
                lines.append(
                    f"    Left Top{exit_event.top_n_threshold} on {exit_event.exit_date} "
                    f"(was #{exit_event.last_rank_in_top_n}, in top for {exit_event.days_in_top_n} days)"
                )
        else:
            lines.append("  No recent exits found")
        lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def print_report(self, summary: InsightsSummary = None):
        """Print the insights report to console."""
        if summary is None:
            summary = self.generate()

        report = self.format_report(summary)
        try:
            print(report)
        except UnicodeEncodeError:
            # Handle encoding issues on Windows with cp949
            print(report.encode('utf-8', errors='replace').decode('utf-8'))
