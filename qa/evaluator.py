"""End-to-End QA Evaluator and Benchmark Engine (REQ-QA-02)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from qa.corpus_fixture import load_golden_dataset, load_golden_rules
from qa.metrics import QAEvaluationResults
from mkp_server.server import MKPServerEngine

logger = logging.getLogger(__name__)


class QAEvaluator:
    """Runs automated benchmarks over MKPServerEngine against Golden Ground Truth."""

    def __init__(self, engine: MKPServerEngine, qa_dir: Path | str | None = None):
        self.engine = engine
        self.qa_dir = Path(qa_dir) if qa_dir else Path(__file__).parent
        self.dataset = load_golden_dataset(self.qa_dir)
        self.golden_rules = load_golden_rules(self.qa_dir)

    def evaluate_all(self, invariants_pass: bool = True) -> QAEvaluationResults:
        """Run all evaluation suites and compute comprehensive metrics."""
        res = QAEvaluationResults(
            total_questions=len(self.dataset),
            total_golden_rules=len(self.golden_rules),
            all_invariants_pass=invariants_pass,
        )

        # 1. Search Chunks Benchmark (30 questions)
        r1_hits = 0
        r3_hits = 0
        r5_hits = 0
        term_precision_accum = 0.0
        hallucination_count = 0

        for q in self.dataset:
            query = q["query"]
            exp_book = q["expected_book"]
            exp_page = q["expected_page"]
            must_terms = [t.lower() for t in q.get("must_contain_terms", [])]

            # Query server tool
            search_res = self.engine.search_chunks(query, top_k=5)

            if not search_res:
                hallucination_count += 1
                continue

            # Check if any result hallucinated non-existing book
            for item in search_res:
                if item.get("book_id") not in ("dedekam_sail_trim", "dedekam_seamanship"):
                    hallucination_count += 1

            # Recall@K
            books_pages = [(item.get("book_id"), item.get("page_number")) for item in search_res]
            target = (exp_book, exp_page)

            if target in books_pages[:1]:
                r1_hits += 1
            if target in books_pages[:3]:
                r3_hits += 1
            if target in books_pages[:5]:
                r5_hits += 1

            # Term precision on top 1 result
            top_text = search_res[0].get("text_content", "").lower()
            matched_terms = sum(1 for t in must_terms if t in top_text)
            term_prec = matched_terms / len(must_terms) if must_terms else 1.0
            term_precision_accum += term_prec

        n_q = len(self.dataset)
        if n_q > 0:
            res.search_recall_at_1 = r1_hits / n_q
            res.search_recall_at_3 = r3_hits / n_q
            res.search_recall_at_5 = r5_hits / n_q
            res.term_precision = term_precision_accum / n_q
            res.hallucination_rate = hallucination_count / n_q

        # 2. Rules Evaluation (Scenario battery & citations)
        test_scenarios = [
            {"archetype": "all_monohulls", "telemetry": {"tws": 19.0}, "expected": "RULE_REEF_001_FIRST_REEF"},
            {"archetype": "all_monohulls", "telemetry": {"tws": 23.0}, "expected": "RULE_REEF_002_SECOND_REEF"},
            {"archetype": "all_monohulls", "telemetry": {"tws": 29.0}, "expected": "RULE_REEF_003_THIRD_REEF"},
            {"archetype": "all_monohulls", "telemetry": {"heel": 21.0}, "expected": "RULE_SAFETY_001_HEEL_LIMIT"},
            {"archetype": "cruising_catamaran", "telemetry": {"heel": 6.0}, "expected": "RULE_SAFETY_007_CATAMARAN_HEEL_LIMIT"},
            {"archetype": "cruising_catamaran", "telemetry": {"tws": 17.0}, "expected": "RULE_REEF_004_CATAMARAN_EARLY_REEF"},
            {"archetype": "all_monohulls", "telemetry": {"tws": 36.0}, "expected": "RULE_SAFETY_006_HEAVE_TO_HEAVY_WEATHER"},
            {"archetype": "all_monohulls", "telemetry": {"tws": 16.0}, "expected": "RULE_TRIM_002_FLATTEN_MAIN_BREEZE"},
        ]

        rule_hits = 0
        for sc in test_scenarios:
            q_rules = self.engine.query_rules(
                archetype=sc["archetype"],
                telemetry=sc["telemetry"],
            )
            q_ids = [r.get("rule_id") for r in q_rules]
            if sc["expected"] in q_ids:
                rule_hits += 1

        res.rule_recall = rule_hits / len(test_scenarios) if test_scenarios else 0.0

        # Citation rate: rules with non-empty verbatim quotes
        active_rules = self.engine.rules_store.rules.values()
        valid_citations = 0
        for r in active_rules:
            if r.sources and any(len(s.quote) > 10 for s in r.sources):
                valid_citations += 1

        res.citation_rate = valid_citations / len(active_rules) if active_rules else 0.0

        # 3. Triplets Graph Evaluation
        graph_questions = [q for q in self.dataset if q.get("expected_triples")]
        res.total_graph_queries = len(graph_questions)
        graph_hits = 0

        for gq in graph_questions:
            for exp_tr in gq["expected_triples"]:
                subj, pred, obj = exp_tr
                entities = self.engine.get_related_entities(subj)
                matched = any(
                    (e.get("predicate") == pred and e.get("object") == obj) or (e.get("subject") == obj)
                    for e in entities
                )
                if matched:
                    graph_hits += 1
                    break

        res.triplets_accuracy = graph_hits / len(graph_questions) if graph_questions else 1.0

        # 4. Guardrails Check
        guardrails_str = self.engine.get_guardrails()
        res.guardrails_length = len(guardrails_str)
        res.guardrails_valid = 0 < len(guardrails_str) <= 8000

        return res
