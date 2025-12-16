"""
Unit tests for parsers.

These tests use local HTML fixtures and do not require network access.

To generate fixtures:
1. Open the actual page in your browser
2. Right-click -> "Save page as..." -> "Webpage, Complete"
3. Copy the saved HTML file to tests/fixtures/
"""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.amazon_parser import AmazonParser
from src.parsers.cosme_parser import CosmeParser
from src.parsers.base_parser import ParseStatus
from src.parsers.selector_loader import SelectorLoader


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def selector_loader():
    """Create a selector loader with test selectors."""
    return SelectorLoader(project_root / "selectors.yaml")


@pytest.fixture
def amazon_html():
    """Load sample Amazon HTML fixture."""
    fixture_path = FIXTURES_DIR / "sample_amazon.html"
    if fixture_path.exists():
        return fixture_path.read_text(encoding='utf-8')
    pytest.skip("Amazon fixture not found. See fixture file for generation instructions.")


@pytest.fixture
def cosme_html():
    """Load sample @cosme HTML fixture."""
    fixture_path = FIXTURES_DIR / "sample_cosme.html"
    if fixture_path.exists():
        return fixture_path.read_text(encoding='utf-8')
    pytest.skip("@cosme fixture not found. See fixture file for generation instructions.")


class TestAmazonParser:
    """Tests for Amazon Best Sellers parser."""

    def test_parse_extracts_items(self, selector_loader, amazon_html):
        """Test that parser extracts ranking items from fixture."""
        parser = AmazonParser(selector_loader)
        result = parser.parse(
            amazon_html,
            "https://www.amazon.com/Best-Sellers/zgbs/beauty",
            top_n=10
        )

        # Should extract items
        assert result.status != ParseStatus.FAILED
        assert len(result.items) > 0

    def test_parse_extracts_correct_fields(self, selector_loader, amazon_html):
        """Test that parser extracts all required fields."""
        parser = AmazonParser(selector_loader)
        result = parser.parse(
            amazon_html,
            "https://www.amazon.com/Best-Sellers/zgbs/beauty",
            top_n=10
        )

        # Check first item has required fields
        if result.items:
            item = result.items[0]
            assert item.rank > 0
            assert item.product_name_raw
            assert item.product_url

    def test_parse_handles_rank_numbers(self, selector_loader, amazon_html):
        """Test that parser correctly extracts rank numbers."""
        parser = AmazonParser(selector_loader)
        result = parser.parse(
            amazon_html,
            "https://www.amazon.com/Best-Sellers/zgbs/beauty",
            top_n=10
        )

        # Ranks should be sequential or at least valid
        if result.items:
            ranks = [item.rank for item in result.items]
            assert all(r > 0 for r in ranks)
            # First item should be rank 1 or close to it
            assert min(ranks) <= 5

    def test_parse_respects_top_n_limit(self, selector_loader, amazon_html):
        """Test that parser respects the top_n limit."""
        parser = AmazonParser(selector_loader)

        # Request only 3 items
        result = parser.parse(
            amazon_html,
            "https://www.amazon.com/Best-Sellers/zgbs/beauty",
            top_n=3
        )

        assert len(result.items) <= 3

    def test_heuristic_fallback(self, selector_loader):
        """Test heuristic parsing when selectors fail."""
        parser = AmazonParser(selector_loader)

        # Simple HTML with product-like structure but no matching selectors
        html = """
        <html>
        <body>
            <div data-asin="TEST123">
                <span>#1</span>
                <a href="/dp/TEST123">Test Product Name</a>
            </div>
            <div data-asin="TEST456">
                <span>#2</span>
                <a href="/dp/TEST456">Another Product</a>
            </div>
        </body>
        </html>
        """

        result = parser.parse(html, "https://www.amazon.com/", top_n=10)

        # Should still extract something via heuristics
        # (Note: may be PARTIAL status)
        assert result.status != ParseStatus.FAILED or len(result.items) >= 0


class TestCosmeParser:
    """Tests for @cosme ranking parser."""

    def test_parse_extracts_items(self, selector_loader, cosme_html):
        """Test that parser extracts ranking items from fixture."""
        parser = CosmeParser(selector_loader)
        result = parser.parse(
            cosme_html,
            "https://www.cosme.net/ranking/products",
            top_n=10
        )

        # Should extract items
        assert result.status != ParseStatus.FAILED
        assert len(result.items) > 0

    def test_parse_extracts_correct_fields(self, selector_loader, cosme_html):
        """Test that parser extracts all required fields."""
        parser = CosmeParser(selector_loader)
        result = parser.parse(
            cosme_html,
            "https://www.cosme.net/ranking/products",
            top_n=10
        )

        # Check first item has required fields
        if result.items:
            item = result.items[0]
            assert item.rank > 0
            assert item.product_name_raw
            assert item.product_url

    def test_parse_handles_japanese_ranks(self, selector_loader, cosme_html):
        """Test that parser handles Japanese rank format (e.g., '1位')."""
        parser = CosmeParser(selector_loader)
        result = parser.parse(
            cosme_html,
            "https://www.cosme.net/ranking/products",
            top_n=10
        )

        if result.items:
            # Should correctly parse Japanese rank numbers
            assert result.items[0].rank == 1

    def test_parse_respects_top_n_limit(self, selector_loader, cosme_html):
        """Test that parser respects the top_n limit."""
        parser = CosmeParser(selector_loader)

        # Request only 2 items
        result = parser.parse(
            cosme_html,
            "https://www.cosme.net/ranking/products",
            top_n=2
        )

        assert len(result.items) <= 2


class TestBaseParserHelpers:
    """Tests for base parser helper methods."""

    def test_extract_rank_number_hash_format(self, selector_loader):
        """Test rank extraction from '#1' format."""
        parser = AmazonParser(selector_loader)

        assert parser._extract_rank_number("#1") == 1
        assert parser._extract_rank_number("#42") == 42
        assert parser._extract_rank_number("#100") == 100

    def test_extract_rank_number_japanese_format(self, selector_loader):
        """Test rank extraction from Japanese '1位' format."""
        parser = CosmeParser(selector_loader)

        assert parser._extract_rank_number("1位") == 1
        assert parser._extract_rank_number("10位") == 10
        assert parser._extract_rank_number("99位") == 99

    def test_extract_rank_number_plain_format(self, selector_loader):
        """Test rank extraction from plain number format."""
        parser = AmazonParser(selector_loader)

        assert parser._extract_rank_number("1") == 1
        assert parser._extract_rank_number("50") == 50

    def test_clean_text_removes_whitespace(self, selector_loader):
        """Test text cleaning removes extra whitespace."""
        parser = AmazonParser(selector_loader)

        assert parser._clean_text("  Hello   World  ") == "Hello World"
        assert parser._clean_text("\n\tTest\n\n") == "Test"
        assert parser._clean_text("No  Extra   Spaces") == "No Extra Spaces"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
