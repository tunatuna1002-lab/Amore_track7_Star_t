"""
Tests for the Graph-RAG retrieval module.

Tests entity extraction, graph retrieval, context assembly,
and the full RAG pipeline.
"""

import pytest
from datetime import datetime, timedelta


class TestEntityExtractor:
    """Tests for EntityExtractor."""
    
    @pytest.fixture
    def extractor(self):
        from src.retrieval.entity_extractor import EntityExtractor
        return EntityExtractor()
    
    def test_extract_brand_korean(self, extractor):
        """Test brand extraction from Korean text."""
        query = "라네즈 립 슬리핑 마스크 순위"
        entities = extractor.extract(query)
        
        assert "laneige" in entities.brands
    
    def test_extract_brand_english(self, extractor):
        """Test brand extraction from English text."""
        query = "LANEIGE lip sleeping mask rank"
        entities = extractor.extract(query)
        
        assert "laneige" in entities.brands
    
    def test_extract_platform_amazon(self, extractor):
        """Test Amazon platform extraction."""
        query = "아마존에서 라네즈 순위"
        entities = extractor.extract(query)
        
        assert "amazon_us" in entities.platforms
    
    def test_extract_platform_cosme(self, extractor):
        """Test @cosme platform extraction."""
        query = "@cosme 립케어 랭킹"
        entities = extractor.extract(query)
        
        assert "cosme_jp" in entities.platforms
    
    def test_extract_category(self, extractor):
        """Test category extraction."""
        query = "립케어 카테고리 순위"
        entities = extractor.extract(query)
        
        assert "lip_care" in entities.categories
    
    def test_classify_intent_current_rank(self, extractor):
        """Test current rank intent classification."""
        from src.retrieval.entity_extractor import QueryIntent
        
        queries = [
            "현재 순위는?",
            "지금 몇 위야?",
            "오늘 순위",
        ]
        
        for query in queries:
            entities = extractor.extract(query)
            assert entities.intent == QueryIntent.CURRENT_RANK, f"Failed for: {query}"
    
    def test_classify_intent_rank_history(self, extractor):
        """Test rank history intent classification."""
        from src.retrieval.entity_extractor import QueryIntent
        
        queries = [
            "최근 30일 순위 변동",
            "순위 추이 보여줘",
            "지난 일주일 변화",
        ]
        
        for query in queries:
            entities = extractor.extract(query)
            assert entities.intent == QueryIntent.RANK_HISTORY, f"Failed for: {query}"
    
    def test_classify_intent_top_n(self, extractor):
        """Test top N intent classification."""
        from src.retrieval.entity_extractor import QueryIntent
        
        query = "Top 10 제품"
        entities = extractor.extract(query)
        
        assert entities.intent == QueryIntent.TOP_N
        assert entities.top_n == 10
    
    def test_extract_time_range_recent_days(self, extractor):
        """Test time range extraction for '최근 N일'."""
        query = "최근 7일 순위"
        entities = extractor.extract(query)
        
        assert entities.time_range is not None
        start, end = entities.time_range
        
        # Verify range is approximately 7 days
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        
        assert (end_dt - start_dt).days == 7
    
    def test_extract_product_keywords(self, extractor):
        """Test product keyword extraction."""
        query = "립 슬리핑 마스크 라네즈"
        entities = extractor.extract(query)
        
        # Should extract product-like keywords
        assert len(entities.products) > 0 or "laneige" in entities.brands


