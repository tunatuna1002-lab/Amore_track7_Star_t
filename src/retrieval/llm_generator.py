"""
LLM Generator for Graph-RAG response generation.

Uses Claude API to generate natural language responses
based on retrieved context from graph and vector search.

Supports:
- Grounded responses with citations
- Multi-language output (Korean/English)
- Evidence-based answers
- Fallback to template responses
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from .context_assembler import RAGContext

logger = logging.getLogger(__name__)

# Optional Anthropic import
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("Anthropic SDK not installed. LLM generation will use templates.")


# =============================================================================
# Prompt Templates
# =============================================================================

SYSTEM_PROMPT_KO = """당신은 라네즈 랭킹 분석 전문가입니다.
주어진 데이터를 기반으로 정확하고 근거있는 답변을 제공합니다.

## 규칙
1. 컨텍스트에 있는 데이터만 사용하여 답변합니다.
2. 출처(날짜, 플랫폼, 카테고리)를 명시합니다.
3. 데이터가 없으면 "해당 정보를 찾을 수 없습니다"라고 답합니다.
4. 한국어로 답변합니다.
5. 간결하고 핵심적인 답변을 제공합니다.
6. 순위 변동이 있으면 인사이트를 추가합니다.

## 응답 형식
- 핵심 답변을 먼저 제시
- 근거 데이터 언급
- 관련 인사이트 추가 (있는 경우)
"""

SYSTEM_PROMPT_EN = """You are a LANEIGE ranking analysis expert.
Provide accurate, evidence-based answers using the given data.

## Rules
1. Use only data from the provided context.
2. Cite sources (dates, platforms, categories).
3. Say "Information not found" if data is unavailable.
4. Respond in English.
5. Keep answers concise and focused.
6. Add insights for ranking changes.

## Response Format
- Lead with the key answer
- Mention supporting data
- Add relevant insights (if available)
"""

USER_PROMPT_TEMPLATE = """## 질문
{query}

## 컨텍스트
{context}

위 컨텍스트를 기반으로 질문에 답변해주세요."""

USER_PROMPT_TEMPLATE_EN = """## Question
{query}

## Context
{context}

