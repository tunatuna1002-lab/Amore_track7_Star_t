"""
Knowledge Rule Engine for ranking insights.

Implements rule-based inference engine that:
- Loads rules from YAML configuration
- Evaluates rules against ranking data
- Generates tagged insights with evidence
- Supports rule chaining and conflict resolution

Rules are defined in docs/knowledge_rules.yaml

Implemented Rules (Phase 1):
- R001: Stable Leader (Top5 연속 7일+)
- R002: Rising Star (순위 10↑ 상승)
- R003: At Risk (순위 10↓ 하락)
- R004: New Entrant (신규 진입)
- R005: Recent Exit (최근 이탈)

Future Rules (Phase 2):
- R006: Global Hit (Amazon + @cosme 동시 Top 10)
- R007: Successful Launch (출시 30일 내 Top 100)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Any, Callable

import yaml

from .streak_analyzer import StreakAnalyzer, StreakInfo
from .shock_detector import ShockDetector, RankShock
from .entry_exit_tracker import EntryExitTracker, EntryEvent, ExitEvent

logger = logging.getLogger(__name__)


class RuleCategory(str, Enum):
    """Categories of knowledge rules."""
    STREAK = "streak"
    SHOCK = "shock"
    ENTRY = "entry"
    EXIT = "exit"
    CROSS_MARKET = "cross_market"
    LAUNCH = "launch"
    ALERT = "alert"


class Confidence(str, Enum):
    """Confidence levels for rule matches."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RuleMatch:
    """
    Represents a rule match with evidence.
    
    Attributes:
        rule_id: Rule identifier (e.g., "R001")
        rule_name: Human-readable name
        tag: Classification tag (e.g., "stable_leader")
        confidence: Confidence level
        product_name: Product name
        product_url: Product URL
        market: Market identifier
        category_key: Category identifier
        message: Generated message
        evidence: Dictionary of evidence fields
        matched_at: When the rule was matched
    """
    rule_id: str
    rule_name: str
    tag: str
    confidence: Confidence
    product_name: str
    product_url: str
    market: str
    category_key: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    matched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "tag": self.tag,
            "confidence": self.confidence.value,
            "product_name": self.product_name,
            "product_url": self.product_url,
            "market": self.market,
            "category_key": self.category_key,
            "message": self.message,
            "evidence": self.evidence,
            "matched_at": self.matched_at,
        }


@dataclass
class RuleDefinition:
    """
    Definition of a knowledge rule.
    
    Attributes:
        rule_id: Unique identifier
        name: Human-readable name
        description: Rule description
        category: Rule category
        priority: Execution priority (1=highest)
        condition: Condition expression
        parameters: Rule parameters
        output_tag: Tag to apply on match
        confidence: Confidence level on match
        message_template: Template for generating message
        evidence_fields: Fields to include as evidence
        enabled: Whether rule is active
    """
    rule_id: str
    name: str
    description: str
    category: RuleCategory
    priority: int
    condition: str
    parameters: Dict[str, Any]
    output_tag: str
    confidence: Confidence
    message_template: str
    evidence_fields: List[str]
    enabled: bool = True
    
    @classmethod
    def from_yaml(cls, rule_id: str, data: dict) -> "RuleDefinition":
        """Create RuleDefinition from YAML data."""
        return cls(
            rule_id=rule_id,
            name=data.get("name", rule_id),
            description=data.get("description", ""),
            category=RuleCategory(data.get("category", "streak")),
            priority=data.get("priority", 5),
            condition=data.get("expression", ""),
            parameters=data.get("condition", {}).get("parameters", {}),
            output_tag=data.get("output", {}).get("tag", rule_id),
            confidence=Confidence(data.get("output", {}).get("confidence", "medium")),
            message_template=data.get("output", {}).get("message_template", ""),
            evidence_fields=data.get("evidence_fields", []),
            enabled=data.get("enabled", True),
        )


