"""
Graph builder for the ranking ontology using NetworkX.

Provides functionality to:
- Build knowledge graph from ranking snapshots
- Query graph for insights
- Export/import graph data
- Support Graph-RAG traversal patterns

Reference: docs/ontology_schema.yaml
"""

import json
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Iterator

try:
    import networkx as nx
except ImportError:
    nx = None
    logging.warning("NetworkX not installed. Graph features will be limited.")

from .entities import (
    ProductNode,
    CategoryNode,
    PlatformNode,
    RankingRecord,
    BrandNode,
    Market,
    PLATFORMS,
    get_platform,
)
from .relations import (
    Relation,
    RelationType,
    create_belongs_to_relation,
    create_listed_on_relation,
    create_ranked_as_relation,
    create_competes_with_relation,
    create_produced_by_relation,
)

logger = logging.getLogger(__name__)


class RankingGraph:
    """
    Knowledge graph for ranking data using NetworkX MultiDiGraph.
    
    Uses MultiDiGraph to support:
    - Multiple edges between same nodes (e.g., multiple rankings)
    - Directed relationships
    - Node and edge attributes
    
    Node ID format: {type}:{id}
    - Product:abc123
    - Category:amazon_us_lip_care
    - Platform:amazon_us
    - Ranking:xyz789
    """
    
    def __init__(self):
        """Initialize empty graph."""
        if nx is None:
            raise ImportError("NetworkX is required for graph features. Install with: pip install networkx")
        
        self.graph = nx.MultiDiGraph()
        
        # Index structures for fast lookup
        self._products: Dict[str, ProductNode] = {}
        self._categories: Dict[str, CategoryNode] = {}
        self._rankings: Dict[str, RankingRecord] = {}
        
        # Initialize platforms
        self._init_platforms()
        
        logger.debug("RankingGraph initialized")
    
    def _init_platforms(self):
        """Add platform nodes to graph."""
        for market, platform in PLATFORMS.items():
            node_id = f"Platform:{platform.platform_id}"
            self.graph.add_node(node_id, **platform.to_dict())
    
    def _node_id(self, node_type: str, entity_id: str) -> str:
        """Generate consistent node ID."""
        return f"{node_type}:{entity_id}"
    
    # =========================================================================
    # Node Operations
    # =========================================================================
    
    def add_product(self, product: ProductNode) -> str:
        """
        Add or update a product node.
        
        Args:
            product: ProductNode instance
            
        Returns:
            Node ID
        """
        node_id = self._node_id("Product", product.product_id)
        
        if product.product_id in self._products:
            # Update existing product
            existing = self._products[product.product_id]
            existing.update_seen_dates(product.last_seen or "")
            self.graph.nodes[node_id].update(existing.to_dict())
        else:
            # Add new product
            self._products[product.product_id] = product
            self.graph.add_node(node_id, **product.to_dict())
        
        return node_id
    
    def add_category(self, category: CategoryNode) -> str:
        """
        Add or update a category node.
        
        Args:
            category: CategoryNode instance
            
        Returns:
            Node ID
        """
        node_id = self._node_id("Category", category.category_id)
        
        if category.category_id not in self._categories:
            self._categories[category.category_id] = category
            self.graph.add_node(node_id, **category.to_dict())
        
        return node_id
    
    def add_ranking(self, ranking: RankingRecord) -> str:
        """
        Add a ranking record node.
        
        Args:
            ranking: RankingRecord instance
            
        Returns:
            Node ID
        """
        node_id = self._node_id("Ranking", ranking.ranking_id)
        
        if ranking.ranking_id not in self._rankings:
            self._rankings[ranking.ranking_id] = ranking
            self.graph.add_node(node_id, **ranking.to_dict())
        
        return node_id
    
    # =========================================================================
    # Relation Operations
    # =========================================================================
    
    def add_relation(self, relation: Relation):
        """
        Add a relation (edge) to the graph.
        
        Args:
            relation: Relation instance
        """
        from_id, to_id, edge_data = relation.to_edge_tuple()
        self.graph.add_edge(from_id, to_id, **edge_data)
    
    def add_belongs_to(self, product_id: str, category_id: str, date: str):
        """Add belongsTo relation between product and category."""
        relation = create_belongs_to_relation(
            product_id=self._node_id("Product", product_id),
            category_id=self._node_id("Category", category_id),
            first_ranked_date=date,
            last_ranked_date=date,
        )
        self.add_relation(relation)
    
    def add_listed_on(self, product_id: str, platform_id: str, url: str, date: str):
        """Add listedOn relation between product and platform."""
        relation = create_listed_on_relation(
            product_id=self._node_id("Product", product_id),
            platform_id=self._node_id("Platform", platform_id),
            listing_url=url,
            first_seen=date,
        )
        self.add_relation(relation)
    
    def add_ranked_as(self, product_id: str, ranking_id: str):
        """Add rankedAs relation between product and ranking."""
        relation = create_ranked_as_relation(
            product_id=self._node_id("Product", product_id),
            ranking_id=self._node_id("Ranking", ranking_id),
        )
        self.add_relation(relation)
    
    # =========================================================================
    # Build from Snapshots
    # =========================================================================
    
    def build_from_snapshots(self, snapshots: List[dict]) -> "RankingGraph":
        """
        Build graph from ranking snapshot dictionaries.
        
        Args:
            snapshots: List of ranking snapshot dicts (from ExcelStorage)
            
        Returns:
            Self for chaining
        """
        logger.info(f"Building graph from {len(snapshots)} snapshots")
        
        # Track unique categories
        seen_categories: Set[str] = set()
        
        for snapshot in snapshots:
            # Create and add product
            product = ProductNode.from_snapshot(snapshot)
            self.add_product(product)
            
            # Create and add category if new
            market = snapshot.get("market", "")
            category_key = snapshot.get("category_key", "")
            category_id = CategoryNode.generate_id(market, category_key)
            
            if category_id not in seen_categories:
                category = CategoryNode(
                    category_id=category_id,
                    category_key=category_key,
                    category_name=category_key,  # Could be enriched from config
                    category_url=snapshot.get("category_url", ""),
                    platform_id=market,
                )
                self.add_category(category)
                seen_categories.add(category_id)
            
            # Create and add ranking record
            ranking = RankingRecord.from_snapshot(snapshot)
            self.add_ranking(ranking)
            
            # Add relations
            date_kst = snapshot.get("date_kst", "")
            self.add_belongs_to(product.product_id, category_id, date_kst)
            self.add_listed_on(product.product_id, market, product.product_url, date_kst)
            self.add_ranked_as(product.product_id, ranking.ranking_id)
        
        logger.info(
            f"Graph built: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )
        
        return self
    
    # =========================================================================
    # Query Operations (Graph Traversal)
    # =========================================================================
    
    def get_product(self, product_id: str) -> Optional[ProductNode]:
        """Get product by ID."""
        return self._products.get(product_id)
    
    def get_product_by_url(self, product_url: str) -> Optional[ProductNode]:
        """Get product by URL."""
        product_id = ProductNode.generate_id(product_url)
        return self.get_product(product_id)
    
    def get_product_rankings(
        self,
        product_id: str,
        category_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[RankingRecord]:
        """
        Get ranking history for a product.
        
        Pattern: Product → rankedAs → Ranking[]
        
        Args:
            product_id: Product identifier
            category_id: Optional category filter
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            
        Returns:
            List of RankingRecord sorted by date
        """
        rankings = []
        product_node_id = self._node_id("Product", product_id)
        
        # Get all outgoing rankedAs edges
        for _, target_id, edge_data in self.graph.out_edges(product_node_id, data=True):
            if edge_data.get("relation_type") != RelationType.RANKED_AS.value:
                continue
            
            # Extract ranking ID from node ID
            ranking_id = target_id.split(":", 1)[1] if ":" in target_id else target_id
            ranking = self._rankings.get(ranking_id)
            
            if ranking:
                # Apply filters
                if category_id and ranking.category_id != category_id:
                    continue
                if start_date and ranking.recorded_at < start_date:
                    continue
                if end_date and ranking.recorded_at > end_date:
                    continue
                
                rankings.append(ranking)
        
        # Sort by date
        rankings.sort(key=lambda r: r.recorded_at)
        return rankings
    
    def get_current_rank(
        self,
        product_id: str,
        category_id: Optional[str] = None
    ) -> Optional[int]:
        """
        Get most recent rank for a product.
        
        Args:
            product_id: Product identifier
            category_id: Optional category filter
            
        Returns:
            Current rank or None
        """
        rankings = self.get_product_rankings(product_id, category_id)
        if rankings:
            return rankings[-1].rank
        return None
    
    def get_category_rankings(
        self,
        category_id: str,
        date: str,
        top_n: int = 100
    ) -> List[Tuple[ProductNode, int]]:
        """
        Get products ranked in a category on a specific date.
        
        Pattern: Category ← belongsTo ← Product → rankedAs → Ranking[date]
        
        Args:
            category_id: Category identifier
            date: Date string (YYYY-MM-DD)
            top_n: Maximum number of results
            
        Returns:
            List of (ProductNode, rank) tuples sorted by rank
        """
        results = []
        
        for ranking in self._rankings.values():
            if ranking.category_id == category_id and ranking.recorded_at == date:
                product = self._products.get(ranking.product_id)
                if product:
                    results.append((product, ranking.rank))
        
        # Sort by rank and limit
        results.sort(key=lambda x: x[1])
        return results[:top_n]
    
    def get_competitors(
        self,
        product_id: str,
        category_id: str,
        date: Optional[str] = None
    ) -> List[ProductNode]:
        """
        Get products that compete with a given product.
        
        Products are competitors if they appear in the same category.
        
        Args:
            product_id: Product identifier
            category_id: Category to check
            date: Optional date filter (most recent if not specified)
            
        Returns:
            List of competing ProductNodes
        """
        # Get all products in category
        if date:
            category_products = self.get_category_rankings(category_id, date)
        else:
            # Find most recent date for category
            dates = set()
            for ranking in self._rankings.values():
                if ranking.category_id == category_id:
                    dates.add(ranking.recorded_at)
            
            if not dates:
                return []
            
            latest_date = max(dates)
            category_products = self.get_category_rankings(category_id, latest_date)
        
        # Exclude self
        competitors = [
            product for product, rank in category_products
            if product.product_id != product_id
        ]
        
        return competitors
    
    def find_products_by_brand(self, brand_name: str) -> List[ProductNode]:
        """
        Find products by brand name (case-insensitive partial match).
        
        Args:
            brand_name: Brand name to search
            
        Returns:
            List of matching ProductNodes
        """
        brand_lower = brand_name.lower()
        return [
            product for product in self._products.values()
            if product.brand and brand_lower in product.brand.lower()
        ]
    
    def find_products_by_name(self, name_query: str) -> List[ProductNode]:
        """
        Find products by name (case-insensitive partial match).
        
        Args:
            name_query: Name to search
            
        Returns:
            List of matching ProductNodes
        """
        query_lower = name_query.lower()
        return [
            product for product in self._products.values()
            if query_lower in product.product_name_raw.lower()
        ]
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get graph statistics."""
        node_types = defaultdict(int)
        for node_id in self.graph.nodes():
            node_type = node_id.split(":")[0] if ":" in node_id else "Unknown"
            node_types[node_type] += 1
        
        edge_types = defaultdict(int)
        for _, _, data in self.graph.edges(data=True):
            edge_type = data.get("relation_type", "unknown")
            edge_types[edge_type] += 1
        
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": dict(node_types),
            "edge_types": dict(edge_types),
            "products": len(self._products),
            "categories": len(self._categories),
            "rankings": len(self._rankings),
        }
    
    # =========================================================================
    # Export/Import
    # =========================================================================
    
    def to_json(self) -> str:
        """Export graph to JSON string."""
        data = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "stats": self.get_stats(),
            }
        }
        
        for node_id in self.graph.nodes():
            node_data = dict(self.graph.nodes[node_id])
            node_data["_id"] = node_id
            data["nodes"].append(node_data)
        
        for from_id, to_id, edge_data in self.graph.edges(data=True):
            edge = {
                "from": from_id,
                "to": to_id,
                **edge_data
            }
            data["edges"].append(edge)
        
        return json.dumps(data, ensure_ascii=False, indent=2)
    
    def save_json(self, filepath: str):
        """Save graph to JSON file."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info(f"Graph saved to {filepath}")
    
    @classmethod
    def load_json(cls, filepath: str) -> "RankingGraph":
        """Load graph from JSON file."""
        path = Path(filepath)
        data = json.loads(path.read_text(encoding="utf-8"))
        
        graph = cls()
        
        # Restore nodes
        for node_data in data.get("nodes", []):
            node_id = node_data.pop("_id", None)
            if node_id:
                graph.graph.add_node(node_id, **node_data)
                
                # Restore index
                node_type = node_data.get("node_type", "")
                if node_type == "Product":
                    product = ProductNode(
                        product_id=node_data.get("product_id", ""),
                        product_name_raw=node_data.get("product_name_raw", ""),
                        product_url=node_data.get("product_url", ""),
                        brand=node_data.get("brand"),
                        first_seen=node_data.get("first_seen"),
                        last_seen=node_data.get("last_seen"),
                    )
                    graph._products[product.product_id] = product
                elif node_type == "Category":
                    category = CategoryNode(
                        category_id=node_data.get("category_id", ""),
                        category_key=node_data.get("category_key", ""),
                        category_name=node_data.get("category_name", ""),
                        category_url=node_data.get("category_url", ""),
                        platform_id=node_data.get("platform_id", ""),
                    )
                    graph._categories[category.category_id] = category
        
        # Restore edges
        for edge_data in data.get("edges", []):
            from_id = edge_data.pop("from", None)
            to_id = edge_data.pop("to", None)
            if from_id and to_id:
                graph.graph.add_edge(from_id, to_id, **edge_data)
        
        logger.info(f"Graph loaded from {filepath}: {graph.get_stats()}")
        return graph


class GraphBuilder:
    """
    Builder class for constructing RankingGraph from various sources.
    """
    
    def __init__(self):
        """Initialize builder."""
        self.graph = RankingGraph()
    
    def from_excel_storage(self, storage) -> RankingGraph:
        """
        Build graph from ExcelStorage instance.
        
        Args:
            storage: ExcelStorage instance
            
        Returns:
            Built RankingGraph
        """
        snapshots = storage.get_rank_history()
        return self.graph.build_from_snapshots(snapshots)
    
    def from_snapshot_list(self, snapshots: List[dict]) -> RankingGraph:
        """
        Build graph from list of snapshot dictionaries.
        
        Args:
            snapshots: List of ranking snapshot dicts
            
        Returns:
            Built RankingGraph
        """
        return self.graph.build_from_snapshots(snapshots)
    
    def get_graph(self) -> RankingGraph:
        """Get the built graph."""
        return self.graph
