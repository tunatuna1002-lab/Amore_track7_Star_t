"""
Relation definitions for the ranking ontology.

Defines the relationships between entities in the knowledge graph:
- belongsTo: Product → Category
- listedOn: Product → Platform  
- rankedAs: Product → RankingRecord
- recordedAt: RankingRecord → Time
- competesWidth: Product ↔ Product
- triggeredBy: RankingRecord → Event
- partOf: Brand → Company

Reference: docs/ontology_schema.yaml
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


class RelationType(str, Enum):
    """
    Types of relationships in the ontology.
    
    Naming convention: {action}_{target} or {relationship}
    """
    # Core relations (Phase 1)
    BELONGS_TO = "belongsTo"       # Product → Category
    LISTED_ON = "listedOn"         # Product → Platform
    RANKED_AS = "rankedAs"         # Product → RankingRecord
    RECORDED_AT = "recordedAt"     # RankingRecord → Time/Date
    
    # Extended relations (Phase 2)
    COMPETES_WITH = "competesWith" # Product ↔ Product (bidirectional)
    TRIGGERED_BY = "triggeredBy"   # RankingRecord → Event
    PART_OF = "partOf"             # Brand → Company
    PRODUCED_BY = "producedBy"     # Product → Brand


class Cardinality(str, Enum):
    """Relationship cardinality types."""
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_ONE = "N:1"
    MANY_TO_MANY = "N:N"


@dataclass
class RelationDefinition:
    """
    Defines a relationship type in the ontology.
    
    Attributes:
        relation_type: Type of relationship
        from_entity: Source entity type
        to_entity: Target entity type
        cardinality: Relationship cardinality
        description: Human-readable description
        bidirectional: Whether relation goes both ways
        properties: Additional edge properties
    """
    relation_type: RelationType
    from_entity: str  # Entity type name (e.g., "Product")
    to_entity: str    # Entity type name
    cardinality: Cardinality
    description: str
    bidirectional: bool = False
    inverse_name: Optional[str] = None  # Name for reverse relation
    properties: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "type": self.relation_type.value,
            "from": self.from_entity,
            "to": self.to_entity,
            "cardinality": self.cardinality.value,
            "description": self.description,
            "bidirectional": self.bidirectional,
            "inverse_name": self.inverse_name,
            "properties": self.properties,
        }


@dataclass
class Relation:
    """
    Represents an actual relationship instance between two entities.
    
    Attributes:
        relation_type: Type of this relation
        from_id: Source entity ID
        to_id: Target entity ID
        properties: Edge properties/attributes
        created_at: When this relation was created
    """
    relation_type: RelationType
    from_id: str
    to_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    
    def to_edge_tuple(self) -> Tuple[str, str, dict]:
        """Convert to NetworkX edge tuple format."""
        edge_data = {
            "relation_type": self.relation_type.value,
            **self.properties,
        }
        if self.created_at:
            edge_data["created_at"] = self.created_at
        return (self.from_id, self.to_id, edge_data)
    
    def to_dict(self) -> dict:
        return {
            "relation_type": self.relation_type.value,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "properties": self.properties,
            "created_at": self.created_at,
        }


# =============================================================================
# Relation Definitions (Schema)
# =============================================================================

RELATION_DEFINITIONS: Dict[RelationType, RelationDefinition] = {
    
    # -------------------------------------------------------------------------
    # belongsTo: Product → Category
    # -------------------------------------------------------------------------
    RelationType.BELONGS_TO: RelationDefinition(
        relation_type=RelationType.BELONGS_TO,
        from_entity="Product",
        to_entity="Category",
        cardinality=Cardinality.MANY_TO_MANY,
        description="Product belongs to a ranking category",
        bidirectional=False,
        inverse_name="hasProduct",
        properties={
            "first_ranked_date": "str",  # When first appeared in category
            "last_ranked_date": "str",   # When last appeared
        },
    ),
    
    # -------------------------------------------------------------------------
    # listedOn: Product → Platform
    # -------------------------------------------------------------------------
    RelationType.LISTED_ON: RelationDefinition(
        relation_type=RelationType.LISTED_ON,
        from_entity="Product",
        to_entity="Platform",
        cardinality=Cardinality.MANY_TO_MANY,
        description="Product is listed on a platform",
        bidirectional=False,
        inverse_name="hasListing",
        properties={
            "listing_url": "str",
            "first_seen": "str",
        },
    ),
    
    # -------------------------------------------------------------------------
    # rankedAs: Product → RankingRecord
    # -------------------------------------------------------------------------
    RelationType.RANKED_AS: RelationDefinition(
        relation_type=RelationType.RANKED_AS,
        from_entity="Product",
        to_entity="Ranking",
        cardinality=Cardinality.ONE_TO_MANY,
        description="Product has ranking records over time",
        bidirectional=False,
        inverse_name="rankingOf",
        properties={},  # All properties are on RankingRecord node
    ),
    
    # -------------------------------------------------------------------------
    # recordedAt: RankingRecord → Time
    # -------------------------------------------------------------------------
    RelationType.RECORDED_AT: RelationDefinition(
        relation_type=RelationType.RECORDED_AT,
        from_entity="Ranking",
        to_entity="Time",
        cardinality=Cardinality.MANY_TO_ONE,
        description="Ranking was recorded at a specific time",
        bidirectional=False,
        properties={
            "timezone": "str",  # Default: KST
        },
    ),
    
    # -------------------------------------------------------------------------
    # competesWith: Product ↔ Product (Phase 2)
    # -------------------------------------------------------------------------
    RelationType.COMPETES_WITH: RelationDefinition(
        relation_type=RelationType.COMPETES_WITH,
        from_entity="Product",
        to_entity="Product",
        cardinality=Cardinality.MANY_TO_MANY,
        description="Products compete in the same category",
        bidirectional=True,  # Symmetric relation
        properties={
            "category_id": "str",
            "overlap_days": "int",     # Days both in same category
            "rank_correlation": "float", # How ranks correlate
        },
    ),
    
    # -------------------------------------------------------------------------
    # triggeredBy: RankingRecord → Event (Phase 2)
    # -------------------------------------------------------------------------
    RelationType.TRIGGERED_BY: RelationDefinition(
        relation_type=RelationType.TRIGGERED_BY,
        from_entity="Ranking",
        to_entity="Event",
        cardinality=Cardinality.MANY_TO_ONE,
        description="Ranking change was potentially triggered by event",
        bidirectional=False,
        inverse_name="affected",
        properties={
            "confidence": "float",  # How confident we are in the association
            "rank_delta": "int",    # Rank change amount
        },
    ),
    
    # -------------------------------------------------------------------------
    # partOf: Brand → Company (Phase 2)
    # -------------------------------------------------------------------------
    RelationType.PART_OF: RelationDefinition(
        relation_type=RelationType.PART_OF,
        from_entity="Brand",
        to_entity="Brand",  # Parent company is also a Brand node
        cardinality=Cardinality.MANY_TO_ONE,
        description="Brand is part of parent company",
        bidirectional=False,
        inverse_name="owns",
        properties={
            "acquisition_date": "str",
            "ownership_percent": "float",
        },
    ),
    
    # -------------------------------------------------------------------------
    # producedBy: Product → Brand (Phase 2)
    # -------------------------------------------------------------------------
    RelationType.PRODUCED_BY: RelationDefinition(
        relation_type=RelationType.PRODUCED_BY,
        from_entity="Product",
        to_entity="Brand",
        cardinality=Cardinality.MANY_TO_ONE,
        description="Product is produced by brand",
        bidirectional=False,
        inverse_name="produces",
        properties={},
    ),
}


# =============================================================================
# Relation Factory Functions
# =============================================================================

def create_belongs_to_relation(
    product_id: str,
    category_id: str,
    first_ranked_date: Optional[str] = None,
    last_ranked_date: Optional[str] = None
) -> Relation:
    """Create a belongsTo relation between Product and Category."""
    properties = {}
    if first_ranked_date:
        properties["first_ranked_date"] = first_ranked_date
    if last_ranked_date:
        properties["last_ranked_date"] = last_ranked_date
    
    return Relation(
        relation_type=RelationType.BELONGS_TO,
        from_id=product_id,
        to_id=category_id,
        properties=properties,
    )


def create_listed_on_relation(
    product_id: str,
    platform_id: str,
    listing_url: Optional[str] = None,
    first_seen: Optional[str] = None
) -> Relation:
    """Create a listedOn relation between Product and Platform."""
    properties = {}
    if listing_url:
        properties["listing_url"] = listing_url
    if first_seen:
        properties["first_seen"] = first_seen
    
    return Relation(
        relation_type=RelationType.LISTED_ON,
        from_id=product_id,
        to_id=platform_id,
        properties=properties,
    )


def create_ranked_as_relation(
    product_id: str,
    ranking_id: str
) -> Relation:
    """Create a rankedAs relation between Product and RankingRecord."""
    return Relation(
        relation_type=RelationType.RANKED_AS,
        from_id=product_id,
        to_id=ranking_id,
    )


def create_competes_with_relation(
    product_id_1: str,
    product_id_2: str,
    category_id: str,
    overlap_days: int = 0,
    rank_correlation: Optional[float] = None
) -> Relation:
    """Create a competesWith relation between two Products."""
    properties = {
        "category_id": category_id,
        "overlap_days": overlap_days,
    }
    if rank_correlation is not None:
        properties["rank_correlation"] = rank_correlation
    
    return Relation(
        relation_type=RelationType.COMPETES_WITH,
        from_id=product_id_1,
        to_id=product_id_2,
        properties=properties,
    )


def create_produced_by_relation(
    product_id: str,
    brand_id: str
) -> Relation:
    """Create a producedBy relation between Product and Brand."""
    return Relation(
        relation_type=RelationType.PRODUCED_BY,
        from_id=product_id,
        to_id=brand_id,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_relation_definition(relation_type: RelationType) -> Optional[RelationDefinition]:
    """Get the definition for a relation type."""
    return RELATION_DEFINITIONS.get(relation_type)


def validate_relation(relation: Relation) -> bool:
    """
    Validate that a relation conforms to its definition.
    
    Args:
        relation: Relation instance to validate
        
    Returns:
        True if valid, False otherwise
    """
    definition = get_relation_definition(relation.relation_type)
    if not definition:
        logger.warning(f"Unknown relation type: {relation.relation_type}")
        return False
    
    # Check required properties
    for prop_name, prop_type in definition.properties.items():
        if prop_name in relation.properties:
            # Could add type checking here
            pass
    
    return True


def get_inverse_relation_name(relation_type: RelationType) -> Optional[str]:
    """Get the inverse relation name for a given type."""
    definition = get_relation_definition(relation_type)
    return definition.inverse_name if definition else None