class KnowledgeEngine:
    """
    Rule-based inference engine for ranking insights.
    
    Integrates with existing insight modules and provides unified
    rule evaluation and tagging.
    """
    
    # Default rule definitions (embedded for standalone use)
    DEFAULT_RULES: ClassVar[Dict[str, dict]] = {
        "R001_stable_leader": {
            "name": "Stable Leader",
            "description": "TopN에서 연속 N일 이상 유지하는 제품",
            "category": "streak",
            "priority": 1,
            "expression": "rank <= {top_n_threshold} AND consecutive_days >= {min_consecutive_days}",
            "condition": {
                "type": "streak",
                "parameters": {
                    "top_n_threshold": 5,
                    "min_consecutive_days": 7,
                }
            },
            "output": {
                "tag": "stable_leader",
                "confidence": "high",
                "message_template": "{product_name}은(는) {category_key}에서 Top {top_n_threshold}을 {streak_days}일 연속 유지 중입니다."
            },
            "evidence_fields": ["streak_days", "streak_start", "streak_end", "current_rank"]
        },
        "R002_rising_star": {
            "name": "Rising Star",
            "description": "순위가 급격히 상승한 제품",
            "category": "shock",
            "priority": 2,
            "expression": "rank_change >= {min_improvement}",
            "condition": {
                "type": "shock",
                "parameters": {
                    "min_improvement": 10,
                }
            },
            "output": {
                "tag": "rising_star",
                "confidence": "medium",
                "message_template": "{product_name}이(가) {previous_rank}위에서 {new_rank}위로 {change}순위 상승!"
            },
            "evidence_fields": ["previous_rank", "new_rank", "change", "date"]
        },
        "R003_at_risk": {
            "name": "At Risk",
            "description": "순위가 급격히 하락한 제품",
            "category": "shock",
            "priority": 2,
            "expression": "rank_change <= {min_drop}",
            "condition": {
                "type": "shock",
                "parameters": {
                    "min_drop": -10,
                }
            },
            "output": {
                "tag": "at_risk",
                "confidence": "medium",
                "message_template": "⚠️ {product_name}이(가) {previous_rank}위에서 {new_rank}위로 {change}순위 하락"
            },
            "evidence_fields": ["previous_rank", "new_rank", "change", "date"]
        },
        "R004_new_entrant": {
            "name": "New Entrant",
            "description": "lookback 기간 내 TopN에 처음 진입한 제품",
            "category": "entry",
            "priority": 3,
            "expression": "first_in_top_n >= (today - {lookback_days})",
            "condition": {
                "type": "entry",
                "parameters": {
                    "top_n_threshold": 100,
                    "lookback_days": 7,
                }
            },
            "output": {
                "tag": "new_entrant",
                "confidence": "high",
                "message_template": "🆕 {product_name}이(가) {entry_date}에 Top {top_n_threshold}에 {entry_rank}위로 신규 진입!"
            },
            "evidence_fields": ["entry_date", "entry_rank", "top_n_threshold", "current_rank"]
        },
        "R005_recent_exit": {
            "name": "Recent Exit",
            "description": "lookback 기간 내 TopN에서 이탈한 제품",
            "category": "exit",
            "priority": 3,
            "expression": "last_in_top_n <= (today - 1) AND >= (today - {lookback_days})",
            "condition": {
                "type": "exit",
                "parameters": {
                    "top_n_threshold": 100,
                    "lookback_days": 7,
                }
            },
            "output": {
                "tag": "recent_exit",
                "confidence": "high",
                "message_template": "📤 {product_name}이(가) Top {top_n_threshold}에서 이탈 (마지막: {last_rank_in_top_n}위, 체류: {days_in_top_n}일)"
            },
            "evidence_fields": ["exit_date", "last_rank_in_top_n", "days_in_top_n"]
        },
    }
    
    def __init__(
        self,
        rules_file: Optional[str] = None,
        streak_thresholds: List[int] = None,
        shock_threshold: int = 3,
        lookback_days: int = 7
    ):
        """
        Initialize the knowledge engine.
        
        Args:
            rules_file: Path to YAML rules file (optional)
            streak_thresholds: TopN thresholds for streak analysis
            shock_threshold: Minimum rank change for shock detection
            lookback_days: Days to look back for entry/exit
        """
        self.streak_thresholds = streak_thresholds or [5, 10, 100]
        self.shock_threshold = shock_threshold
        self.lookback_days = lookback_days
        
        # Load rules
        self.rules: Dict[str, RuleDefinition] = {}
        self._load_rules(rules_file)
        
        # Initialize insight analyzers
        self.streak_analyzer = StreakAnalyzer(top_n_thresholds=self.streak_thresholds)
        self.shock_detector = ShockDetector(threshold=self.shock_threshold)
        self.entry_exit_tracker = EntryExitTracker(
            top_n_thresholds=self.streak_thresholds,
            lookback_days=self.lookback_days
        )
        
        logger.info(f"KnowledgeEngine initialized with {len(self.rules)} rules")
    
    def _load_rules(self, rules_file: Optional[str]):
        """Load rules from YAML file or use defaults."""
        if rules_file:
            path = Path(rules_file)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    
                classification_rules = data.get("classification_rules", {})
                for rule_id, rule_data in classification_rules.items():
                    self.rules[rule_id] = RuleDefinition.from_yaml(rule_id, rule_data)
                
                logger.debug(f"Loaded {len(self.rules)} rules from {rules_file}")
                return
        
        # Use embedded default rules
        for rule_id, rule_data in self.DEFAULT_RULES.items():
            self.rules[rule_id] = RuleDefinition.from_yaml(rule_id, rule_data)
        
        logger.debug(f"Using {len(self.rules)} default rules")
    
    def evaluate_all(self, rank_history: List[dict]) -> List[RuleMatch]:
        """
        Evaluate all rules against ranking history.
        
        Args:
            rank_history: List of ranking dictionaries from storage
            
        Returns:
            List of RuleMatch objects sorted by priority
        """
        if not rank_history:
            return []
        
        matches = []
        
        # Run streak analysis
        matches.extend(self._evaluate_streak_rules(rank_history))
        
        # Run shock detection
        matches.extend(self._evaluate_shock_rules(rank_history))
        
        # Run entry/exit tracking
        matches.extend(self._evaluate_entry_exit_rules(rank_history))
        
        # Sort by priority (lower = higher priority)
        matches.sort(key=lambda m: self.rules.get(m.rule_id, RuleDefinition(
            rule_id="", name="", description="", category=RuleCategory.STREAK,
            priority=99, condition="", parameters={}, output_tag="",
            confidence=Confidence.LOW, message_template="", evidence_fields=[]
        )).priority)
        
        logger.info(f"Found {len(matches)} rule matches")
        return matches
    
    def _evaluate_streak_rules(self, rank_history: List[dict]) -> List[RuleMatch]:
        """Evaluate streak-related rules."""
        matches = []
        
        # Get rule definition
        rule = self.rules.get("R001_stable_leader")
        if not rule or not rule.enabled:
            return matches
        
        # Run analyzer
        streaks = self.streak_analyzer.analyze(rank_history)
        
        # Filter by rule parameters
        min_days = rule.parameters.get("min_consecutive_days", 7)
        top_n = rule.parameters.get("top_n_threshold", 5)
        
        for streak in streaks:
            if streak.streak_days >= min_days and streak.top_n_threshold <= top_n:
                # Create evidence
                evidence = {
                    "streak_days": streak.streak_days,
                    "streak_start": streak.streak_start,
                    "streak_end": streak.streak_end,
                    "current_rank": streak.current_rank,
                    "top_n_threshold": streak.top_n_threshold,
                    "is_active": streak.is_active,
                }
                
                # Generate message
                message = rule.message_template.format(
                    product_name=streak.product_name,
                    category_key=streak.category_key,
                    top_n_threshold=streak.top_n_threshold,
                    streak_days=streak.streak_days,
                )
                
                matches.append(RuleMatch(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    tag=rule.output_tag,
                    confidence=rule.confidence,
                    product_name=streak.product_name,
                    product_url=streak.product_url,
                    market=streak.market,
                    category_key=streak.category_key,
                    message=message,
                    evidence=evidence,
                ))
        
        return matches
    
    def _evaluate_shock_rules(self, rank_history: List[dict]) -> List[RuleMatch]:
        """Evaluate shock-related rules (rising star, at risk)."""
        matches = []
        
        # Run shock detector
        shocks = self.shock_detector.detect(rank_history)
        
        # Rising Star (R002)
        rising_rule = self.rules.get("R002_rising_star")
        if rising_rule and rising_rule.enabled:
            min_improvement = rising_rule.parameters.get("min_improvement", 10)
            
            for shock in shocks:
                if shock.change >= min_improvement:
                    evidence = {
                        "previous_rank": shock.previous_rank,
                        "new_rank": shock.new_rank,
                        "change": shock.change,
                        "date": shock.date,
                        "previous_date": shock.previous_date,
                    }
                    
                    message = rising_rule.message_template.format(
                        product_name=shock.product_name,
                        previous_rank=shock.previous_rank,
                        new_rank=shock.new_rank,
                        change=shock.change,
                    )
                    
                    matches.append(RuleMatch(
                        rule_id=rising_rule.rule_id,
                        rule_name=rising_rule.name,
                        tag=rising_rule.output_tag,
                        confidence=rising_rule.confidence,
                        product_name=shock.product_name,
                        product_url=shock.product_url,
                        market=shock.market,
                        category_key=shock.category_key,
                        message=message,
                        evidence=evidence,
                    ))
        
        # At Risk (R003)
        risk_rule = self.rules.get("R003_at_risk")
        if risk_rule and risk_rule.enabled:
            min_drop = risk_rule.parameters.get("min_drop", -10)
            
            for shock in shocks:
                if shock.change <= min_drop:
                    evidence = {
                        "previous_rank": shock.previous_rank,
                        "new_rank": shock.new_rank,
                        "change": shock.change,
                        "date": shock.date,
                    }
                    
                    message = risk_rule.message_template.format(
                        product_name=shock.product_name,
                        previous_rank=shock.previous_rank,
                        new_rank=shock.new_rank,
                        change=abs(shock.change),
                    )
                    
                    matches.append(RuleMatch(
                        rule_id=risk_rule.rule_id,
                        rule_name=risk_rule.name,
                        tag=risk_rule.output_tag,
                        confidence=risk_rule.confidence,
                        product_name=shock.product_name,
                        product_url=shock.product_url,
                        market=shock.market,
                        category_key=shock.category_key,
                        message=message,
                        evidence=evidence,
                    ))
        
        return matches
    
    def _evaluate_entry_exit_rules(self, rank_history: List[dict]) -> List[RuleMatch]:
        """Evaluate entry/exit rules."""
        matches = []
        
        # New Entrant (R004)
        entry_rule = self.rules.get("R004_new_entrant")
        if entry_rule and entry_rule.enabled:
            entries = self.entry_exit_tracker.find_new_entries(rank_history)
            
            for entry in entries:
                evidence = {
                    "entry_date": entry.entry_date,
                    "entry_rank": entry.entry_rank,
                    "top_n_threshold": entry.top_n_threshold,
                    "current_rank": entry.current_rank,
                }
                
                message = entry_rule.message_template.format(
                    product_name=entry.product_name,
                    entry_date=entry.entry_date,
                    top_n_threshold=entry.top_n_threshold,
                    entry_rank=entry.entry_rank,
                )
                
                matches.append(RuleMatch(
                    rule_id=entry_rule.rule_id,
                    rule_name=entry_rule.name,
                    tag=entry_rule.output_tag,
                    confidence=entry_rule.confidence,
                    product_name=entry.product_name,
                    product_url=entry.product_url,
                    market=entry.market,
                    category_key=entry.category_key,
                    message=message,
                    evidence=evidence,
                ))
        
        # Recent Exit (R005)
        exit_rule = self.rules.get("R005_recent_exit")
        if exit_rule and exit_rule.enabled:
            exits = self.entry_exit_tracker.find_exits(rank_history)
            
            for exit_event in exits:
                evidence = {
                    "exit_date": exit_event.exit_date,
                    "last_rank_in_top_n": exit_event.last_rank_in_top_n,
                    "days_in_top_n": exit_event.days_in_top_n,
                    "top_n_threshold": exit_event.top_n_threshold,
                }
                
                message = exit_rule.message_template.format(
                    product_name=exit_event.product_name,
                    top_n_threshold=exit_event.top_n_threshold,
                    last_rank_in_top_n=exit_event.last_rank_in_top_n,
                    days_in_top_n=exit_event.days_in_top_n,
                )
                
                matches.append(RuleMatch(
                    rule_id=exit_rule.rule_id,
                    rule_name=exit_rule.name,
                    tag=exit_rule.output_tag,
                    confidence=exit_rule.confidence,
                    product_name=exit_event.product_name,
                    product_url=exit_event.product_url,
                    market=exit_event.market,
                    category_key=exit_event.category_key,
                    message=message,
                    evidence=evidence,
                ))
        
        return matches
    
    def get_matches_by_tag(self, matches: List[RuleMatch], tag: str) -> List[RuleMatch]:
        """Filter matches by tag."""
        return [m for m in matches if m.tag == tag]
    
    def get_matches_by_product(self, matches: List[RuleMatch], product_url: str) -> List[RuleMatch]:
        """Filter matches by product URL."""
        return [m for m in matches if m.product_url == product_url]
    
    def get_matches_by_brand(self, matches: List[RuleMatch], brand_name: str) -> List[RuleMatch]:
        """Filter matches by brand name (case-insensitive partial match)."""
        brand_lower = brand_name.lower()
        return [m for m in matches if brand_lower in m.product_name.lower()]
    
    def generate_report(self, matches: List[RuleMatch]) -> str:
        """
        Generate a text report from rule matches.
        
        Args:
            matches: List of RuleMatch objects
            
        Returns:
            Formatted report string
        """
        if not matches:
            return "No rule matches found."
        
        lines = [
            "=" * 60,
            "Knowledge Rule Engine Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Matches: {len(matches)}",
            "=" * 60,
            "",
        ]
        
        # Group by tag
        by_tag: Dict[str, List[RuleMatch]] = {}
        for match in matches:
            if match.tag not in by_tag:
                by_tag[match.tag] = []
            by_tag[match.tag].append(match)
        
        for tag, tag_matches in by_tag.items():
            lines.append(f"## {tag.upper()} ({len(tag_matches)} matches)")
            lines.append("-" * 40)
            
            for match in tag_matches:
                lines.append(f"  • {match.message}")
                lines.append(f"    Market: {match.market} | Category: {match.category_key}")
                lines.append("")
            
            lines.append("")
        
        return "\n".join(lines)
