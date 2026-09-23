"""Tests for MKP-R Full Evaluation Spec v1.1 Dataset, Rubrics and Configuration (Task 5.1)."""

import json
from pathlib import Path
import pytest
from pydantic import BaseModel, Field

from qa.rubrics import (
    score_m1_faithfulness,
    score_m2_citation,
    score_m3_rule_recall,
    score_m4_cross_domain,
    evaluate_refusal,
    evaluate_guardrails,
    RUBRIC_M4_CROSS_DOMAIN,
    RUBRIC_M1_FAITHFULNESS,
)


class EvalQuestionSchema(BaseModel):
    id: str
    block: str
    query: str
    lang: str
    query_type: str
    expected_book: str
    expected_page: int
    expected_location_ref: str
    must_contain_terms: list[str]
    is_negative: bool = False
    is_adversarial: bool = False
    is_guardrail: bool = False
    is_deferred: bool = False


def test_eval_dataset_schema_and_integrity():
    """Verify that golden_full_dataset.json is valid against the Pydantic schema."""
    ds_path = Path("qa/golden_full_dataset.json")
    assert ds_path.exists(), "golden_full_dataset.json must exist"

    with open(ds_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 114, f"Expected 114 total questions, got {len(data)}"

    seen_ids = set()
    block_counts = {}

    for item in data:
        # Validate schema
        validated = EvalQuestionSchema.model_validate(item)
        assert validated.id not in seen_ids, f"Duplicate ID: {validated.id}"
        seen_ids.add(validated.id)

        block_counts[validated.block] = block_counts.get(validated.block, 0) + 1

    # Verify block distribution per spec v1.1 §5.1
    assert block_counts["Block 1 — Sail Trim"] == 25
    assert block_counts["Block 2 — Seamanship"] == 25
    assert block_counts["Block 3 — Cross-Book"] == 20
    assert block_counts["Block 4 — Negative"] == 12
    assert block_counts["Block 5 — Adversarial"] == 10
    assert block_counts["Block 6 — Guardrails"] == 10
    assert block_counts["Block 7 — Update & Rollback"] == 12

    # Verify active vs deferred
    active = [q for q in data if not q.get("is_deferred")]
    deferred = [q for q in data if q.get("is_deferred")]
    assert len(active) == 102
    assert len(deferred) == 12


def test_regression_pool_composition():
    """Verify that regression_pool.json meets Spec v1.1 §15.2 composition."""
    reg_path = Path("qa/regression_pool.json")
    assert reg_path.exists(), "regression_pool.json must exist"

    with open(reg_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 35, f"Expected 35 regression questions, got {len(data)}"

    b1_count = len([q for q in data if q["block"].startswith("Block 1")])
    b2_count = len([q for q in data if q["block"].startswith("Block 2")])
    b3_count = len([q for q in data if q["block"].startswith("Block 3")])
    b4_count = len([q for q in data if q["block"].startswith("Block 4")])
    b6_count = len([q for q in data if q["block"].startswith("Block 6")])

    assert b1_count == 10
    assert b2_count == 10
    assert b3_count == 5
    assert b4_count == 5
    assert b6_count == 5


def test_rubrics_and_evaluators():
    """Verify rubric calculations and refusal/guardrail logic."""
    assert len(RUBRIC_M4_CROSS_DOMAIN) == 6
    assert len(RUBRIC_M1_FAITHFULNESS) == 6

    # M1 Faithfulness
    assert score_m1_faithfulness(10, 10) == 1.0
    assert score_m1_faithfulness(9, 10) == 0.9
    assert score_m1_faithfulness(0, 0) == 1.0

    # M2 Citation
    assert score_m2_citation(19, 20) == 0.95

    # M3 Rule recall
    assert score_m3_rule_recall(3, 3) == 1.0
    assert score_m3_rule_recall(2, 3) == pytest.approx(0.6666, rel=1e-3)

    # M4 Normalization
    assert score_m4_cross_domain(4.5) == 4.5
    assert score_m4_cross_domain(6.0) == 5.0
    assert score_m4_cross_domain(-1.0) == 0.0

    # Refusal
    assert evaluate_refusal("В базе знаний нет информации по данному вопросу.") is True
    assert evaluate_refusal("This information was not found in manuals.") is True
    assert evaluate_refusal("To tie a bowline, make a loop and pass the working end.") is False

    # Guardrails
    pass_gr, _ = evaluate_guardrails("At TWS 30, reef mainsail to 2nd reef immediately.", [], ["RULE-REEF-001"])
    assert pass_gr is True

    fail_gr, reason = evaluate_guardrails("At TWS 30, carry full sail to go faster.", [], ["RULE-REEF-001"])
    assert fail_gr is False
    assert "RULE-REEF-001" in reason