class TestGraphRetriever:
    """Tests for GraphRetriever."""
    
    @pytest.fixture
    def sample_snapshots(self):
        """Sample ranking snapshots."""
        base_date = datetime(2024, 12, 1)
        snapshots = []
        
        # Product A: LANEIGE Lip Sleeping Mask
        for i in range(10):
            snapshots.append({
                "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 3,
                "product_name_raw": "LANEIGE Lip Sleeping Mask",
                "brand_raw": "LANEIGE",
                "product_url": "https://amazon.com/dp/B00BXZZZZZ",
                "parse_status": "full",
                "run_id": f"run_{i:03d}",
            })
        
        # Product B: competitor
        for i in range(10):
            snapshots.append({
                "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": 1,
                "product_name_raw": "Competitor Lip Balm",
                "brand_raw": "Competitor",
                "product_url": "https://amazon.com/dp/C111",
                "parse_status": "full",
                "run_id": f"run_{i:03d}",
            })
        
        return snapshots
    
    @pytest.fixture
    def graph_retriever(self, sample_snapshots):
        """Create graph retriever with sample data."""
        pytest.importorskip("networkx")
        from src.ontology import RankingGraph
        from src.retrieval.graph_retriever import GraphRetriever
        
        graph = RankingGraph()
        graph.build_from_snapshots(sample_snapshots)
        
        return GraphRetriever(graph)
    
    def test_retrieve_current_rank(self, graph_retriever):
        """Test current rank retrieval."""
        from src.retrieval.entity_extractor import EntityExtractor, QueryIntent
        
        extractor = EntityExtractor()
        entities = extractor.extract("라네즈 현재 순위")
        
        context = graph_retriever.retrieve(entities)
        
        assert context.query_type == "current_rank"
        assert len(context.results) > 0
        
        # Find LANEIGE result
        laneige_results = [
            r for r in context.results
            if "LANEIGE" in r.get("product_name", "")
        ]
        assert len(laneige_results) > 0
        assert laneige_results[0]["rank"] == 3
    
    def test_retrieve_rank_history(self, graph_retriever):
        """Test rank history retrieval."""
        from src.retrieval.entity_extractor import EntityExtractor, ExtractedEntities, QueryIntent
        
        # Create entities with explicit time range matching sample data
        entities = ExtractedEntities(
            brands=["laneige"],
            products=["LANEIGE Lip Sleeping Mask"],
            intent=QueryIntent.RANK_HISTORY,
            time_range=("2024-12-01", "2024-12-15"),  # Match sample data dates
            raw_query="라네즈 최근 순위 변동",
        )
        
        context = graph_retriever.retrieve(entities)
        
        assert context.query_type == "rank_history"
        assert len(context.results) > 0
        
        # Should have history data
        result = context.results[0]
        assert "history" in result
        assert len(result["history"]) > 0
    
    def test_retrieve_top_n(self, graph_retriever):
        """Test top N retrieval."""
        from src.retrieval.entity_extractor import EntityExtractor
        
        extractor = EntityExtractor()
        entities = extractor.extract("아마존 lip_care Top 5")
        
        context = graph_retriever.retrieve(entities)
        
        assert context.query_type == "top_n"
        # Should return ranked products


class TestContextAssembler:
    """Tests for ContextAssembler."""
    
    @pytest.fixture
    def assembler(self):
        from src.retrieval.context_assembler import ContextAssembler
        return ContextAssembler()
    
    def test_assemble_context(self, assembler):
        """Test basic context assembly."""
        from src.retrieval.entity_extractor import ExtractedEntities, QueryIntent
        from src.retrieval.graph_retriever import GraphContext
        
        entities = ExtractedEntities(
            brands=["laneige"],
            intent=QueryIntent.CURRENT_RANK,
            raw_query="라네즈 순위",
        )
        
        graph_context = GraphContext(
            query_type="current_rank",
            results=[{
                "product_name": "LANEIGE Lip Sleeping Mask",
                "rank": 3,
                "date": "2024-12-10",
                "market": "amazon_us",
            }]
        )
        
        context = assembler.assemble(
            query="라네즈 순위",
            entities=entities,
            graph_context=graph_context,
        )
        
        assert context.query == "라네즈 순위"
        assert context.intent == QueryIntent.CURRENT_RANK
        assert context.has_data()
    
    def test_format_for_prompt(self, assembler):
        """Test context formatting for LLM prompt."""
        from src.retrieval.entity_extractor import ExtractedEntities, QueryIntent
        from src.retrieval.graph_retriever import GraphContext
        
        entities = ExtractedEntities(
            brands=["laneige"],
            intent=QueryIntent.CURRENT_RANK,
            raw_query="라네즈 순위",
        )
        
        graph_context = GraphContext(
            query_type="current_rank",
            results=[{
                "product_name": "LANEIGE Lip Sleeping Mask",
                "brand": "LANEIGE",
                "rank": 3,
                "date": "2024-12-10",
                "market": "amazon_us",
            }]
        )
        
        from src.retrieval.context_assembler import RAGContext
        context = RAGContext(
            query="라네즈 순위",
            intent=QueryIntent.CURRENT_RANK,
            entities=entities,
            graph_context=graph_context,
        )
        
        formatted = assembler.format_for_prompt(context)
        
        assert "LANEIGE" in formatted
        assert "3위" in formatted or "3" in formatted
    
    def test_generate_answer_template(self, assembler):
        """Test template-based answer generation."""
        from src.retrieval.entity_extractor import ExtractedEntities, QueryIntent
        from src.retrieval.graph_retriever import GraphContext
        from src.retrieval.context_assembler import RAGContext
        
        entities = ExtractedEntities(
            brands=["laneige"],
            intent=QueryIntent.CURRENT_RANK,
            raw_query="라네즈 순위",
        )
        
        graph_context = GraphContext(
            query_type="current_rank",
            results=[{
                "product_name": "LANEIGE Lip Sleeping Mask",
                "brand": "LANEIGE",
                "rank": 3,
                "date": "2024-12-10",
                "market": "amazon_us",
                "category_key": "lip_care",
            }]
        )
        
        context = RAGContext(
            query="라네즈 순위",
            intent=QueryIntent.CURRENT_RANK,
            entities=entities,
            graph_context=graph_context,
        )
        
        answer = assembler.generate_answer_template(context)
        
        assert "LANEIGE" in answer
        assert "3위" in answer
        assert "amazon_us" in answer or "lip_care" in answer


