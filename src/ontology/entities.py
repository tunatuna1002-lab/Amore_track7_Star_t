"""
Entity definitions for the ranking ontology.

These dataclasses represent the core entities in our knowledge graph:
- ProductNode: Individual products being tracked
- CategoryNode: Ranking categories (e.g., Lip Care, Skin Care)
- PlatformNode: E-commerce platforms (Amazon US, @cosme Japan)
- RankingRecord: Time-series ranking snapshots
- BrandNode: Brand information (Phase 2)
- EventNode: Events affecting rankings (Phase 2)

Reference: docs/ontology_schema.yaml
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class Market(str, Enum):
    """Supported markets/platforms."""
    AMAZON_US = "amazon_us"
    COSME_JP = "cosme_jp"


class RankingType(str, Enum):
    """Type of ranking methodology."""
    SALES_BASED = "sales_based"      # Amazon BSR
    REVIEW_BASED = "review_based"    # @cosme


class ParseStatus(str, Enum):
    """Parsing result status."""
    FULL = "full"           # All fields extracted
    PARTIAL = "partial"     # Some fields missing
    HEURISTIC = "heuristic" # Used fallback/heuristic parsing


class EventType(str, Enum):
    """Types of events that affect rankings."""
    PRIME_DAY = "prime_day"
    BLACK_FRIDAY = "black_friday"
    COSME_AWARDS = "cosme_awards"
    PRODUCT_LAUNCH = "product_launch"
    PROMOTION = "promotion"
    SEASONAL = "seasonal"


# =============================================================================
# Core Entities (Phase 1)
# =============================================================================

@dataclass
class ProductNode:
    """
    Represents a product in the knowledge graph.
    
    Attributes:
        product_id: Unique identifier (MD5 hash of product_url)
        product_name_raw: Original product name as scraped
        product_url: Product detail page URL
        product_name_normalized: Cleaned/normalized name (optional)
        brand: Brand name if available
        first_seen: Date first observed in rankings
        last_seen: Date last observed in rankings
        metadata: Additional product attributes
    """
    product_id: str
    product_name_raw: str
    product_url: str
    product_name_normalized: Optional[str] = None
    brand: Optional[str] = None
    first_seen: Optional[str] = None  # YYYY-MM-DD
    last_seen: Optional[str] = None   # YYYY-MM-DD
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def generate_id(cls, product_url: str) -> str:
        """Generate deterministic product ID from URL."""
        return hashlib.md5(product_url.encode()).hexdigest()
    
    @classmethod
    def from_snapshot(cls, snapshot_dict: dict) -> "ProductNode":
        """
        Create ProductNode from a ranking snapshot dictionary.
        
        Args:
            snapshot_dict: Dictionary with product data
            
        Returns:
            ProductNode instance
        """
        product_url = snapshot_dict.get("product_url", "")
        return cls(
            product_id=cls.generate_id(product_url),
            product_name_raw=snapshot_dict.get("product_name_raw", ""),
            product_url=product_url,
            brand=snapshot_dict.get("brand_raw"),
            first_seen=snapshot_dict.get("date_kst"),
            last_seen=snapshot_dict.get("date_kst"),
        )
    
    def update_seen_dates(self, date_kst: str):
        """Update first_seen and last_seen dates."""
        if self.first_seen is None or date_kst < self.first_seen:
            self.first_seen = date_kst
        if self.last_seen is None or date_kst > self.last_seen:
            self.last_seen = date_kst
    
    @property
    def node_type(self) -> str:
        return "Product"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "node_type": self.node_type,
            "product_id": self.product_id,
            "product_name_raw": self.product_name_raw,
            "product_url": self.product_url,
            "product_name_normalized": self.product_name_normalized,
            "brand": self.brand,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }


@dataclass
class CategoryNode:
    """
    Represents a ranking category.
    
    Attributes:
        category_id: Unique identifier (market + category_key)
        category_key: Config key (e.g., "lip_care")
        category_name: Display name
        category_url: Category page URL
        platform_id: Associated platform
    """
    category_id: str
    category_key: str
    category_name: str
    category_url: str
    platform_id: str  # Market enum value
    
    @classmethod
    def generate_id(cls, market: str, category_key: str) -> str:
        """Generate category ID from market and key."""
        return f"{market}_{category_key}"
    
    @classmethod
    def from_config(cls, market: str, category_key: str, category_config: dict) -> "CategoryNode":
        """Create CategoryNode from config dictionary."""
        return cls(
            category_id=cls.generate_id(market, category_key),
            category_key=category_key,
            category_name=category_config.get("name", category_key),
            category_url=category_config.get("url", ""),
            platform_id=market,
        )
    
    @property
    def node_type(self) -> str:
        return "Category"
    
    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "category_id": self.category_id,
            "category_key": self.category_key,
            "category_name": self.category_name,
            "category_url": self.category_url,
            "platform_id": self.platform_id,
        }


@dataclass
class PlatformNode:
    """
    Represents an e-commerce platform.
    
    Attributes:
        platform_id: Unique identifier (market enum value)
        platform_name: Display name
        base_url: Platform base URL
        ranking_type: Type of ranking (sales_based, review_based)
        update_frequency: How often rankings update
    """
    platform_id: str
    platform_name: str
    base_url: str
    ranking_type: RankingType
    update_frequency: str  # e.g., "hourly", "semi-annual"
    
    @property
    def node_type(self) -> str:
        return "Platform"
    
    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "platform_id": self.platform_id,
            "platform_name": self.platform_name,
            "base_url": self.base_url,
            "ranking_type": self.ranking_type.value,
            "update_frequency": self.update_frequency,
        }


# Pre-defined platform instances
PLATFORMS = {
    Market.AMAZON_US: PlatformNode(
        platform_id=Market.AMAZON_US.value,
        platform_name="Amazon US",
        base_url="https://www.amazon.com",
        ranking_type=RankingType.SALES_BASED,
        update_frequency="hourly",
    ),
    Market.COSME_JP: PlatformNode(
        platform_id=Market.COSME_JP.value,
        platform_name="@cosme Japan",
        base_url="https://www.cosme.net",
        ranking_type=RankingType.REVIEW_BASED,
        update_frequency="semi-annual",
    ),
}


@dataclass
class RankingRecord:
    """
    Represents a single ranking observation (time-series data point).
    
    This is the edge data connecting Product to a specific rank at a point in time.
    
    Attributes:
        ranking_id: Unique identifier (MD5 of composite key)
        product_id: Reference to ProductNode
        category_id: Reference to CategoryNode
        platform_id: Reference to PlatformNode
        rank: Numeric rank (1-100)
        recorded_at: Timestamp of observation (date_kst)
        source_url: URL where ranking was observed
        price: Product price if available
        review_count: Number of reviews if available
        rating: Product rating if available
        parse_status: How the data was extracted
        run_id: Collection run identifier
    """
    ranking_id: str
    product_id: str
    category_id: str
    platform_id: str
    rank: int
    recorded_at: str  # YYYY-MM-DD
    source_url: str
    price: Optional[float] = None
    review_count: Optional[int] = None
    rating: Optional[float] = None
    parse_status: ParseStatus = ParseStatus.FULL
    run_id: Optional[str] = None
    
    @classmethod
    def generate_id(
        cls,
        date_kst: str,
        market: str,
        category_key: str,
        rank: int,
        product_url: str
    ) -> str:
        """Generate deterministic ranking ID from composite key."""
        key_parts = [date_kst, market, category_key, str(rank), product_url]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @classmethod
    def from_snapshot(cls, snapshot_dict: dict) -> "RankingRecord":
        """Create RankingRecord from a ranking snapshot dictionary."""
        date_kst = snapshot_dict.get("date_kst", "")
        market = snapshot_dict.get("market", "")
        category_key = snapshot_dict.get("category_key", "")
        rank = snapshot_dict.get("rank", 0)
        product_url = snapshot_dict.get("product_url", "")
        
        return cls(
            ranking_id=cls.generate_id(date_kst, market, category_key, rank, product_url),
            product_id=ProductNode.generate_id(product_url),
            category_id=CategoryNode.generate_id(market, category_key),
            platform_id=market,
            rank=int(rank) if rank else 0,
            recorded_at=date_kst,
            source_url=snapshot_dict.get("category_url", ""),
            parse_status=ParseStatus(snapshot_dict.get("parse_status", "full")),
            run_id=snapshot_dict.get("run_id"),
        )
    
    @property
    def node_type(self) -> str:
        return "Ranking"
    
    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "ranking_id": self.ranking_id,
            "product_id": self.product_id,
            "category_id": self.category_id,
            "platform_id": self.platform_id,
            "rank": self.rank,
            "recorded_at": self.recorded_at,
            "source_url": self.source_url,
            "price": self.price,
            "review_count": self.review_count,
            "rating": self.rating,
            "parse_status": self.parse_status.value,
            "run_id": self.run_id,
        }


# =============================================================================
# Extended Entities (Phase 2)
# =============================================================================

@dataclass
class BrandNode:
    """
    Represents a brand in the knowledge graph.
    
    Attributes:
        brand_id: Unique identifier
        brand_name: Brand name
        parent_company: Parent company (e.g., "Amorepacific")
        target_markets: List of target markets
        hero_products: List of flagship product IDs
    """
    brand_id: str
    brand_name: str
    parent_company: Optional[str] = None
    target_markets: List[str] = field(default_factory=list)
    hero_products: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def generate_id(cls, brand_name: str) -> str:
        """Generate brand ID from normalized name."""
        normalized = brand_name.lower().strip().replace(" ", "_")
        return hashlib.md5(normalized.encode()).hexdigest()[:12]
    
    @property
    def node_type(self) -> str:
        return "Brand"
    
    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
            "parent_company": self.parent_company,
            "target_markets": self.target_markets,
            "hero_products": self.hero_products,
            "metadata": self.metadata,
        }


# Pre-defined brand for Laneige
LANEIGE_BRAND = BrandNode(
    brand_id="laneige",
    brand_name="LANEIGE",
    parent_company="Amorepacific",
    target_markets=["global", "us", "japan", "korea"],
    hero_products=[],  # Populated dynamically
    metadata={
        "founded": 1994,
        "headquarters": "Seoul, South Korea",
        "category_focus": ["skincare", "lip care"],
    }
)


@dataclass
class EventNode:
    """
    Represents an event that may affect rankings.
    
    Attributes:
        event_id: Unique identifier
        event_type: Type of event
        event_name: Human-readable name
        event_date: Date of event
        end_date: End date for multi-day events
        platform_id: Affected platform (None for global)
        impact_scope: Scope of impact
        description: Event description
    """
    event_id: str
    event_type: EventType
    event_name: str
    event_date: str  # YYYY-MM-DD
    end_date: Optional[str] = None
    platform_id: Optional[str] = None
    impact_scope: str = "global"  # global, category, brand
    description: Optional[str] = None
    
    @classmethod
    def generate_id(cls, event_type: str, event_date: str, platform_id: str = "") -> str:
        """Generate event ID."""
        key = f"{event_type}|{event_date}|{platform_id}"
        return hashlib.md5(key.encode()).hexdigest()[:12]
    
    @property
    def node_type(self) -> str:
        return "Event"
    
    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_name": self.event_name,
            "event_date": self.event_date,
            "end_date": self.end_date,
            "platform_id": self.platform_id,
            "impact_scope": self.impact_scope,
            "description": self.description,
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_product_from_snapshot(snapshot: dict) -> ProductNode:
    """Factory function to create ProductNode from snapshot."""
    return ProductNode.from_snapshot(snapshot)


def create_ranking_from_snapshot(snapshot: dict) -> RankingRecord:
    """Factory function to create RankingRecord from snapshot."""
    return RankingRecord.from_snapshot(snapshot)


def get_platform(market: str) -> Optional[PlatformNode]:
    """Get platform node by market identifier."""
    try:
        market_enum = Market(market)
        return PLATFORMS.get(market_enum)
    except ValueError:
        logger.warning(f"Unknown market: {market}")
        return None
