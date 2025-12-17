"""
Ontology module for Laneige Ranking Collector.

Provides structured data models (entities) and relationship definitions
for Graph-RAG implementation.

Entities:
- ProductNode: Product information
- CategoryNode: Category information  
- PlatformNode: Platform (Amazon US, @cosme Japan)
- RankingRecord: Time-series ranking data

Relations:
- belongsTo: Product → Category
- listedOn: Product → Platform
- rankedAs: Product → RankingRecord
- competessWith: Product ↔ Product
"""

from .entities import (
    ProductNode,
    CategoryNode,
    PlatformNode,
    RankingRecord,
    BrandNode,
    EventNode,
)
from .relations import (
    Relation,
    RelationType,
    RELATION_DEFINITIONS,
)
from .graph_builder import (
    RankingGraph,
    GraphBuilder,
)

__all__ = [
    # Entities
    "ProductNode",
    "CategoryNode", 
    "PlatformNode",
    "RankingRecord",
    "BrandNode",
    "EventNode",
    # Relations
    "Relation",
    "RelationType",
    "RELATION_DEFINITIONS",
    # Graph
    "RankingGraph",
    "GraphBuilder",
]