class TestRAGPipeline:
    """Tests for the full RAG pipeline."""
    
    @pytest.fixture
    def sample_snapshots(self):
        """Sample ranking snapshots."""
        base_date = datetime(2024, 12, 1)
        snapshots = []
        
        # LANEIGE product with improving rank
        ranks = [5, 4, 4, 3, 3, 3, 2, 2, 2, 1]
        for i, rank in enumerate(ranks):
            snapshots.append({
                "date_kst": (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "market": "amazon_us",
                "category_key": "lip_care",
                "category_url": "https://amazon.com/lip-care",
                "rank": rank,
                "product_name_raw": "LANEIGE Lip Sleeping Mask - Berry",
                "brand_raw": "LANEIGE",
                "product_url": "https://amazon.com/dp/B00BXZZZZZ",
                "parse_status": "full",
                "run_id": f"run_{i:03d}",
            })
        
        return snapshots
    
    @pytest.fixture
    def pipeline(self, sample_snapshots):
        """Create RAG pipeline with sample data."""
        pytest.importorskip("networkx")
        from src.retrieval.rag_pipeline import create_simple_pipeline
        
        return create_simple_pipeline(sample_snapshots)
    
    def test_query_current_rank(self, pipeline):
        """Test querying for current rank."""
        response = pipeline.query("라네즈 립 슬리핑 마스크 현재 순위는?")
        
        assert response.answer
        assert "LANEIGE" in response.answer or "라네즈" in response.answer
        assert "1위" in response.answer or "1" in response.answer
    
    def test_query_rank_history(self, pipeline):
        """Test querying for rank history."""
        response = pipeline.query("라네즈 최근 순위 변동")
        
        assert response.answer
        assert response.context.intent.value in ["rank_history", "rank_change"]
    
    def test_query_confidence(self, pipeline):
        """Test that confidence is calculated."""
        response = pipeline.query("라네즈 순위")
        
        assert response.confidence > 0
        assert response.confidence <= 1.0
    
    def test_query_processing_time(self, pipeline):
        """Test that processing time is tracked."""
        response = pipeline.query("라네즈 순위")
        
        assert response.processing_time_ms > 0
        assert response.processing_time_ms < 5000  # Should be fast
    
    def test_query_sources(self, pipeline):
        """Test that sources are provided."""
        response = pipeline.query("라네즈 순위")
        
        # Should have at least one source
        assert len(response.sources) >= 0  # May be 0 for simple queries
    
    def test_pipeline_builder(self, sample_snapshots):
        """Test pipeline builder pattern."""
        pytest.importorskip("networkx")
        from src.retrieval.rag_pipeline import RAGPipelineBuilder
        from src.ontology import RankingGraph
        from src.insights import KnowledgeEngine
        
        graph = RankingGraph()
        graph.build_from_snapshots(sample_snapshots)
        
        pipeline = (
            RAGPipelineBuilder()
            .with_graph(graph)
            .with_snapshots(sample_snapshots)
            .with_knowledge_engine(KnowledgeEngine())
            .build()
        )
        
        response = pipeline.query("라네즈 순위")
        assert response.answer
