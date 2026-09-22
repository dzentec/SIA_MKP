"""Acceptance and Quality Metrics Dataclasses (REQ-QA-02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QAEvaluationResults:
    """Comprehensive QA benchmark score card."""
    total_questions: int = 0
    search_recall_at_1: float = 0.0
    search_recall_at_3: float = 0.0
    search_recall_at_5: float = 0.0
    term_precision: float = 0.0
    hallucination_rate: float = 0.0

    total_golden_rules: int = 0
    rule_recall: float = 0.0
    citation_rate: float = 0.0

    total_graph_queries: int = 0
    triplets_accuracy: float = 0.0

    guardrails_length: int = 0
    guardrails_valid: bool = False

    all_invariants_pass: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed_all_acceptance_criteria(self) -> bool:
        """Check if metrics satisfy REQ-QA-02 thresholds."""
        return (
            self.hallucination_rate == 0.0
            and self.rule_recall >= 0.80
            and self.citation_rate >= 0.90
            and self.triplets_accuracy >= 0.90
            and self.guardrails_valid
            and self.guardrails_length <= 8000
            and self.all_invariants_pass
        )
