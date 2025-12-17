"""
Graph-RAG Retrieval Module for Laneige Ranking Collector.

Implements the retrieval pipeline for question answering:
1. Entity Extraction - Extract products, categories, dates from queries
2. Graph Retrieval - Traverse knowledge graph for structured data
3. Vector Retrieval - Semantic search for related information
4. Hybrid Retrieval - Combine graph and vector results
5. Context Assembly - Build context for LLM generation
6. LLM Generation - Generate natural language responses

Usage:
    from src.retrieval import RAGPipeline, create_simple_pipeline
    
    pipeline = create_simple_pipeline(snapshots)
    response = pipeline.query("라네즈 립 슬리핑 마스크 현재 순위는?")
"""

from .entity_extractor import (
    EntityExtractor,
    ExtractedEntities,
    QueryIntent,
)
from .graph_retriever import (
    GraphRetriever,
    GraphContext,
)
from .context_assembler import (
    ContextAssembler,
    RAGContext,
)
from .rag_pipeline import (
    RAGPipeline,
    RAGPipelineBuilder,
    RAGResponse,
    create_simple_pipeline,
    create_pipeline_from_storage,
)

# Optional imports (may not be available)
try:
    from .vector_retriever import (
        VectorRetriever,
        VectorSearchResult,
        create_vector_retriever,
        CHROMADB_AVAILABLE,
    )
except ImportError:
    VectorRetriever = None
    VectorSearchResult = None
    create_vector_retriever = None
    CHROMADB_AVAILABLE = False

try:
    from .llm_generator import (
        LLMGenerator,
        LLMConfig,
        LLMResponse,
        StreamingLLMGenerator,
        create_llm_generator,
        create_generator_function,
        ANTHROPIC_AVAILABLE,
    )
except ImportError:
    LLMGenerator = None
    LLMConfig = None
    LLMResponse = None
    StreamingLLMGenerator = None
    create_llm_generator = None
    create_generator_function = None
    ANTHROPIC_AVAILABLE = False

__all__ = [
    # Entity Extraction
    "EntityExtractor",
    "ExtractedEntities",
    "QueryIntent",
    # Graph Retrieval
    "GraphRetriever",
    "GraphContext",
    # Context Assembly
    "ContextAssembler",
    "RAGContext",
    # Pipeline
    "RAGPipeline",
    "RAGPipelineBuilder",
    "RAGResponse",
    # Convenience functions
    "create_simple_pipeline",
    "create_pipeline_from_storage",
    # Vector Retrieval (optional)
    "VectorRetriever",
    "VectorSearchResult",
    "create_vector_retriever",
    "CHROMADB_AVAILABLE",
    # LLM Generation (optional)
    "LLMGenerator",
    "LLMConfig",
    "LLMResponse",
    "StreamingLLMGenerator",
    "create_llm_generator",
    "create_generator_function",
    "ANTHROPIC_AVAILABLE",
]
