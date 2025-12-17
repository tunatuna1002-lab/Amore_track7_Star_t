"""
Tests for ontology module.

Tests entity definitions, relations, and graph builder.
"""

import pytest
from datetime import datetime


class TestProductNode:
    """Tests for ProductNode entity."""
    
    def test_generate_id_deterministic(self):
        """Test that ID generation is deterministic."""
        from src.ontology.entities import ProductNode
        
        url = "https://amazon.com/dp/B00BXZZZZZ"
        id1 = ProductNode.generate_id(url)
        id2 = ProductNode.generate_id(url)
        
        assert id1 == id2
        assert len(id1) == 32  # MD5 hex length
    
    def test_from_snapshot(self):
        """Test creating ProductNode from snapshot."""
        from src.ontology.entities import ProductNode
        
        snapshot = {
            "date_kst": "2024-12-17",
            "market": "amazon_us",
            "category_key": "lip_care",
            "rank": 3,
            "product_name_raw": "LANEIGE Lip Sleeping Mask",
            "brand_raw": "LANEIGE",
            "product_url": "https://amazon.com/dp/B00BXZZZZZ",
        }
        
        product = ProductNode.from_snapshot(snapshot)
        
        assert product.product_name_raw == "LANEIGE Lip Sleeping Mask"
        assert product.product_url == "https://amazon.com/dp/B00BXZZZZZ"
        assert product.brand == "LANEIGE"
        assert product.first_seen == "2024-12-17"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        from src.ontology.entities import ProductNode
        
        product = ProductNode(
            product_id="abc123",
            product_name_raw="Test Product",
            product_url="https://example.com/product",
        )
        
        data = product.to_dict()
        
        assert data["node_type"] == "Product"
        assert data["product_id"] == "abc123"
        assert data["product_name_raw"] == "Test Product"


class TestCategoryNode:
    """Tests for CategoryNode entity."""
    
    def test_generate_id(self):
        """Test category ID generation."""
        from src.ontology.entities import CategoryNode
        
        category_id = CategoryNode.generate_id("amazon_us", "lip_care")
        
        assert category_id == "amazon_us_lip_care"
    
    def test_to_dict(self):
        """Test serialization."""
        from src.ontology.entities import CategoryNode
        
        category = CategoryNode(
            category_id="amazon_us_lip_care",
            category_key="lip_care",
            category_name="Lip Care",
            category_url="https://amazon.com/lip-care",
            platform_id="amazon_us",
        )
        
        data = category.to_dict()
        
        assert data["node_type"] == "Category"
        assert data["category_key"] == "lip_care"


class TestRankingRecord:
    """Tests for RankingRecord entity."""
    
    def test_generate_id_composite_key(self):
        """Test ranking ID generation from composite key."""
        from src.ontology.entities import RankingRecord
        
        id1 = RankingRecord.generate_id(
            "2024-12-17", "amazon_us", "lip_care", 3, "https://amazon.com/dp/B00BXZZZZZ"
        )
        id2 = RankingRecord.generate_id(
            "2024-12-17", "amazon_us", "lip_care", 3, "https://amazon.com/dp/B00BXZZZZZ"
        )
        
        assert id1 == id2
        
        # Different rank should give different ID
        id3 = RankingRecord.generate_id(
            "2024-12-17", "amazon_us", "lip_care", 4, "https://amazon.com/dp/B00BXZZZZZ"
        )
        assert id1 != id3
    
    def test_from_snapshot(self):
        """Test creating RankingRecord from snapshot."""
        from src.ontology.entities import RankingRecord, ParseStatus
        
        snapshot = {
            "date_kst": "2024-12-17",
            "market": "amazon_us",
            "category_key": "lip_care",
            "category_url": "https://amazon.com/lip-care",
            "rank": 3,
            "product_name_raw": "Test Product",
            "product_url": "https://amazon.com/dp/B00BXZZZZZ",
            "parse_status": "full",
            "run_id": "run_001",
        }
        
        ranking = RankingRecord.from_snapshot(snapshot)
        
        assert ranking.rank == 3
        assert ranking.recorded_at == "2024-12-17"
        assert ranking.parse_status == ParseStatus.FULL


class TestRelations:
    """Tests for relation definitions."""
    
    def test_relation_definitions_exist(self):
        """Test that all relation types have definitions."""
        from src.ontology.relations import RelationType, RELATION_DEFINITIONS
        
        for relation_type in RelationType:
            assert relation_type in RELATION_DEFINITIONS, \
                f"Missing definition for {relation_type}"
    
    def test_create_belongs_to_relation(self):
        """Test creating belongsTo relation."""
        from src.ontology.relations import create_belongs_to_relation, RelationType
        
        relation = create_belongs_to_relation(
            product_id="Product:abc123",
            category_id="Category:amazon_us_lip_care",
            first_ranked_date="2024-12-17",
        )
        
        assert relation.relation_type == RelationType.BELONGS_TO
        assert relation.from_id == "Product:abc123"
        assert relation.to_id == "Category:amazon_us_lip_care"
    
    def test_relation_to_edge_tuple(self):
        """Test converting relation to edge tuple."""
        from src.ontology.relations import create_ranked_as_relation
        
        relation = create_ranked_as_relation(
            product_id="Product:abc",
            ranking_id="Ranking:xyz",
        )
        
        from_id, to_id, edge_data = relation.to_edge_tuple()
        
        assert from_id == "Product:abc"
        assert to_id == "Ranking:xyz"
        assert "relation_type" in edge_data


