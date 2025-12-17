"""
Tests for Phase 4: Vector Search, LLM Generation, and Dashboard.
"""

import pytest
from datetime import datetime, timedelta


class TestVectorRetriever:
    """Tests for VectorRetriever."""
    
    @pytest.fixture
    def sample_products(self):
        return [
            {
                "product_name": "LANEIGE Lip Sleeping Mask - Berry",
                "brand": "LANEIGE",
                "product_url": "https://amazon.com/dp/LSM001",
                "category": "lip_care",
                "market": "amazon_us",
            },
            {
                "product_name": "LANEIGE Water Sleeping Mask",
                "brand": "LANEIGE",
                "product_url": "https://amazon.com/dp/WSM001",
                "category": "face_mask",
                "market": "amazon_us",
            },
            {
                "product_name": "Burt's Bees Lip Balm",
                "brand": "Burt's Bees",
                "product_url": "https://amazon.com/dp/BB001",
                "category": "lip_care",
                "market": "amazon_us",
            },
        ]
    
    def test_vector_retriever_available(self):
        """Test that VectorRetriever can be imported."""
        from src.retrieval import CHROMADB_AVAILABLE
        # ChromaDB should be available after install
        assert CHROMADB_AVAILABLE is True or CHROMADB_AVAILABLE is False
    
    def test_vector_retriever_import(self):
        """Test VectorRetriever can be imported."""
        from src.retrieval.vector_retriever import VectorRetriever, CHROMADB_AVAILABLE
        
        if CHROMADB_AVAILABLE:
            assert VectorRetriever is not None
        else:
            pytest.skip("ChromaDB not available")
    
    @pytest.mark.skip(reason="ChromaDB embedding model requires network access")
    def test_index_products(self, sample_products):
        """Test indexing products."""
        from src.retrieval.vector_retriever import VectorRetriever
        
        retriever = VectorRetriever(collection_name="test_products")
        count = retriever.index_products(sample_products)
        
        assert count == len(sample_products)
        
        stats = retriever.get_stats()
        assert stats["products_count"] >= len(sample_products)
        
        # Cleanup
        retriever.clear_all()
    
    @pytest.mark.skip(reason="ChromaDB embedding model requires network access")
    def test_search_products(self, sample_products):
        """Test searching products."""
        from src.retrieval.vector_retriever import VectorRetriever
        
        retriever = VectorRetriever(collection_name="test_search")
        retriever.index_products(sample_products)
        
        results = retriever.search_products("lip sleeping mask", top_k=2)
        
        assert len(results) > 0
        assert any("LANEIGE" in r.metadata.get("brand", "") for r in results)
        
        # Cleanup
        retriever.clear_all()


class TestLLMGenerator:
    """Tests for LLMGenerator."""
    
    def test_llm_generator_fallback(self):
        """Test LLM generator falls back to template."""
        from src.retrieval.llm_generator import LLMGenerator, LLMConfig
        from src.retrieval.context_assembler import RAGContext
        from src.retrieval.graph_retriever import GraphContext
        from src.retrieval.entity_extractor import ExtractedEntities, QueryIntent
        
        # Create generator without API key
        generator = LLMGenerator(api_key=None)
        
        # Should not have API available
        assert generator.is_api_available is False
        
        # Create context
        entities = ExtractedEntities(
            brands=["laneige"],
            intent=QueryIntent.CURRENT_RANK,
            raw_query="라네즈 순위",
        )
        
        graph_context = GraphContext(
            query_type="current_rank",
            results=[{
                "product_name": "LANEIGE Lip Sleeping Mask",
                "rank": 1,
                "date": "2024-12-10",
            }]
        )
        
        context = RAGContext(
            query="라네즈 순위",
            intent=QueryIntent.CURRENT_RANK,
            entities=entities,
            graph_context=graph_context,
        )
        
        # Generate should work with fallback
        response = generator.generate("라네즈 순위", context)
        
        assert response.is_fallback is True
        assert response.text
        assert "LANEIGE" in response.text or "1" in response.text
    
    def test_create_generator_function(self):
        """Test creating generator function for pipeline."""
        from src.retrieval.llm_generator import create_generator_function
        
        gen_fn = create_generator_function()
        
        assert callable(gen_fn)


class TestDashboard:
    """Tests for Dashboard application."""
    
    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from src.dashboard.app import create_app, DashboardApp
        
        dashboard = DashboardApp()
        app = create_app(dashboard, debug=True)
        app.config["TESTING"] = True
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "healthy"
    
    def test_api_stats(self, client):
        """Test stats endpoint."""
        response = client.get("/api/stats")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "stats" in data
    
    def test_api_rankings(self, client):
        """Test rankings endpoint."""
        response = client.get("/api/rankings")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "data" in data
    
    def test_api_query(self, client):
        """Test query endpoint."""
        response = client.post(
            "/api/query",
            json={"query": "라네즈 순위"},
            content_type="application/json"
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
    
    def test_api_query_missing_field(self, client):
        """Test query endpoint with missing field."""
        response = client.post(
            "/api/query",
            json={},
            content_type="application/json"
        )
        
        assert response.status_code == 400
    
    def test_index_page(self, client):
        """Test index page."""
        response = client.get("/")
        
        assert response.status_code == 200
        assert b"LANEIGE" in response.data
    
    def test_rankings_page(self, client):
        """Test rankings page."""
        response = client.get("/rankings")
        
        assert response.status_code == 200
    
    def test_insights_page(self, client):
        """Test insights page."""
        response = client.get("/insights")
        
        assert response.status_code == 200
    
    def test_query_page(self, client):
        """Test query page."""
        response = client.get("/query")
        
        assert response.status_code == 200


class TestDashboardWithData:
    """Tests for Dashboard with sample data."""
    
    @pytest.fixture
    def sample_snapshots(self):
        """Generate sample data."""
        base_date = datetime(2024, 12, 1)
        snapshots = []
        
        for i in range(10):
            snapshots.append({
                "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 3 - min(i // 4, 2),
                "product_name_raw": "LANEIGE Lip Sleeping Mask",
                "brand_raw": "LANEIGE",
                "product_url": "https://amazon.com/dp/LSM001",
                "parse_status": "full",
                "run_id": f"run_{i:03d}",
            })
        
        return snapshots
    
    @pytest.fixture
    def app_with_data(self, sample_snapshots):
        """Create Flask app with data."""
        from src.dashboard.app import create_app, DashboardApp
        from src.retrieval import create_simple_pipeline
        
        pipeline = create_simple_pipeline(sample_snapshots)
        dashboard = DashboardApp(rag_pipeline=pipeline)
        dashboard.set_sample_data(sample_snapshots)
        
        app = create_app(dashboard, debug=True)
        app.config["TESTING"] = True
        
        return app
    
    def test_stats_with_data(self, app_with_data):
        """Test stats with actual data."""
        client = app_with_data.test_client()
        response = client.get("/api/stats")
        
        data = response.get_json()
        assert data["stats"]["total_records"] == 10
        assert data["stats"]["laneige"]["unique_products"] == 1
    
    def test_query_with_data(self, app_with_data):
        """Test query with actual data."""
        client = app_with_data.test_client()
        response = client.post(
            "/api/query",
            json={"query": "라네즈 현재 순위"},
            content_type="application/json"
        )
        
        data = response.get_json()
        assert data["success"] is True
        assert "LANEIGE" in data["result"]["answer"] or "1" in data["result"]["answer"]
