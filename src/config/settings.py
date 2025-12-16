"""
Settings dataclass for type-safe configuration access.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from pathlib import Path

from src.utils.config_loader import load_config, load_selectors


@dataclass
class ComplianceSettings:
    """Compliance-related settings."""
    daily_budget: int = 25
    delay_range_s: Tuple[float, float] = (3.0, 8.0)
    respect_robots_crawl_delay: bool = True
    max_retries: int = 3
    backoff_base_s: float = 5.0
    backoff_multiplier: float = 2.0
    consecutive_failure_limit: int = 5
    concurrency: int = 1
    user_agent: str = "LaneigeRankingBot/1.0 (Research Project)"


@dataclass
class CollectionSettings:
    """Data collection settings."""
    top_n_target: int = 100
    brand_filter_enabled: bool = False
    brand_filter_keywords: List[str] = field(default_factory=lambda: ["laneige", "라네즈"])
    schedule_kst: str = "09:00"
    timezone: str = "Asia/Seoul"


@dataclass
class StorageSettings:
    """Storage settings."""
    output_file: str = "data/ranking_data.xlsx"
    rank_history_sheet: str = "rank_history_min"
    run_log_sheet: str = "run_log"


@dataclass
class InsightsSettings:
    """Insights generation settings."""
    top_n_thresholds: List[int] = field(default_factory=lambda: [5, 10, 100])
    rank_shock_threshold: int = 3
    lookback_days: int = 7


@dataclass
class CategoryConfig:
    """Configuration for a single category."""
    url: str
    category_key: str
    market: str  # amazon_us or cosme_jp


@dataclass
class Settings:
    """
    Main settings container with all configuration.

    Provides type-safe access to all configuration values.
    """
    compliance: ComplianceSettings
    collection: CollectionSettings
    storage: StorageSettings
    insights: InsightsSettings
    categories: List[CategoryConfig]

    @classmethod
    def from_yaml(cls, config_path: str = None) -> "Settings":
        """
        Load settings from config.yaml.

        Args:
            config_path: Optional path to config file

        Returns:
            Settings instance
        """
        config = load_config(config_path)

        # Parse compliance settings
        comp_cfg = config.get('compliance', {})
        delay_range = comp_cfg.get('delay_range_s', {})
        compliance = ComplianceSettings(
            daily_budget=comp_cfg.get('daily_budget', 25),
            delay_range_s=(
                delay_range.get('min', 3.0),
                delay_range.get('max', 8.0)
            ),
            respect_robots_crawl_delay=comp_cfg.get('respect_robots_crawl_delay', True),
            max_retries=comp_cfg.get('retry', {}).get('max_retries', 3),
            backoff_base_s=comp_cfg.get('retry', {}).get('backoff_base_s', 5.0),
            backoff_multiplier=comp_cfg.get('retry', {}).get('backoff_multiplier', 2.0),
            consecutive_failure_limit=comp_cfg.get('consecutive_failure_limit', 5),
            concurrency=comp_cfg.get('concurrency', 1),
            user_agent=comp_cfg.get('user_agent', "LaneigeRankingBot/1.0")
        )

        # Parse collection settings
        coll_cfg = config.get('collection', {})
        brand_filter = coll_cfg.get('brand_filter', {})
        collection = CollectionSettings(
            top_n_target=coll_cfg.get('top_n_target', 100),
            brand_filter_enabled=brand_filter.get('enabled', False),
            brand_filter_keywords=brand_filter.get('keywords', ['laneige']),
            schedule_kst=coll_cfg.get('schedule_kst', '09:00'),
            timezone=coll_cfg.get('timezone', 'Asia/Seoul')
        )

        # Parse storage settings
        stor_cfg = config.get('storage', {})
        sheets = stor_cfg.get('sheets', {})
        storage = StorageSettings(
            output_file=stor_cfg.get('output_file', 'data/ranking_data.xlsx'),
            rank_history_sheet=sheets.get('rank_history', 'rank_history_min'),
            run_log_sheet=sheets.get('run_log', 'run_log')
        )

        # Parse insights settings
        ins_cfg = config.get('insights', {})
        insights = InsightsSettings(
            top_n_thresholds=ins_cfg.get('top_n_thresholds', [5, 10, 100]),
            rank_shock_threshold=ins_cfg.get('rank_shock_threshold', 3),
            lookback_days=ins_cfg.get('lookback_days', 7)
        )

        # Parse categories
        categories = [
            CategoryConfig(
                url=cat['url'],
                category_key=cat['category_key'],
                market=cat['market']
            )
            for cat in config.get('categories', [])
        ]

        return cls(
            compliance=compliance,
            collection=collection,
            storage=storage,
            insights=insights,
            categories=categories
        )

    def get_categories_by_market(self, market: str) -> List[CategoryConfig]:
        """Get all categories for a specific market."""
        return [cat for cat in self.categories if cat.market == market]

    def get_amazon_categories(self) -> List[CategoryConfig]:
        """Get Amazon US categories."""
        return self.get_categories_by_market('amazon_us')

    def get_cosme_categories(self) -> List[CategoryConfig]:
        """Get @cosme JP categories."""
        return self.get_categories_by_market('cosme_jp')
