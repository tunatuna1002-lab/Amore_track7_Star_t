"""
Unit tests for insights module.

Tests insight generation with mock ranking data.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.insights.streak_analyzer import StreakAnalyzer
from src.insights.shock_detector import ShockDetector
from src.insights.entry_exit_tracker import EntryExitTracker


class TestStreakAnalyzer:
    """Tests for TopN streak analysis."""

    @pytest.fixture
    def sample_history(self):
        """Sample ranking history for testing."""
        return [
            # Product A: 5-day streak in Top5
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 3},
            {"date_kst": "2024-01-02", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 2},
            {"date_kst": "2024-01-03", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 4},
            {"date_kst": "2024-01-04", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 5},
            {"date_kst": "2024-01-05", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 3},

            # Product B: Enters and exits Top5
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 8},
            {"date_kst": "2024-01-02", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 4},
            {"date_kst": "2024-01-03", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 10},
        ]

    def test_finds_streaks(self, sample_history):
        """Test that analyzer finds TopN streaks."""
        analyzer = StreakAnalyzer(top_n_thresholds=[5, 10])
        streaks = analyzer.analyze(sample_history)

        assert len(streaks) > 0

    def test_calculates_streak_length(self, sample_history):
        """Test correct streak length calculation."""
        analyzer = StreakAnalyzer(top_n_thresholds=[5])
        streaks = analyzer.analyze(sample_history)

        # Find Product A's streak
        product_a_streaks = [s for s in streaks if "Product A" in s.product_name]

        # Product A should have a 5-day Top5 streak
        if product_a_streaks:
            assert product_a_streaks[0].streak_days == 5

    def test_identifies_active_streaks(self, sample_history):
        """Test identification of active vs ended streaks."""
        analyzer = StreakAnalyzer(top_n_thresholds=[5])
        active = analyzer.get_active_streaks(sample_history)

        # Product A should have an active streak (last entry is rank 3)
        product_a_active = [s for s in active if "Product A" in s.product_name]
        assert len(product_a_active) > 0


class TestShockDetector:
    """Tests for rank shock detection."""

    @pytest.fixture
    def sample_history(self):
        """Sample ranking history with rank changes."""
        return [
            # Product A: Big improvement
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 20},
            {"date_kst": "2024-01-02", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 5},

            # Product B: Big drop
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 3},
            {"date_kst": "2024-01-02", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 15},

            # Product C: Small change (no shock)
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/c", "product_name_raw": "Product C", "rank": 10},
            {"date_kst": "2024-01-02", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/c", "product_name_raw": "Product C", "rank": 11},
        ]

    def test_detects_shocks(self, sample_history):
        """Test that detector finds rank shocks."""
        detector = ShockDetector(threshold=3)
        shocks = detector.detect(sample_history)

        # Should find shocks for Product A and B, not C
        assert len(shocks) == 2

    def test_calculates_change_correctly(self, sample_history):
        """Test correct change calculation."""
        detector = ShockDetector(threshold=3)
        shocks = detector.detect(sample_history)

        # Product A improved from 20 to 5: change = +15
        product_a_shocks = [s for s in shocks if "Product A" in s.product_name]
        if product_a_shocks:
            assert product_a_shocks[0].change == 15
            assert product_a_shocks[0].change_type == "improved"

        # Product B dropped from 3 to 15: change = -12
        product_b_shocks = [s for s in shocks if "Product B" in s.product_name]
        if product_b_shocks:
            assert product_b_shocks[0].change == -12
            assert product_b_shocks[0].change_type == "dropped"

    def test_respects_threshold(self, sample_history):
        """Test that detector respects the threshold setting."""
        # With high threshold, should find fewer shocks
        detector = ShockDetector(threshold=20)
        shocks = detector.detect(sample_history)

        # Only Product A and B should qualify (changes of 15 and 12)
        # With threshold 20, neither qualifies
        assert len(shocks) == 0


class TestEntryExitTracker:
    """Tests for new entry and exit tracking."""

    @pytest.fixture
    def sample_history(self):
        """Sample ranking history for entry/exit testing."""
        return [
            # Product A: Was in Top10 from day 1
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 5},
            {"date_kst": "2024-01-07", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/a", "product_name_raw": "Product A", "rank": 3},

            # Product B: New entry on day 5
            {"date_kst": "2024-01-05", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 8},
            {"date_kst": "2024-01-07", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/b", "product_name_raw": "Product B", "rank": 6},

            # Product C: Was in Top10, then exited
            {"date_kst": "2024-01-01", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/c", "product_name_raw": "Product C", "rank": 7},
            {"date_kst": "2024-01-03", "market": "amazon_us", "category_key": "beauty",
             "product_url": "https://example.com/c", "product_name_raw": "Product C", "rank": 15},
        ]

    def test_finds_new_entries(self, sample_history):
        """Test finding new TopN entries."""
        tracker = EntryExitTracker(top_n_thresholds=[10], lookback_days=7)
        entries = tracker.find_new_entries(sample_history)

        # Product B should be a new entry (first appeared on day 5)
        product_b_entries = [e for e in entries if "Product B" in e.product_name]
        assert len(product_b_entries) > 0

    def test_finds_exits(self, sample_history):
        """Test finding TopN exits."""
        tracker = EntryExitTracker(top_n_thresholds=[10], lookback_days=7)
        exits = tracker.find_exits(sample_history)

        # Product C exited Top10 (went from 7 to 15)
        product_c_exits = [e for e in exits if "Product C" in e.product_name]
        assert len(product_c_exits) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
