"""
Graph Retriever for Graph-RAG queries.

Traverses the RankingGraph to retrieve structured data based on
extracted entities and query intent.

Supports traversal patterns:
- Current rank: Product → rankedAs → Ranking[latest]
- Rank history: Product → rankedAs → Ranking[] (time series)
- Top N: Category → belongsTo ← Product[] → rankedAs → Ranking[date]
- Competitors: Product → belongsTo → Category → belongsTo ← Product[]
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from src.ontology import RankingGraph, ProductNode, RankingRecord
from .entity_extractor import ExtractedEntities, QueryIntent

logger = logging.getLogger(__name__)


@dataclass
class RankResult:
    """A single ranking result."""
    product_name: str
    product_url: str
    product_id: str
    brand: Optional[str]
    rank: int
    date: str
    market: str
    category_key: str
    
    def to_dict(self) -> dict:
        return {
            "product_name": self.product_name,
            "product_url": self.product_url,
            "product_id": self.product_id,
            "brand": self.brand,
            "rank": self.rank,
            "date": self.date,
            "market": self.market,
            "category_key": self.category_key,
        }


@dataclass
class RankHistory:
    """Ranking history for a product."""
    product_name: str
    product_url: str
    product_id: str
    brand: Optional[str]
    market: str
    category_key: str
    history: List[Tuple[str, int]]  # List of (date, rank) tuples
    
    @property
    def current_rank(self) -> Optional[int]:
        """Get most recent rank."""
        if self.history:
            return self.history[-1][1]
        return None
    
    @property
    def rank_change(self) -> Optional[int]:
        """Calculate rank change (positive = improvement)."""
        if len(self.history) >= 2:
            # Rank decrease (e.g., 5 to 3) is improvement
            return self.history[-2][1] - self.history[-1][1]
        return None
    
    @property
    def trend(self) -> str:
        """Determine trend direction."""
        if len(self.history) < 2:
            return "stable"
        
        change = self.rank_change
        if change is None:
            return "stable"
        elif change > 3:
            return "rising"
        elif change < -3:
            return "falling"
        else:
            return "stable"
    
    def to_dict(self) -> dict:
        return {
            "product_name": self.product_name,
            "product_url": self.product_url,
            "product_id": self.product_id,
            "brand": self.brand,
            "market": self.market,
            "category_key": self.category_key,
            "history": [{"date": d, "rank": r} for d, r in self.history],
            "current_rank": self.current_rank,
            "rank_change": self.rank_change,
            "trend": self.trend,
        }


@dataclass
class GraphContext:
    """
    Context retrieved from the knowledge graph.
    
    Attributes:
        query_type: Type of query performed
        results: List of result dictionaries
        traversal_path: Description of graph traversal
        metadata: Additional context metadata
    """
    query_type: str
    results: List[dict] = field(default_factory=list)
    traversal_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_empty(self) -> bool:
        return len(self.results) == 0
    
    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type,
            "results": self.results,
            "traversal_path": self.traversal_path,
            "metadata": self.metadata,
        }


class GraphRetriever:
    """
    Retrieves data from the RankingGraph based on query intent.
    """
    
    def __init__(self, graph: RankingGraph):
        """
        Initialize the graph retriever.
        
        Args:
            graph: RankingGraph instance to query
        """
        self.graph = graph
        logger.debug("GraphRetriever initialized")
    
    def retrieve(self, entities: ExtractedEntities) -> GraphContext:
        """
        Retrieve graph context based on extracted entities.
        
        Args:
            entities: Extracted entities from query
            
        Returns:
            GraphContext with query results
        """
        intent = entities.intent
        
        # Route to appropriate handler
        if intent == QueryIntent.CURRENT_RANK:
            return self._get_current_rank(entities)
        elif intent == QueryIntent.RANK_HISTORY:
            return self._get_rank_history(entities)
        elif intent == QueryIntent.RANK_CHANGE:
            return self._get_rank_change(entities)
        elif intent == QueryIntent.TOP_N:
            return self._get_top_n(entities)
        elif intent == QueryIntent.COMPARISON:
            return self._get_comparison(entities)
        elif intent == QueryIntent.TREND:
            return self._get_trend(entities)
        elif intent == QueryIntent.PRODUCT_INFO:
            return self._get_product_info(entities)
        elif intent == QueryIntent.PRODUCT_SEARCH:
            return self._search_products(entities)
        else:
            return self._get_general_context(entities)
    
    def _get_current_rank(self, entities: ExtractedEntities) -> GraphContext:
        """
        Get current ranking for products.
        
        Pattern: Product → rankedAs → Ranking[latest]
        """
        results = []
        
        # Find products by name or brand
        products = self._find_products(entities)
        
        for product in products:
            rankings = self.graph.get_product_rankings(product.product_id)
            if rankings:
                latest = rankings[-1]
                results.append(RankResult(
                    product_name=product.product_name_raw,
                    product_url=product.product_url,
                    product_id=product.product_id,
                    brand=product.brand,
                    rank=latest.rank,
                    date=latest.recorded_at,
                    market=latest.platform_id,
                    category_key=latest.category_id.split("_", 1)[-1] if "_" in latest.category_id else latest.category_id,
                ).to_dict())
        
        return GraphContext(
            query_type="current_rank",
            results=results,
            traversal_path="Product → rankedAs → Ranking[latest]",
            metadata={
                "products_found": len(products),
                "results_count": len(results),
            }
        )
    
    def _get_rank_history(self, entities: ExtractedEntities) -> GraphContext:
        """
        Get ranking history for products.
        
        Pattern: Product → rankedAs → Ranking[] (sorted by date)
        """
        results = []
        products = self._find_products(entities)
        
        # Determine date range
        start_date, end_date = self._get_date_range(entities)
        
        for product in products:
            rankings = self.graph.get_product_rankings(
                product.product_id,
                start_date=start_date,
                end_date=end_date,
            )
            
            if rankings:
                # Group by category
                by_category: Dict[str, List[RankingRecord]] = defaultdict(list)
                for r in rankings:
                    by_category[r.category_id].append(r)
                
                for category_id, cat_rankings in by_category.items():
                    history = [(r.recorded_at, r.rank) for r in cat_rankings]
                    history.sort(key=lambda x: x[0])
                    
                    results.append(RankHistory(
                        product_name=product.product_name_raw,
                        product_url=product.product_url,
                        product_id=product.product_id,
                        brand=product.brand,
                        market=cat_rankings[0].platform_id,
                        category_key=category_id.split("_", 1)[-1] if "_" in category_id else category_id,
                        history=history,
                    ).to_dict())
        
        return GraphContext(
            query_type="rank_history",
            results=results,
            traversal_path="Product → rankedAs → Ranking[] (time series)",
            metadata={
                "date_range": {"start": start_date, "end": end_date},
                "products_found": len(products),
            }
        )
    
    def _get_rank_change(self, entities: ExtractedEntities) -> GraphContext:
        """Get rank change summary."""
        # Reuse rank history and extract change
        history_context = self._get_rank_history(entities)
        
        # Add change information
        for result in history_context.results:
            if "history" in result and len(result["history"]) >= 2:
                first_rank = result["history"][0]["rank"]
                last_rank = result["history"][-1]["rank"]
                result["total_change"] = first_rank - last_rank  # Positive = improvement
        
        history_context.query_type = "rank_change"
        return history_context
    
    def _get_top_n(self, entities: ExtractedEntities) -> GraphContext:
        """
        Get Top N products in a category.
        
        Pattern: Category → belongsTo ← Product[] → rankedAs → Ranking[date]
        """
        results = []
        top_n = entities.top_n or 10
        
        # Determine categories to query
        category_ids = self._get_category_ids(entities)
        
        # Get latest date with data
        dates = self.graph.graph.nodes  # Get available dates
        
        for category_id in category_ids:
            # Find rankings for this category
            rankings_in_category = [
                r for r in self.graph._rankings.values()
                if r.category_id == category_id
            ]
            
            if not rankings_in_category:
                continue
            
            # Get latest date
            latest_date = max(r.recorded_at for r in rankings_in_category)
            
            # Get rankings on latest date
            latest_rankings = [
                r for r in rankings_in_category
                if r.recorded_at == latest_date
            ]
            
            # Sort by rank and take top N
            latest_rankings.sort(key=lambda r: r.rank)
            top_rankings = latest_rankings[:top_n]
            
            for ranking in top_rankings:
                product = self.graph._products.get(ranking.product_id)
                if product:
                    results.append(RankResult(
                        product_name=product.product_name_raw,
                        product_url=product.product_url,
                        product_id=product.product_id,
                        brand=product.brand,
                        rank=ranking.rank,
                        date=ranking.recorded_at,
                        market=ranking.platform_id,
                        category_key=category_id.split("_", 1)[-1] if "_" in category_id else category_id,
                    ).to_dict())
        
        return GraphContext(
            query_type="top_n",
            results=results,
            traversal_path=f"Category → belongsTo ← Product[Top {top_n}]",
            metadata={
                "top_n": top_n,
                "categories": category_ids,
                "results_count": len(results),
            }
        )
    
    def _get_comparison(self, entities: ExtractedEntities) -> GraphContext:
        """
        Compare products (competitors).
        
        Pattern: Product → belongsTo → Category → belongsTo ← Product[]
        """
        results = []
        products = self._find_products(entities)
        
        if not products:
            return GraphContext(
                query_type="comparison",
                results=[],
                traversal_path="No products found for comparison",
            )
        
        # For each product, find competitors
        for product in products:
            rankings = self.graph.get_product_rankings(product.product_id)
            if not rankings:
                continue
            
            latest = rankings[-1]
            competitors = self.graph.get_competitors(
                product.product_id,
                latest.category_id,
            )
            
            comparison = {
                "main_product": {
                    "name": product.product_name_raw,
                    "brand": product.brand,
                    "current_rank": latest.rank,
                },
                "competitors": [],
            }
            
            for comp in competitors[:10]:  # Top 10 competitors
                comp_rankings = self.graph.get_product_rankings(comp.product_id)
                if comp_rankings:
                    comp_latest = comp_rankings[-1]
                    comparison["competitors"].append({
                        "name": comp.product_name_raw,
                        "brand": comp.brand,
                        "rank": comp_latest.rank,
                    })
            
            results.append(comparison)
        
        return GraphContext(
            query_type="comparison",
            results=results,
            traversal_path="Product → belongsTo → Category → belongsTo ← Product[]",
            metadata={"products_compared": len(products)}
        )
    
    def _get_trend(self, entities: ExtractedEntities) -> GraphContext:
        """Get trend analysis for products."""
        # Get history and analyze trend
        history_context = self._get_rank_history(entities)
        
        # Add trend analysis
        for result in history_context.results:
            if "history" in result and len(result["history"]) >= 3:
                ranks = [h["rank"] for h in result["history"]]
                
                # Calculate trend metrics
                result["trend_analysis"] = {
                    "avg_rank": sum(ranks) / len(ranks),
                    "best_rank": min(ranks),
                    "worst_rank": max(ranks),
                    "volatility": max(ranks) - min(ranks),
                    "direction": result.get("trend", "stable"),
                }
        
        history_context.query_type = "trend"
        return history_context
    
    def _get_product_info(self, entities: ExtractedEntities) -> GraphContext:
        """Get detailed product information."""
        results = []
        products = self._find_products(entities)
        
        for product in products:
            rankings = self.graph.get_product_rankings(product.product_id)
            
            info = {
                "product": product.to_dict(),
                "rankings_count": len(rankings),
                "first_seen": product.first_seen,
                "last_seen": product.last_seen,
            }
            
            if rankings:
                info["current_rank"] = rankings[-1].rank
                info["current_market"] = rankings[-1].platform_id
                info["current_category"] = rankings[-1].category_id
            
            results.append(info)
        
        return GraphContext(
            query_type="product_info",
            results=results,
            traversal_path="Product → attributes + rankedAs → Ranking[latest]",
        )
    
    def _search_products(self, entities: ExtractedEntities) -> GraphContext:
        """Search for products matching criteria."""
        results = []
        
        # Search by brand
        if entities.brands:
            for brand in entities.brands:
                products = self.graph.find_products_by_brand(brand)
                for p in products:
                    results.append(p.to_dict())
        
        # Search by name keywords
        if entities.products:
            for keyword in entities.products:
                products = self.graph.find_products_by_name(keyword)
                for p in products:
                    if p.to_dict() not in results:
                        results.append(p.to_dict())
        
        return GraphContext(
            query_type="product_search",
            results=results,
            traversal_path="Product[name/brand match]",
            metadata={
                "search_brands": entities.brands,
                "search_keywords": entities.products,
                "results_count": len(results),
            }
        )
    
    def _get_general_context(self, entities: ExtractedEntities) -> GraphContext:
        """Get general context when intent is unclear."""
        results = []
        
        # Try to find any matching products
        products = self._find_products(entities)
        
        if products:
            # Get current ranks for found products
            return self._get_current_rank(entities)
        
        # If no products found but brands specified, search by brand
        if entities.brands:
            return self._search_products(entities)
        
        # Return graph stats as general info
        stats = self.graph.get_stats()
        results.append({
            "type": "graph_stats",
            "stats": stats,
        })
        
        return GraphContext(
            query_type="general",
            results=results,
            traversal_path="Graph statistics",
        )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _find_products(self, entities: ExtractedEntities) -> List[ProductNode]:
        """Find products matching entities."""
        found_products = []
        
        # Search by brand
        for brand in entities.brands:
            products = self.graph.find_products_by_brand(brand)
            found_products.extend(products)
        
        # Search by product name keywords
        for keyword in entities.products:
            products = self.graph.find_products_by_name(keyword)
            found_products.extend(products)
        
        # Deduplicate by product_id
        seen = set()
        unique_products = []
        for p in found_products:
            if p.product_id not in seen:
                seen.add(p.product_id)
                unique_products.append(p)
        
        return unique_products
    
    def _get_date_range(self, entities: ExtractedEntities) -> Tuple[Optional[str], Optional[str]]:
        """Get date range from entities or default."""
        if entities.time_range:
            return entities.time_range
        
        # Default to last 30 days
        today = datetime.now()
        start = today - timedelta(days=30)
        return (start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    
    def _get_category_ids(self, entities: ExtractedEntities) -> List[str]:
        """Get category IDs from entities."""
        category_ids = []
        
        # Build category IDs from platforms and categories
        platforms = entities.platforms or ["amazon_us", "cosme_jp"]
        categories = entities.categories or list(self.graph._categories.keys())
        
        for category_id in self.graph._categories.keys():
            # Filter by platform if specified
            if entities.platforms:
                if not any(p in category_id for p in entities.platforms):
                    continue
            
            # Filter by category if specified
            if entities.categories:
                if not any(c in category_id for c in entities.categories):
                    continue
            
            category_ids.append(category_id)
        
        return category_ids or list(self.graph._categories.keys())