class TestRankingGraph:
    """Tests for RankingGraph."""
    
    @pytest.fixture
    def sample_snapshots(self):
        """Sample ranking snapshots for testing."""
        return [
            {
                "date_kst": "2024-12-17",
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 1,
                "product_name_raw": "Product A",
                "brand_raw": "Brand A",
                "product_url": "https://amazon.com/dp/A111",
                "parse_status": "full",
                "run_id": "run_001",
            },
            {
                "date_kst": "2024-12-17",
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 2,
                "product_name_raw": "LANEIGE Lip Sleeping Mask",
                "brand_raw": "LANEIGE",
                "product_url": "https://amazon.com/dp/B222",
                "parse_status": "full",
                "run_id": "run_001",
            },
            {
                "date_kst": "2024-12-18",
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 1,
                "product_name_raw": "LANEIGE Lip Sleeping Mask",
                "brand_raw": "LANEIGE",
                "product_url": "https://amazon.com/dp/B222",
                "parse_status": "full",
                "run_id": "run_002",
            },
        ]
    
    def test_build_from_snapshots(self, sample_snapshots):
        """Test building graph from snapshots."""
        pytest.importorskip("networkx")
        from src.ontology.graph_builder import RankingGraph
        
        graph = RankingGraph()
        graph.build_from_snapshots(sample_snapshots)
        
        stats = graph.get_stats()
        
        assert stats["products"] == 2
        assert stats["rankings"] == 3
        assert stats["categories"] == 1
    
    def test_find_products_by_brand(self, sample_snapshots):
        """Test finding products by brand."""
        pytest.importorskip("networkx")
        from src.ontology.graph_builder import RankingGraph
        
        graph = RankingGraph()
        graph.build_from_snapshots(sample_snapshots)
        
        laneige_products = graph.find_products_by_brand("LANEIGE")
        
        assert len(laneige_products) == 1
        assert "Lip Sleeping Mask" in laneige_products[0].product_name_raw
    
    def test_get_product_rankings(self, sample_snapshots):
        """Test getting product ranking history."""
        pytest.importorskip("networkx")
        from src.ontology.graph_builder import RankingGraph
        from src.ontology.entities import ProductNode
        
        graph = RankingGraph()
        graph.build_from_snapshots(sample_snapshots)
        
        product_id = ProductNode.generate_id("https://amazon.com/dp/B222")
        rankings = graph.get_product_rankings(product_id)
        
        assert len(rankings) == 2
        assert rankings[0].rank == 2  # First day
        assert rankings[1].rank == 1  # Second day


class TestKnowledgeEngine:
    """Tests for KnowledgeEngine."""
    
    @pytest.fixture
    def sample_history(self):
        """Sample ranking history for testing."""
        from datetime import datetime, timedelta
        
        base_date = datetime(2024, 12, 1)
        history = []
        
        # Product A: stable in top 5 for 10 days
        for i in range(10):
            history.append({
                "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "market": "amazon_us",
                "category_key": "lip_care",
                "rank": 3,
                "product_name_raw": "LANEIGE Lip Sleeping Mask",
                "product_url": "https://amazon.com/dp/B222",
            })
        
        # Product B: rising star (rank improved by 15)
        history.append({
            "date_kst": "2024-12-09",
            "market": "amazon_us",
            "category_key": "lip_care",
            "rank": 20,
            "product_name_raw": "Rising Product",
            "product_url": "https://amazon.com/dp/C333",
        })
        history.append({
            "date_kst": "2024-12-10",
            "market": "amazon_us",
            "category_key": "lip_care",
            "rank": 5,
            "product_name_raw": "Rising Product",
            "product_url": "https://amazon.com/dp/C333",
        })
        
        return history
    
    def test_evaluate_stable_leader(self, sample_history):
        """Test stable leader rule detection."""
        from src.insights.knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine()
        matches = engine.evaluate_all(sample_history)
        
        stable_leaders = [m for m in matches if m.tag == "stable_leader"]
        
        assert len(stable_leaders) > 0
        assert any("LANEIGE" in m.product_name for m in stable_leaders)
    
    def test_evaluate_rising_star(self, sample_history):
        """Test rising star rule detection."""
        from src.insights.knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine()
        matches = engine.evaluate_all(sample_history)
        
        rising_stars = [m for m in matches if m.tag == "rising_star"]
        
        assert len(rising_stars) > 0
        assert any("Rising Product" in m.product_name for m in rising_stars)
    
    def test_generate_report(self, sample_history):
        """Test report generation."""
        from src.insights.knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine()
        matches = engine.evaluate_all(sample_history)
        report = engine.generate_report(matches)
        
        assert "Knowledge Rule Engine Report" in report
        assert len(report) > 100