Please answer the question based on the context above."""


@dataclass
class LLMConfig:
    """Configuration for LLM generation."""
    model: str = "claude-3-haiku-20240307"
    max_tokens: int = 1024
    temperature: float = 0.3
    language: str = "ko"  # "ko" or "en"
    
    @property
    def system_prompt(self) -> str:
        return SYSTEM_PROMPT_KO if self.language == "ko" else SYSTEM_PROMPT_EN
    
    @property
    def user_template(self) -> str:
        return USER_PROMPT_TEMPLATE if self.language == "ko" else USER_PROMPT_TEMPLATE_EN


@dataclass
class LLMResponse:
    """Response from LLM generation."""
    text: str
    model: str
    tokens_used: int = 0
    generation_time_ms: float = 0.0
    is_fallback: bool = False
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "generation_time_ms": self.generation_time_ms,
            "is_fallback": self.is_fallback,
        }


class LLMGenerator:
    """
    LLM-based response generator using Claude API.
    
    Falls back to template-based generation if API is unavailable.
    """
    
    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the LLM generator.
        
        Args:
            config: LLM configuration
            api_key: Anthropic API key (or from ANTHROPIC_API_KEY env)
        """
        self.config = config or LLMConfig()
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        
        self.client = None
        if ANTHROPIC_AVAILABLE and self.api_key:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info(f"LLMGenerator initialized with model: {self.config.model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")
        else:
            logger.info("LLMGenerator using template fallback (no API)")
    
    def generate(
        self,
        query: str,
        context: RAGContext,
        context_assembler=None,
    ) -> LLMResponse:
        """
        Generate a response for the query.
        
        Args:
            query: User query
            context: RAG context with retrieved data
            context_assembler: Optional ContextAssembler for formatting
            
        Returns:
            LLMResponse with generated text
        """
        start_time = datetime.now()
        
        # Format context for prompt
        if context_assembler:
            formatted_context = context_assembler.format_for_prompt(context)
        else:
            formatted_context = self._format_context(context)
        
        # Try LLM generation
        if self.client:
            try:
                response = self._generate_with_api(query, formatted_context)
                response.generation_time_ms = (
                    datetime.now() - start_time
                ).total_seconds() * 1000
                return response
            except Exception as e:
                logger.exception("LLM generation failed")
        
        # Fallback to template
        response = self._generate_with_template(query, context, context_assembler)
        response.generation_time_ms = (
            datetime.now() - start_time
        ).total_seconds() * 1000
        return response
    
    def _generate_with_api(
        self,
        query: str,
        formatted_context: str,
    ) -> LLMResponse:
        """Generate response using Claude API."""
        user_message = self.config.user_template.format(
            query=query,
            context=formatted_context,
        )
        
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=self.config.system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        
        text = response.content[0].text if response.content else ""
        tokens_used = (
            response.usage.input_tokens + response.usage.output_tokens
            if response.usage else 0
        )
        
        return LLMResponse(
            text=text,
            model=self.config.model,
            tokens_used=tokens_used,
            is_fallback=False,
        )
    
    def _generate_with_template(
        self,
        query: str,
        context: RAGContext,
        context_assembler=None,
    ) -> LLMResponse:
        """Generate response using templates (fallback)."""
        if context_assembler:
            text = context_assembler.generate_answer_template(context)
        else:
            text = self._simple_template_response(query, context)
        
        return LLMResponse(
            text=text,
            model="template",
            tokens_used=0,
            is_fallback=True,
        )
    
    def _format_context(self, context: RAGContext) -> str:
        """Simple context formatting."""
        lines = []
        
        # Graph results
        if context.graph_context.results:
            lines.append("### 그래프 데이터")
            for result in context.graph_context.results[:5]:
                lines.append(f"- {self._format_result(result)}")
        
        # Rule matches
        if context.rule_matches:
            lines.append("\n### 인사이트")
            for match in context.rule_matches[:3]:
                lines.append(f"- [{match.tag}] {match.message}")
        
        # Vector results
        if context.vector_results:
            lines.append("\n### 관련 정보")
            for result in context.vector_results[:3]:
                doc = result.get("document", "")[:200]
                lines.append(f"- {doc}...")
        
        return "\n".join(lines) if lines else "데이터 없음"
    
    def _format_result(self, result: dict) -> str:
        """Format a single result for context."""
        if "product_name" in result:
            return (
                f"{result.get('product_name', 'Unknown')}: "
                f"{result.get('rank', '?')}위 "
                f"({result.get('market', '-')}, {result.get('date', '-')})"
            )
        return str(result)
    
    def _simple_template_response(
        self,
        query: str,
        context: RAGContext,
    ) -> str:
        """Generate simple template response."""
        results = context.graph_context.results
        
        if not results:
            return f"'{query}'에 대한 정보를 찾을 수 없습니다."
        
        # Build response based on results
        lines = []
        for r in results[:3]:
            if "product_name" in r and "rank" in r:
                lines.append(
                    f"**{r.get('product_name')}**: "
                    f"{r.get('rank')}위 "
                    f"({r.get('date', '-')} 기준)"
                )
        
        if lines:
            return "\n".join(lines)
        
        return f"'{query}'에 대한 결과: {len(results)}건의 데이터를 찾았습니다."
    
    @property
    def is_api_available(self) -> bool:
        """Check if API is available."""
        return self.client is not None


class StreamingLLMGenerator(LLMGenerator):
    """
    Streaming version of LLM generator.
    
    Yields tokens as they are generated for real-time display.
    """
    
    def generate_stream(
        self,
        query: str,
        context: RAGContext,
        context_assembler=None,
    ):
        """
        Generate response with streaming.
        
        Yields:
            str: Generated text chunks
        """
        if not self.client:
            # Fallback: yield complete response
            response = self.generate(query, context, context_assembler)
            yield response.text
            return
        
        # Format context
        if context_assembler:
            formatted_context = context_assembler.format_for_prompt(context)
        else:
            formatted_context = self._format_context(context)
        
        user_message = self.config.user_template.format(
            query=query,
            context=formatted_context,
        )
        
        try:
            with self.client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=self.config.system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            ) as stream:
                for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            logger.exception("Streaming generation failed")
            response = self._generate_with_template(query, context, context_assembler)
            yield response.text


# =============================================================================
# Factory Functions
# =============================================================================

def create_llm_generator(
    model: str = "claude-3-haiku-20240307",
    language: str = "ko",
    api_key: Optional[str] = None,
) -> LLMGenerator:
    """
    Create an LLM generator with specified settings.
    
    Args:
        model: Claude model to use
        language: Response language ("ko" or "en")
        api_key: Anthropic API key
        
    Returns:
        Configured LLMGenerator
    """
    config = LLMConfig(
        model=model,
        language=language,
    )
    return LLMGenerator(config=config, api_key=api_key)


def create_generator_function(
    model: str = "claude-3-haiku-20240307",
    language: str = "ko",
    api_key: Optional[str] = None,
) -> Callable[[str, RAGContext], str]:
    """
    Create a generator function for use with RAGPipeline.
    
    Args:
        model: Claude model to use
        language: Response language
        api_key: Anthropic API key
        
    Returns:
        Function that takes (query, context) and returns response text
    """
    generator = create_llm_generator(model, language, api_key)
    
    def generate_fn(query: str, context: RAGContext) -> str:
        response = generator.generate(query, context)
        return response.text
    
    return generate_fn
