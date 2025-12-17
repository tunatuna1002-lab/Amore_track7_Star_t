"""
Entity Extractor for Graph-RAG queries.

Extracts entities (products, brands, categories, dates) from natural language
queries and classifies the query intent.

Supports:
- Product name matching (fuzzy)
- Brand recognition
- Category detection
- Date/time expression parsing
- Query intent classification
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    """Classification of query intent."""
    
    # Rank queries
    CURRENT_RANK = "current_rank"          # "현재 순위는?"
    RANK_HISTORY = "rank_history"          # "최근 30일 순위 변동"
    RANK_CHANGE = "rank_change"            # "순위가 얼마나 변했나요?"
    
    # Comparison queries
    COMPARISON = "comparison"              # "경쟁사 대비 순위"
    TOP_N = "top_n"                         # "Top 10 제품"
    
    # Analysis queries
    TREND = "trend"                         # "상승/하락 추세"
    INSIGHT = "insight"                     # "인사이트/분석"
    
    # Product queries
    PRODUCT_INFO = "product_info"          # "제품 정보"
    PRODUCT_SEARCH = "product_search"      # "제품 검색"
    
    # General
    GENERAL = "general"                     # 기타


@dataclass
class ExtractedEntities:
    """
    Entities extracted from a user query.
    
    Attributes:
        products: List of product names/keywords
        brands: List of brand names
        categories: List of category names
        platforms: List of platform identifiers
        time_range: Optional (start_date, end_date) tuple
        top_n: Optional N for Top N queries
        intent: Classified query intent
        raw_query: Original query string
    """
    products: List[str] = field(default_factory=list)
    brands: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    time_range: Optional[Tuple[str, str]] = None
    top_n: Optional[int] = None
    intent: QueryIntent = QueryIntent.GENERAL
    raw_query: str = ""
    confidence: float = 0.0
    
    def has_entities(self) -> bool:
        """Check if any entities were extracted."""
        return bool(self.products or self.brands or self.categories)
    
    def to_dict(self) -> dict:
        return {
            "products": self.products,
            "brands": self.brands,
            "categories": self.categories,
            "platforms": self.platforms,
            "time_range": self.time_range,
            "top_n": self.top_n,
            "intent": self.intent.value,
            "raw_query": self.raw_query,
            "confidence": self.confidence,
        }


class EntityExtractor:
    """
    Extracts entities from natural language queries.
    
    Uses keyword matching, pattern recognition, and fuzzy matching
    to identify products, brands, categories, and time expressions.
    """
    
    # Known brands (case-insensitive)
    KNOWN_BRANDS = {
        "laneige": ["라네즈", "laneige"],
        "sulwhasoo": ["설화수", "sulwhasoo"],
        "innisfree": ["이니스프리", "innisfree"],
        "etude": ["에뛰드", "etude"],
        "amorepacific": ["아모레퍼시픽", "amorepacific"],
        "hera": ["헤라", "hera"],
        "iope": ["아이오페", "iope"],
        "mamonde": ["마몽드", "mamonde"],
        "primera": ["프리메라", "primera"],
        # Competitors
        "neutrogena": ["뉴트로지나", "neutrogena"],
        "cerave": ["세라비", "cerave"],
        "vaseline": ["바세린", "vaseline"],
        "burt's bees": ["버츠비", "burt's bees", "burts bees"],
        "aquaphor": ["아쿠아포", "aquaphor"],
        "eos": ["이오에스", "eos"],
        "carmex": ["카멕스", "carmex"],
    }
    
    # Known categories
    KNOWN_CATEGORIES = {
        "lip_care": ["립케어", "립 케어", "lip care", "lip", "립"],
        "lip_sleeping_mask": ["립 슬리핑 마스크", "lip sleeping mask", "립슬리핑마스크"],
        "lip_balm": ["립밤", "lip balm", "립 밤"],
        "skin_care": ["스킨케어", "스킨 케어", "skin care", "skincare"],
        "face_mask": ["페이스 마스크", "face mask", "마스크팩"],
        "moisturizer": ["모이스처라이저", "보습제", "moisturizer"],
    }
    
    # Known platforms
    KNOWN_PLATFORMS = {
        "amazon_us": ["아마존", "amazon", "amazon us", "아마존 미국"],
        "cosme_jp": ["코스메", "@cosme", "cosme", "앳코스메", "일본"],
    }
    
    # Intent keywords
    INTENT_PATTERNS = {
        QueryIntent.CURRENT_RANK: [
            r"현재\s*순위", r"지금\s*순위", r"오늘\s*순위",
            r"current\s*rank", r"순위가?\s*(어떻|얼마|몇)",
            r"몇\s*위", r"랭킹",
        ],
        QueryIntent.RANK_HISTORY: [
            r"순위\s*변동", r"순위\s*추이", r"순위\s*히스토리",
            r"지난\s*\d+일", r"최근\s*\d+일", r"변화",
            r"rank\s*history", r"rank\s*trend",
        ],
        QueryIntent.RANK_CHANGE: [
            r"얼마나\s*변", r"변했", r"올랐", r"내렸",
            r"상승", r"하락", r"변동폭",
        ],
        QueryIntent.COMPARISON: [
            r"비교", r"대비", r"vs", r"경쟁",
            r"compare", r"versus",
        ],
        QueryIntent.TOP_N: [
            r"top\s*\d+", r"탑\s*\d+", r"상위\s*\d+",
            r"\d+위\s*까지", r"베스트\s*\d+",
        ],
        QueryIntent.TREND: [
            r"트렌드", r"추세", r"동향", r"전망",
            r"trend", r"forecast",
        ],
        QueryIntent.INSIGHT: [
            r"인사이트", r"분석", r"요약", r"리포트",
            r"insight", r"analysis", r"summary",
        ],
        QueryIntent.PRODUCT_INFO: [
            r"제품\s*정보", r"상품\s*정보", r"정보",
            r"product\s*info",
        ],
        QueryIntent.PRODUCT_SEARCH: [
            r"검색", r"찾아", r"어디", r"어떤\s*제품",
            r"search", r"find",
        ],
    }
    
    # Time expression patterns
    TIME_PATTERNS = {
        "today": (0, 0),
        "오늘": (0, 0),
        "yesterday": (-1, -1),
        "어제": (-1, -1),
        "this week": (-7, 0),
        "이번 주": (-7, 0),
        "이번주": (-7, 0),
        "last week": (-14, -7),
        "지난 주": (-14, -7),
        "지난주": (-14, -7),
        "this month": (-30, 0),
        "이번 달": (-30, 0),
        "이번달": (-30, 0),
        "last month": (-60, -30),
        "지난 달": (-60, -30),
        "지난달": (-60, -30),
    }
    
    def __init__(
        self,
        product_index: Optional[List[str]] = None,
        custom_brands: Optional[Dict[str, List[str]]] = None,
        custom_categories: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize the entity extractor.
        
        Args:
            product_index: List of known product names for matching
            custom_brands: Additional brand aliases
            custom_categories: Additional category aliases
        """
        self.product_index = product_index or []
        
        # Merge custom dictionaries
        self.brands = {**self.KNOWN_BRANDS}
        if custom_brands:
            self.brands.update(custom_brands)
        
        self.categories = {**self.KNOWN_CATEGORIES}
        if custom_categories:
            self.categories.update(custom_categories)
        
        logger.debug(
            f"EntityExtractor initialized: {len(self.brands)} brands, "
            f"{len(self.categories)} categories, {len(self.product_index)} products"
        )
    
    def extract(self, query: str) -> ExtractedEntities:
        """
        Extract entities from a natural language query.
        
        Args:
            query: User query string
            
        Returns:
            ExtractedEntities with all extracted information
        """
        if not query:
            return ExtractedEntities(raw_query=query)
        
        # Normalize query
        query_normalized = self._normalize(query)
        query_lower = query_normalized.lower()
        
        # Extract entities
        brands = self._extract_brands(query_lower)
        categories = self._extract_categories(query_lower)
        platforms = self._extract_platforms(query_lower)
        products = self._extract_products(query_normalized, brands)
        time_range = self._extract_time_range(query_lower)
        top_n = self._extract_top_n(query_lower)
        intent = self._classify_intent(query_lower)
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            brands, categories, products, intent
        )
        
        result = ExtractedEntities(
            products=products,
            brands=brands,
            categories=categories,
            platforms=platforms,
            time_range=time_range,
            top_n=top_n,
            intent=intent,
            raw_query=query,
            confidence=confidence,
        )
        
        logger.debug(f"Extracted: {result.to_dict()}")
        return result
    
    def _normalize(self, text: str) -> str:
        """Normalize text for processing."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    def _extract_brands(self, query_lower: str) -> List[str]:
        """Extract brand names from query."""
        found_brands = []
        
        for brand_key, aliases in self.brands.items():
            for alias in aliases:
                if alias.lower() in query_lower:
                    found_brands.append(brand_key)
                    break
        
        return list(set(found_brands))
    
    def _extract_categories(self, query_lower: str) -> List[str]:
        """Extract category names from query."""
        found_categories = []
        
        for category_key, aliases in self.categories.items():
            for alias in aliases:
                if alias.lower() in query_lower:
                    found_categories.append(category_key)
                    break
        
        return list(set(found_categories))
    
    def _extract_platforms(self, query_lower: str) -> List[str]:
        """Extract platform identifiers from query."""
        found_platforms = []
        
        for platform_key, aliases in self.KNOWN_PLATFORMS.items():
            for alias in aliases:
                if alias.lower() in query_lower:
                    found_platforms.append(platform_key)
                    break
        
        return list(set(found_platforms))
    
    def _extract_products(self, query: str, brands: List[str]) -> List[str]:
        """Extract product names from query."""
        found_products = []
        query_lower = query.lower()
        
        # Check product index for matches
        for product_name in self.product_index:
            product_lower = product_name.lower()
            # Check for partial match
            if product_lower in query_lower or query_lower in product_lower:
                found_products.append(product_name)
        
        # Extract product-like patterns
        # Pattern: Brand + Product keywords
        product_patterns = [
            r"립\s*슬리핑\s*마스크",
            r"lip\s*sleeping\s*mask",
            r"워터\s*슬리핑\s*마스크",
            r"water\s*sleeping\s*mask",
            r"워터\s*뱅크",
            r"water\s*bank",
            r"네오\s*쿠션",
            r"neo\s*cushion",
        ]
        
        for pattern in product_patterns:
            if re.search(pattern, query_lower):
                # Create product name with brand if available
                match = re.search(pattern, query_lower).group()
                if brands:
                    found_products.append(f"{brands[0]} {match}".strip())
                else:
                    found_products.append(match.strip())
        
        return list(set(found_products))
    
    def _extract_time_range(self, query_lower: str) -> Optional[Tuple[str, str]]:
        """Extract time range from query."""
        today = datetime.now()
        
        # Check predefined time expressions
        for pattern, (start_delta, end_delta) in self.TIME_PATTERNS.items():
            if pattern in query_lower:
                start_date = today + timedelta(days=start_delta)
                end_date = today + timedelta(days=end_delta)
                return (
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                )
        
        # Check for "최근 N일" / "지난 N일" patterns
        recent_match = re.search(r"(?:최근|지난)\s*(\d+)\s*일", query_lower)
        if recent_match:
            days = int(recent_match.group(1))
            start_date = today - timedelta(days=days)
            return (
                start_date.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d"),
            )
        
        # Check for "last N days" pattern
        last_days_match = re.search(r"last\s*(\d+)\s*days?", query_lower)
        if last_days_match:
            days = int(last_days_match.group(1))
            start_date = today - timedelta(days=days)
            return (
                start_date.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d"),
            )
        
        return None
    
    def _extract_top_n(self, query_lower: str) -> Optional[int]:
        """Extract Top N value from query."""
        # Match "top 10", "탑 10", "상위 10" patterns
        patterns = [
            r"top\s*(\d+)",
            r"탑\s*(\d+)",
            r"상위\s*(\d+)",
            r"(\d+)위\s*까지",
            r"베스트\s*(\d+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                return int(match.group(1))
        
        return None
    
    def _classify_intent(self, query_lower: str) -> QueryIntent:
        """Classify query intent."""
        intent_scores: Dict[QueryIntent, int] = {}
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    score += 1
            if score > 0:
                intent_scores[intent] = score
        
        if intent_scores:
            # Return intent with highest score
            return max(intent_scores, key=intent_scores.get)
        
        return QueryIntent.GENERAL
    
    def _calculate_confidence(
        self,
        brands: List[str],
        categories: List[str],
        products: List[str],
        intent: QueryIntent,
    ) -> float:
        """Calculate confidence score for extraction."""
        score = 0.0
        
        # Entity presence adds confidence
        if brands:
            score += 0.3
        if categories:
            score += 0.2
        if products:
            score += 0.3
        
        # Specific intent adds confidence
        if intent != QueryIntent.GENERAL:
            score += 0.2
        
        return min(score, 1.0)
    
    def update_product_index(self, products: List[str]):
        """Update the product index for matching."""
        self.product_index = list(set(self.product_index + products))
        logger.debug(f"Product index updated: {len(self.product_index)} products")
    
    def add_brand_alias(self, brand_key: str, aliases: List[str]):
        """Add brand aliases."""
        if brand_key in self.brands:
            self.brands[brand_key].extend(aliases)
        else:
            self.brands[brand_key] = aliases
    
    def add_category_alias(self, category_key: str, aliases: List[str]):
        """Add category aliases."""
        if category_key in self.categories:
            self.categories[category_key].extend(aliases)
        else:
            self.categories[category_key] = aliases
