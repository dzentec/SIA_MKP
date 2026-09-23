"""Tests for EvalJudge, Statistical Confidence Intervals, and Calibration (Task 5.3)."""

from pathlib import Path
import pytest

from qa.eval_judge import (
    calculate_wilson_ci,
    calculate_bootstrap_ci,
    EvalJudge,
)


def test_wilson_confidence_interval_formula():
    """Verify Wilson score confidence interval matches Spec v1.1 §10.3 worked example."""
    # Worked example in Spec v1.1 §10.3: p = 0.95, n = 100 -> [0.892, 0.975]
    p = 0.95
    n = 100
    low, high = calculate_wilson_ci(p, n, z=1.96)
    assert low == pytest.approx(0.892, abs=0.005)
    assert high == pytest.approx(0.975, abs=0.005)

    # Edge cases
    low_0, high_0 = calculate_wilson_ci(0.0, 50)
    assert low_0 >= 0.0
    assert high_0 < 0.1

    low_1, high_1 = calculate_wilson_ci(1.0, 50)
    assert low_1 > 0.9
    assert high_1 <= 1.0


def test_bootstrap_confidence_interval():
    """Verify Bootstrap percentile confidence interval for M4 continuous metric."""
    scores = [4.5, 4.0, 5.0, 4.2, 4.8, 3.9, 4.7, 4.6, 4.4, 4.5]
    low, high = calculate_bootstrap_ci(scores, n_resamples=500, seed=42)
    assert 3.8 <= low <= 4.5
    assert 4.3 <= high <= 5.0
    assert low <= high


def test_eval_judge_single_and_aggregate(tmp_path: Path):
    """Verify EvalJudge scoring M1-M8, caching, and aggregate CI computation."""
    cache_file = tmp_path / "test_cache.jsonl"
    judge = EvalJudge(cache_file=cache_file)

    q_item = {
        "id": "B1-Q01",
        "query": "How do you adjust backstay tension and mast bend when wind increases?",
        "expected_book": "dedekam_sail_trim",
        "expected_page": 42,
        "expected_rules": ["RULE-REEF-001"],
        "must_contain_terms": ["backstay tension", "mast bend", "flatten mainsail"],
        "is_negative": False,
        "is_adversarial": False,
        "is_guardrail": True,
        "guardrail_level": "warning",
    }

    answer = "[dedekam_sail_trim, p.42]: Adjust backstay tension and mast bend to flatten mainsail and depower rig. Active Rule RULE-REEF-001: Reef when wind increases."
    chunks = [{"book_id": "dedekam_sail_trim", "page_number": 42, "text_content": "Adjust backstay tension and mast bend to flatten mainsail."}]
    rules = [{"rule_id": "RULE-REEF-001", "severity": "warning"}]

    res = judge.evaluate_question(q_item, answer, chunks, rules)

    assert res["M1_Faithfulness"] == 1.0
    assert res["M2_Citation"] == 1.0
    assert res["M3_RuleRecall"] == 1.0
    assert res["M6_Guardrails_Warning"] == 1.0
    assert res["M7_Refusal"] == 1.0
    assert res["M8_Adversarial"] == 1.0

    # Aggregate
    agg = judge.calculate_aggregate_metrics([res])
    assert "M1_Faithfulness" in agg
    assert agg["M1_Faithfulness"].estimate == 1.0
    assert agg["M2_Citation"].estimate == 1.0

    # Human audit calibration
    audit = judge.validate_judge_against_human([res], sample_pct=1.0)
    assert audit["is_valid"] is True
    assert audit["error_rate_pct"] == 0.0
