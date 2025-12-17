"""
Vector Retriever using ChromaDB for semantic search.

Provides semantic search capabilities for:
- Product descriptions and metadata
- Historical insights and rule matches
- Related context for RAG augmentation

Complements graph retrieval with semantic similarity search.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Optional ChromaDB import
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. Vector search will be disabled.")


@dataclass
class VectorSearchResult:
    """A single vector search result."""
    document: str
    metadata: Dict[str, Any]
    distance: float
    doc_id: str
    
    @property
    def score(self) -> float:
        """Convert distance to similarity score (0-1)."""
        # ChromaDB uses L2 distance by default, convert to similarity
        return max(0, 1 - self.distance)
    
    def to_dict(self) -> dict:
        return {
            "document": self.document,
            "metadata": self.metadata,
            "distance": self.distance,
            "score": self.score,
            "doc_id": self.doc_id,
        }


class VectorRetriever:
    """
    ChromaDB-based vector retriever for semantic search.
    
    Collections:
    - products: Product names and descriptions
    - insights: Generated insights from rule engine
    - context: Additional context documents
    """
    
    COLLECTION_PRODUCTS = "products"
    COLLECTION_INSIGHTS = "insights"
    COLLECTION_CONTEXT = "context"
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "ranking_data",
    ):
        """
        Initialize the vector retriever.
        
        Args:
            persist_directory: Directory to persist ChromaDB data
            collection_name: Name of the main collection
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is required for vector search. "
                "Install with: pip install chromadb"
            )
        
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        # Initialize ChromaDB client
        if persist_directory:
            Path(persist_directory).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.client = chromadb.Client()
        
        # Initialize collections
        self._init_collections()
        
        logger.info(f"VectorRetriever initialized with collection: {collection_name}")
    
    def _init_collections(self):
        """Initialize or get collections."""
        # Main collection for all documents
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Specialized collections
        self.products_collection = self.client.get_or_create_collection(
            name=f"{self.collection_name}_products",
            metadata={"hnsw:space": "cosine"}
        )
        
        self.insights_collection = self.client.get_or_create_collection(
            name=f"{self.collection_name}_insights",
            metadata={"hnsw:space": "cosine"}
        )
    
    def _generate_doc_id(self, content: str, prefix: str = "doc") -> str:
        """Generate deterministic document ID."""
        hash_val = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"{prefix}_{hash_val}"
    
    # =========================================================================
    # Indexing Methods
    # =========================================================================
    
    def index_products(self, products: List[dict]) -> int:
        """
        Index product information for semantic search.
        
        Args:
            products: List of product dictionaries with:
                - product_name: Product name
                - brand: Brand name
                - product_url: URL
                - category: Category
                
        Returns:
            Number of products indexed
        """
        if not products:
            return 0
        
        documents = []
        metadatas = []
        ids = []
        
        for product in products:
            # Create searchable document
            doc_parts = [
                product.get("product_name", ""),
                product.get("brand", ""),
                product.get("category", ""),
            ]
            document = " | ".join(filter(None, doc_parts))
            
            if not document.strip():
                continue
            
            doc_id = self._generate_doc_id(
                product.get("product_url", document),
                prefix="prod"
            )
            
            # Skip if already exists
            if self._doc_exists(self.products_collection, doc_id):
                continue
            
            documents.append(document)
            metadatas.append({
                "type": "product",
                "product_name": product.get("product_name", ""),
                "brand": product.get("brand", ""),
                "product_url": product.get("product_url", ""),
                "category": product.get("category", ""),
                "market": product.get("market", ""),
            })
            ids.append(doc_id)
        
        if documents:
            self.products_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            logger.debug(f"Indexed {len(documents)} products")
        
        return len(documents)
    
    def index_insights(self, insights: List[dict]) -> int:
        """
        Index insight messages for semantic search.
        
        Args:
            insights: List of insight dictionaries with:
                - message: Insight message
                - tag: Insight tag (e.g., "stable_leader")
                - rule_id: Rule identifier
                - product_name: Related product
                
        Returns:
            Number of insights indexed
        """
        if not insights:
            return 0
        
        documents = []
        metadatas = []
        ids = []
        
        for insight in insights:
            message = insight.get("message", "")
            if not message:
                continue
            
            doc_id = self._generate_doc_id(
                f"{insight.get('rule_id', '')}_{insight.get('product_url', '')}_{message[:50]}",
                prefix="ins"
            )
            
            if self._doc_exists(self.insights_collection, doc_id):
                continue
            
            documents.append(message)
            metadatas.append({
                "type": "insight",
                "tag": insight.get("tag", ""),
                "rule_id": insight.get("rule_id", ""),
                "rule_name": insight.get("rule_name", ""),
                "product_name": insight.get("product_name", ""),
                "product_url": insight.get("product_url", ""),
                "market": insight.get("market", ""),
                "category": insight.get("category_key", ""),
                "matched_at": insight.get("matched_at", ""),
            })
            ids.append(doc_id)
        
        if documents:
            self.insights_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            logger.debug(f"Indexed {len(documents)} insights")
        
        return len(documents)
    
    def index_from_snapshots(self, snapshots: List[dict]) -> dict:
        """
        Index products from ranking snapshots.
        
        Args:
            snapshots: List of ranking snapshot dictionaries
            
        Returns:
            Statistics about indexed documents
        """
        # Extract unique products
        products_map = {}
        for snapshot in snapshots:
            url = snapshot.get("product_url", "")
            if url and url not in products_map:
                products_map[url] = {
                    "product_name": snapshot.get("product_name_raw", ""),
                    "brand": snapshot.get("brand_raw", ""),
                    "product_url": url,
                    "category": snapshot.get("category_key", ""),
                    "market": snapshot.get("market", ""),
                }
        
        products_indexed = self.index_products(list(products_map.values()))
        
        return {
            "products_indexed": products_indexed,
            "total_snapshots": len(snapshots),
            "unique_products": len(products_map),
        }
    
    def index_from_rule_matches(self, matches: List) -> int:
        """
        Index insights from KnowledgeEngine rule matches.
        
        Args:
            matches: List of RuleMatch objects
            
        Returns:
            Number of insights indexed
        """
        insights = []
        for match in matches:
            if hasattr(match, 'to_dict'):
                insights.append(match.to_dict())
            elif isinstance(match, dict):
                insights.append(match)
        
        return self.index_insights(insights)
    
    def _doc_exists(self, collection, doc_id: str) -> bool:
        """Check if document exists in collection."""
        try:
            result = collection.get(ids=[doc_id])
            return len(result.get("ids", [])) > 0
        except Exception:
            return False
    
    # =========================================================================
    # Search Methods
    # =========================================================================
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        collection_type: str = "all",
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """
        Search for similar documents.
        
        Args:
            query: Search query
            top_k: Number of results to return
            collection_type: "products", "insights", or "all"
            filters: Optional metadata filters
            
        Returns:
            List of VectorSearchResult
        """
        results = []
        
        if collection_type in ["products", "all"]:
            results.extend(
                self._search_collection(
                    self.products_collection, query, top_k, filters
                )
            )
        
        if collection_type in ["insights", "all"]:
            results.extend(
                self._search_collection(
                    self.insights_collection, query, top_k, filters
                )
            )
        
        # Sort by distance and limit
        results.sort(key=lambda r: r.distance)
        return results[:top_k]
    
    def _search_collection(
        self,
        collection,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """Search a specific collection."""
        try:
            # Build where clause from filters
            where = None
            if filters:
                where = {}
                for key, value in filters.items():
                    if isinstance(value, list):
                        where[key] = {"$in": value}
                    else:
                        where[key] = value
            
            results = collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where,
            )
            
            search_results = []
            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
                
                for doc, meta, dist, doc_id in zip(docs, metas, dists, ids):
                    search_results.append(VectorSearchResult(
                        document=doc,
                        metadata=meta,
                        distance=dist,
                        doc_id=doc_id,
                    ))
            
            return search_results
            
        except Exception as e:
            logger.exception("Vector search error")
            return []
    
    def search_products(
        self,
        query: str,
        top_k: int = 5,
        market: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """
        Search for similar products.
        
        Args:
            query: Product name or description to search
            top_k: Number of results
            market: Filter by market (amazon_us, cosme_jp)
            category: Filter by category
            
        Returns:
            List of matching products
        """
        filters = {}
        if market:
            filters["market"] = market
        if category:
            filters["category"] = category
        
        return self.search(
            query=query,
            top_k=top_k,
            collection_type="products",
            filters=filters if filters else None,
        )
    
    def search_insights(
        self,
        query: str,
        top_k: int = 5,
        tag: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """
        Search for similar insights.
        
        Args:
            query: Insight description to search
            top_k: Number of results
            tag: Filter by tag (e.g., "stable_leader")
            rule_id: Filter by rule ID
            
        Returns:
            List of matching insights
        """
        filters = {}
        if tag:
            filters["tag"] = tag
        if rule_id:
            filters["rule_id"] = rule_id
        
        return self.search(
            query=query,
            top_k=top_k,
            collection_type="insights",
            filters=filters if filters else None,
        )
    
    def find_similar_products(
        self,
        product_name: str,
        top_k: int = 5,
        exclude_self: bool = True,
    ) -> List[VectorSearchResult]:
        """
        Find products similar to a given product.
        
        Args:
            product_name: Product name to find similar products for
            top_k: Number of results
            exclude_self: Exclude the queried product from results
            
        Returns:
            List of similar products
        """
        # Get more results to allow for filtering
        results = self.search_products(product_name, top_k=top_k + 5)
        
        if exclude_self:
            # Filter out exact matches
            product_lower = product_name.lower()
            results = [
                r for r in results
                if product_lower not in r.metadata.get("product_name", "").lower()
            ]
        
        return results[:top_k]
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get statistics about indexed documents."""
        return {
            "products_count": self.products_collection.count(),
            "insights_count": self.insights_collection.count(),
            "total_documents": (
                self.products_collection.count() +
                self.insights_collection.count()
            ),
        }
    
    def clear_all(self):
        """Clear all indexed documents."""
        self.client.delete_collection(f"{self.collection_name}_products")
        self.client.delete_collection(f"{self.collection_name}_insights")
        self._init_collections()
        logger.info("All vector collections cleared")
    
    def persist(self):
        """Persist data to disk (if using persistent client)."""
        if self.persist_directory:
            # ChromaDB PersistentClient auto-persists
            logger.info(f"Data persisted to {self.persist_directory}")


# =============================================================================
# Convenience Functions
# =============================================================================

def create_vector_retriever(
    persist_directory: str = "./data/chromadb",
    collection_name: str = "ranking_data",
) -> Optional[VectorRetriever]:
    """
    Create a vector retriever with default settings.
    
    Returns None if ChromaDB is not available.
    """
    if not CHROMADB_AVAILABLE:
        logger.warning("ChromaDB not available, returning None")
        return None
    
    return VectorRetriever(
        persist_directory=persist_directory,
        collection_name=collection_name,
    )
