"""
RAG Pipeline for Laneige Ranking Collector.

Integrates all retrieval components into a unified pipeline:
1. Entity Extraction
2. Graph Retrieval
3. Context Assembly
4. Response Generation

Usage:
    from src.retrieval import RAGPipeline
    from src.ontology import RankingGraph
    
    graph = RankingGraph()
    graph.build_from_snapshots(snapshots)
    
    pipeline = RAGPipeline(graph)
    response = pipeline.query("라네즈 립 슬리핑 마스크 현재 순위는?")
    
    print(response.answer)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from src.ontology import RankingGraph
from src.insights import KnowledgeEngine

from .entity_extractor import EntityExtractor, ExtractedEntities, QueryIntent
from .graph_retriever import GraphRetriever, GraphContext
from .context_assembler import ContextAssembler, RAGContext

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """
    Response from the RAG pipeline.
    
    Attributes:
        query: Original user query
        answer: Generated answer text
        context: Full RAG context (for debugging/transparency)
        confidence: Confidence score (0-1)
        sources: List of source references
        processing_time_ms: Time taken to process query
    """
    query: str
    answer: str
    context: RAGContext
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "confidence": self.confidence,
            "sources": self.sources,
            "processing_time_ms": self.processing_time_ms,
            "intent": self.context.intent.value,
            "graph_results_count": len(self.context.graph_context.results),
            "rule_matches_count": len(self.context.rule_matches),
        }


class RAGPipeline:
    """
    Main RAG pipeline for question answering.
    
    Orchestrates entity extraction, graph retrieval, context assembly,
    and response generation.
    """
    
    def __init__(
        self,
        graph: RankingGraph,
        knowledge_engine: Optional[KnowledgeEngine] = None,
        rank_history: Optional[List[dict]] = None,
        llm_generator: Optional[Callable[[str, RAGContext], str]] = None,
    ):
        """
        Initialize the RAG pipeline.
        
        Args:
            graph: RankingGraph instance
            knowledge_engine: KnowledgeEngine for rule matching
            rank_history: Full ranking history for insights
            llm_generator: Optional LLM generator function
        """
        self.graph = graph
        self.rank_history = rank_history or []
        
        # Initialize components
        self.entity_extractor = EntityExtractor(
            product_index=self._get_product_names()
        )
        self.graph_retriever = GraphRetriever(graph)
        self.knowledge_engine = knowledge_engine or KnowledgeEngine()
        self.context_assembler = ContextAssembler(
            knowledge_engine=self.knowledge_engine
        )
        self.llm_generator = llm_generator
        
        logger.info("RAGPipeline initialized")
    
    def _get_product_names(self) -> List[str]:
        """Get product names from graph for entity extraction."""
        return [p.product_name_raw for p in self.graph._products.values()]
    
    def query(self, query: str) -> RAGResponse:
        """
        Process a user query through the RAG pipeline.
        
        Args:
            query: Natural language query
            
        Returns:
            RAGResponse with answer and context
        """
        start_time = datetime.now()
        
        # Step 1: Entity Extraction
        logger.debug(f"Processing query: {query}")
        entities = self.entity_extractor.extract(query)
        logger.debug(f"Extracted entities: {entities.to_dict()}")
        
        # Step 2: Graph Retrieval
        graph_context = self.graph_retriever.retrieve(entities)
        logger.debug(f"Graph results: {len(graph_context.results)}")
        
        # Step 3: Context Assembly
        rag_context = self.context_assembler.assemble(
            query=query,
            entities=entities,
            graph_context=graph_context,
            rank_history=self.rank_history,
        )
        
        # Step 4: Response Generation
        if self.llm_generator:
            # Use LLM for generation
            answer = self.llm_generator(query, rag_context)
        else:
            # Use template-based generation
            answer = self.context_assembler.generate_answer_template(rag_context)
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Build sources list
        sources = self._build_sources(rag_context)
        
        # Calculate confidence
        confidence = self._calculate_confidence(entities, graph_context)
        
        response = RAGResponse(
            query=query,
            answer=answer,
            context=rag_context,
            confidence=confidence,
            sources=sources,
            processing_time_ms=processing_time,
        )
        
        logger.info(
            f"Query processed in {processing_time:.1f}ms, "
            f"confidence: {confidence:.2f}"
        )
        
        return response
    
    def _build_sources(self, context: RAGContext) -> List[str]:
        """Build list of source references."""
        sources = []
        
        # Add graph sources
        for result in context.graph_context.results[:5]:
            if "date" in result:
                sources.append(f"Ranking data ({result.get('date')})")
            elif "recorded_at" in result:
                sources.append(f"Ranking data ({result.get('recorded_at')})")
        
        # Add rule sources
        for match in context.rule_matches[:3]:
            sources.append(f"{match.rule_name} insight")
        
        return list(set(sources))
    
    def _calculate_confidence(
        self,
        entities: ExtractedEntities,
        graph_context: GraphContext
    ) -> float:
        """Calculate confidence score for the response."""
        score = 0.0
        
        # Entity extraction confidence
        score += entities.confidence * 0.3
        
        # Graph results confidence
        if graph_context.results:
            score += 0.4
            # More results = higher confidence (up to a point)
            score += min(len(graph_context.results) * 0.05, 0.2)
        
        # Intent clarity
        if entities.intent != QueryIntent.GENERAL:
            score += 0.1
        
        return min(score, 1.0)
    
    def update_graph(self, graph: RankingGraph):
        """Update the graph reference."""
        self.graph = graph
        self.graph_retriever = GraphRetriever(graph)
        self.entity_extractor.update_product_index(self._get_product_names())
        logger.info("Graph updated in pipeline")
    
    def update_rank_history(self, rank_history: List[dict]):
        """Update the ranking history for insights."""
        self.rank_history = rank_history
        logger.info(f"Rank history updated: {len(rank_history)} records")


class RAGPipelineBuilder:
    """
    Builder for RAGPipeline with convenient configuration.
    """
    
    def __init__(self):
        self._graph: Optional[RankingGraph] = None
        self._knowledge_engine: Optional[KnowledgeEngine] = None
        self._rank_history: List[dict] = []
        self._llm_generator: Optional[Callable] = None
    
    def with_graph(self, graph: RankingGraph) -> "RAGPipelineBuilder":
        """Set the knowledge graph."""
        self._graph = graph
        return self
    
    def with_snapshots(self, snapshots: List[dict]) -> "RAGPipelineBuilder":
        """Build graph from snapshots and store history."""
        if self._graph is None:
            self._graph = RankingGraph()
        self._graph.build_from_snapshots(snapshots)
        self._rank_history = snapshots
        return self
    
    def with_knowledge_engine(self, engine: KnowledgeEngine) -> "RAGPipelineBuilder":
        """Set the knowledge engine."""
        self._knowledge_engine = engine
        return self
    
    def with_llm_generator(self, generator: Callable[[str, RAGContext], str]) -> "RAGPipelineBuilder":
        """Set the LLM generator function."""
        self._llm_generator = generator
        return self
    
    def build(self) -> RAGPipeline:
        """Build the pipeline."""
        if self._graph is None:
            raise ValueError("Graph is required. Call with_graph() or with_snapshots()")
        
        return RAGPipeline(
            graph=self._graph,
            knowledge_engine=self._knowledge_engine,
            rank_history=self._rank_history,
            llm_generator=self._llm_generator,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def create_pipeline_from_storage(storage) -> RAGPipeline:
    """
    Create RAG pipeline from ExcelStorage.
    
    Args:
        storage: ExcelStorage instance
        
    Returns:
        Configured RAGPipeline
    """
    from src.ontology import GraphBuilder
    
    # Get ranking history
    rank_history = storage.get_rank_history()
    
    # Build graph
    builder = GraphBuilder()
    graph = builder.from_snapshot_list(rank_history)
    
    # Create pipeline
    return (
        RAGPipelineBuilder()
        .with_graph(graph)
        .with_snapshots(rank_history)
        .with_knowledge_engine(KnowledgeEngine())
        .build()
    )


def create_simple_pipeline(snapshots: List[dict]) -> RAGPipeline:
    """
    Create a simple RAG pipeline from snapshot list.
    
    Args:
        snapshots: List of ranking snapshot dictionaries
        
    Returns:
        Configured RAGPipeline
    """
    return (
        RAGPipelineBuilder()
        .with_snapshots(snapshots)
        .with_knowledge_engine(KnowledgeEngine())
        .build()
    )
