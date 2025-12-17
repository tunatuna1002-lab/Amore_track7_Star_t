"""
Context Assembler for Graph-RAG pipeline.

Assembles context from multiple sources:
- Graph retrieval results
- Knowledge engine rule matches
- Vector search results (optional)

Formats the context for LLM prompt generation.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Dict, List, Optional, Any

from .entity_extractor import ExtractedEntities, QueryIntent
from .graph_retriever import GraphContext
from src.insights import KnowledgeEngine, RuleMatch

logger = logging.getLogger(__name__)


@dataclass
class RAGContext:
    """
    Assembled context for LLM generation.
    
    Attributes:
        query: Original user query
        intent: Classified query intent
        entities: Extracted entities
        graph_context: Results from graph retrieval
        rule_matches: Knowledge engine rule matches
        vector_results: Results from vector search (optional)
        timestamp: When context was assembled
    """
    query: str
    intent: QueryIntent
    entities: ExtractedEntities
    graph_context: GraphContext
    rule_matches: List[RuleMatch] = field(default_factory=list)
    vector_results: List[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def has_data(self) -> bool:
        """Check if context has any data."""
        return (
            not self.graph_context.is_empty() or
            len(self.rule_matches) > 0 or
            len(self.vector_results) > 0
        )
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "intent": self.intent.value,
            "entities": self.entities.to_dict(),
            "graph_context": self.graph_context.to_dict(),
            "rule_matches": [m.to_dict() for m in self.rule_matches],
            "vector_results": self.vector_results,
            "timestamp": self.timestamp,
        }


class ContextAssembler:
    """
    Assembles context from multiple retrieval sources.
    """
    
    # Templates for different intents
    CONTEXT_TEMPLATES: ClassVar[Dict[QueryIntent, str]] = {
        QueryIntent.CURRENT_RANK: """
## 현재 순위 정보
{graph_data}

## 관련 인사이트
{insights}
""",
        QueryIntent.RANK_HISTORY: """
## 순위 히스토리
{graph_data}

## 트렌드 분석
{insights}
""",
        QueryIntent.RANK_CHANGE: """
## 순위 변동 정보
{graph_data}

## 주요 변동 사항
{insights}
""",
        QueryIntent.TOP_N: """
## 카테고리 랭킹
{graph_data}
""",
        QueryIntent.COMPARISON: """
## 경쟁 분석
{graph_data}

## 포지션 인사이트
{insights}
""",
        QueryIntent.TREND: """
## 트렌드 분석
{graph_data}

## 인사이트
{insights}
""",
        QueryIntent.PRODUCT_INFO: """
## 제품 정보
{graph_data}
""",
        QueryIntent.PRODUCT_SEARCH: """
## 검색 결과
{graph_data}
""",
        QueryIntent.GENERAL: """
## 관련 정보
{graph_data}

{insights}
""",
    }
    
    def __init__(
        self,
        knowledge_engine: Optional[KnowledgeEngine] = None,
        include_evidence: bool = True,
        max_results: int = 10,
    ):
        """
        Initialize the context assembler.
        
        Args:
            knowledge_engine: KnowledgeEngine instance for rule matching
            include_evidence: Whether to include evidence in context
            max_results: Maximum results to include per section
        """
        self.knowledge_engine = knowledge_engine
        self.include_evidence = include_evidence
        self.max_results = max_results
        
        logger.debug("ContextAssembler initialized")
    
    def assemble(
        self,
        query: str,
        entities: ExtractedEntities,
        graph_context: GraphContext,
        rank_history: Optional[List[dict]] = None,
        vector_results: Optional[List[dict]] = None,
    ) -> RAGContext:
        """
        Assemble RAG context from retrieval results.
        
        Args:
            query: Original user query
            entities: Extracted entities
            graph_context: Graph retrieval results
            rank_history: Full ranking history for rule matching
            vector_results: Vector search results (optional)
            
        Returns:
            Assembled RAGContext
        """
        # Get knowledge engine matches
        rule_matches = []
        if self.knowledge_engine and rank_history:
            all_matches = self.knowledge_engine.evaluate_all(rank_history)
            
            # Filter matches relevant to query entities
            rule_matches = self._filter_relevant_matches(
                all_matches, entities
            )
        
        context = RAGContext(
            query=query,
            intent=entities.intent,
            entities=entities,
            graph_context=graph_context,
            rule_matches=rule_matches,
            vector_results=vector_results or [],
        )
        
        logger.debug(
            f"Context assembled: {len(graph_context.results)} graph results, "
            f"{len(rule_matches)} rule matches"
        )
        
        return context
    
    def _filter_relevant_matches(
        self,
        matches: List[RuleMatch],
        entities: ExtractedEntities,
    ) -> List[RuleMatch]:
        """Filter rule matches relevant to the query entities."""
        if not entities.has_entities():
            # Return top matches if no specific entities
            return matches[:self.max_results]
        
        relevant = []
        
        for match in matches:
            # Check brand match
            if entities.brands:
                product_name_lower = match.product_name.lower()
                if any(brand.lower() in product_name_lower for brand in entities.brands):
                    relevant.append(match)
                    continue
            
            # Check product name match
            if entities.products:
                for product_keyword in entities.products:
                    if product_keyword.lower() in match.product_name.lower():
                        relevant.append(match)
                        break
            
            # Check category match
            if entities.categories:
                if match.category_key in entities.categories:
                    relevant.append(match)
        
        return relevant[:self.max_results]
    
    def format_for_prompt(self, context: RAGContext) -> str:
        """
        Format context for LLM prompt.
        
        Args:
            context: Assembled RAG context
            
        Returns:
            Formatted context string
        """
        template = self.CONTEXT_TEMPLATES.get(
            context.intent,
            self.CONTEXT_TEMPLATES[QueryIntent.GENERAL]
        )
        
        # Format graph data
        graph_data = self._format_graph_data(context)
        
        # Format insights
        insights = self._format_insights(context)
        
        # Combine
        formatted = template.format(
            graph_data=graph_data,
            insights=insights,
        )
        
        # Add vector results if available
        if context.vector_results:
            formatted += "\n## 관련 문서\n"
            formatted += self._format_vector_results(context.vector_results)
        
        return formatted.strip()
    
    def _format_graph_data(self, context: RAGContext) -> str:
        """Format graph context data."""
        if context.graph_context.is_empty():
            return "데이터를 찾을 수 없습니다."
        
        results = context.graph_context.results[:self.max_results]
        intent = context.intent
        
        lines = []
        
        if intent == QueryIntent.CURRENT_RANK:
            for r in results:
                lines.append(
                    f"- **{r.get('product_name', 'Unknown')}** "
                    f"({r.get('brand', '-')}): "
                    f"**{r.get('rank')}위** "
                    f"({r.get('market', '-')}, {r.get('date', '-')})"
                )
        
        elif intent in [QueryIntent.RANK_HISTORY, QueryIntent.RANK_CHANGE, QueryIntent.TREND]:
            for r in results:
                lines.append(f"### {r.get('product_name', 'Unknown')}")
                lines.append(f"- 브랜드: {r.get('brand', '-')}")
                lines.append(f"- 현재 순위: {r.get('current_rank', '-')}위")
                lines.append(f"- 순위 변동: {r.get('rank_change', 0):+d}")
                lines.append(f"- 추세: {r.get('trend', 'stable')}")
                
                if "trend_analysis" in r:
                    ta = r["trend_analysis"]
                    lines.append(f"- 평균 순위: {ta.get('avg_rank', 0):.1f}")
                    lines.append(f"- 최고 순위: {ta.get('best_rank', '-')}위")
                    lines.append(f"- 변동폭: {ta.get('volatility', 0)}")
                
                # Show recent history
                history = r.get("history", [])[-5:]  # Last 5 entries
                if history:
                    lines.append("- 최근 순위:")
                    for h in history:
                        lines.append(f"  - {h.get('date')}: {h.get('rank')}위")
                lines.append("")
        
        elif intent == QueryIntent.TOP_N:
            for r in results:
                lines.append(
                    f"{r.get('rank')}. **{r.get('product_name', 'Unknown')}** "
                    f"({r.get('brand', '-')})"
                )
        
        elif intent == QueryIntent.COMPARISON:
            for r in results:
                main = r.get("main_product", {})
                lines.append(f"### {main.get('name', 'Unknown')}")
                lines.append(f"- 현재 순위: {main.get('current_rank', '-')}위")
                lines.append("- 경쟁 제품:")
                
                for comp in r.get("competitors", [])[:5]:
                    lines.append(
                        f"  - {comp.get('name')}: {comp.get('rank')}위"
                    )
                lines.append("")
        
        elif intent == QueryIntent.PRODUCT_INFO:
            for r in results:
                product = r.get("product", {})
                lines.append(f"### {product.get('product_name_raw', 'Unknown')}")
                lines.append(f"- 브랜드: {product.get('brand', '-')}")
                lines.append(f"- 처음 등장: {r.get('first_seen', '-')}")
                lines.append(f"- 마지막 확인: {r.get('last_seen', '-')}")
                lines.append(f"- 현재 순위: {r.get('current_rank', '-')}위")
                lines.append("")
        
        elif intent == QueryIntent.PRODUCT_SEARCH:
            for r in results:
                lines.append(
                    f"- **{r.get('product_name_raw', 'Unknown')}** "
                    f"({r.get('brand', '-')})"
                )
        
        else:
            # General formatting
            for r in results:
                lines.append(f"- {json.dumps(r, ensure_ascii=False)}")
        
        return "\n".join(lines) if lines else "데이터 없음"
    
    def _format_insights(self, context: RAGContext) -> str:
        """Format rule match insights."""
        if not context.rule_matches:
            return ""
        
        lines = []
        
        # Group by tag
        by_tag: Dict[str, List[RuleMatch]] = {}
        for match in context.rule_matches:
            if match.tag not in by_tag:
                by_tag[match.tag] = []
            by_tag[match.tag].append(match)
        
        for tag, matches in by_tag.items():
            lines.append(f"### {tag.replace('_', ' ').title()}")
            for match in matches[:3]:  # Max 3 per tag
                lines.append(f"- {match.message}")
                
                if self.include_evidence and match.evidence:
                    evidence_items = []
                    for k, v in list(match.evidence.items())[:3]:
                        evidence_items.append(f"{k}: {v}")
                    if evidence_items:
                        lines.append(f"  - 근거: {', '.join(evidence_items)}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_vector_results(self, results: List[dict]) -> str:
        """Format vector search results."""
        lines = []
        
        for i, result in enumerate(results[:3], 1):
            doc = result.get("document", "")
            metadata = result.get("metadata", {})
            
            lines.append(f"{i}. {doc[:200]}...")
            if metadata:
                lines.append(f"   - 출처: {metadata.get('source', '-')}")
        
        return "\n".join(lines)
    
    def generate_answer_template(self, context: RAGContext) -> str:
        """
        Generate a template answer based on context.
        
        This provides a structured response without LLM,
        useful for testing or when LLM is not available.
        """
        intent = context.intent
        results = context.graph_context.results
        
        if not results:
            return f"'{context.query}'에 대한 정보를 찾을 수 없습니다."
        
        if intent == QueryIntent.CURRENT_RANK:
            answers = []
            for r in results[:3]:
                answers.append(
                    f"{r.get('product_name', 'Unknown')}은(는) "
                    f"{r.get('market', '-')} {r.get('category_key', '-')} 카테고리에서 "
                    f"현재 **{r.get('rank')}위**입니다. "
                    f"({r.get('date')} 기준)"
                )
            return "\n\n".join(answers)
        
        elif intent == QueryIntent.RANK_HISTORY:
            answers = []
            for r in results[:2]:
                change = r.get("rank_change", 0)
                trend = r.get("trend", "stable")
                
                trend_desc = {
                    "rising": "상승세",
                    "falling": "하락세",
                    "stable": "안정세"
                }.get(trend, "안정세")
                
                answers.append(
                    f"{r.get('product_name', 'Unknown')}의 순위 추이:\n"
                    f"- 현재 순위: {r.get('current_rank', '-')}위\n"
                    f"- 순위 변동: {change:+d}\n"
                    f"- 전체 추세: {trend_desc}"
                )
            return "\n\n".join(answers)
        
        elif intent == QueryIntent.TOP_N:
            top_n = context.entities.top_n or 10
            category = results[0].get("category_key", "카테고리") if results else "카테고리"
            
            lines = [f"**{category} Top {min(len(results), top_n)}**\n"]
            for r in results[:top_n]:
                lines.append(
                    f"{r.get('rank')}위: {r.get('product_name')} ({r.get('brand', '-')})"
                )
            return "\n".join(lines)
        
        elif intent == QueryIntent.COMPARISON:
            if results:
                r = results[0]
                main = r.get("main_product", {})
                comps = r.get("competitors", [])[:5]
                
                lines = [
                    f"**{main.get('name')}** vs 경쟁 제품\n",
                    f"- 현재 순위: {main.get('current_rank')}위\n",
                    "- 경쟁 현황:",
                ]
                for comp in comps:
                    rank_diff = comp.get("rank", 0) - main.get("current_rank", 0)
                    lines.append(
                        f"  - {comp.get('name')}: {comp.get('rank')}위 "
                        f"({rank_diff:+d})"
                    )
                return "\n".join(lines)
        
        # Default response
        return self.format_for_prompt(context)
