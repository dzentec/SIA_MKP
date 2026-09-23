"""Baseline Runner for MKP-R Full Evaluation Spec v1.1 (§11 Baseline).

Executes control groups:
- Group A: No-MCP (base model weights only)
- Group B: Search-Only (naive RAG, search_chunks only)
- Group C: Full (all 10 MCP tools)

Calculates comparative metrics (M1, M2, M3, M7) and deltas (Δ A→C, Δ B→C).
Target: Δ A→C >= 20 pp on Faithfulness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
import tempfile
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from qa.corpus_fixture import setup_golden_storage
from qa.offline_mcp_agent import OfflineMcpAgent
from qa.rubrics import (
    evaluate_refusal,
    score_m1_faithfulness,
    score_m2_citation,
    score_m3_rule_recall,
)
from mkp_server.server import MKPServerEngine


def run_baseline_evaluation(
    dataset_path: Path | str = "qa/golden_full_dataset.json",
    sample_size: int = 30,
    seed: int = 42,
    groups: list[str] | None = None,
) -> dict[str, Any]:
    """Run baseline evaluation across Group A, Group B, and Group C."""
    if groups is None:
        groups = ["A", "B", "C"]

    ds_file = Path(dataset_path)
    with open(ds_file, "r", encoding="utf-8") as f:
        full_data = json.load(f)

    # Filter out deferred items
    active_items = [q for q in full_data if not q.get("is_deferred")]

    # Sample deterministically
    random.seed(seed)
    if len(active_items) > sample_size:
        sample_questions = random.sample(active_items, sample_size)
    else:
        sample_questions = active_items

    # Setup isolated test storage
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        storage_root = Path(tmp_dir) / "baseline_storage"
        setup_golden_storage(storage_root)
        engine = MKPServerEngine(storage_root)
        agent = OfflineMcpAgent(engine=engine, seed=seed)

        group_results: dict[str, dict[str, Any]] = {}

        for grp in groups:
            print(f"--- Running Baseline Group {grp} ({len(sample_questions)} questions) ---")
            m1_scores = []
            m2_scores = []
            m3_scores = []
            m7_scores = []

            for q in sample_questions:
                traj = agent.run_query(q, group=grp)
                ans = traj.answer
                is_neg = q.get("is_negative", False)

                # M1 Faithfulness: based on support of must_contain_terms
                req_terms = q.get("must_contain_terms", [])
                if is_neg:
                    # For negative, refusal is 100% faithful
                    is_refusal = evaluate_refusal(ans)
                    m1_scores.append(1.0 if is_refusal else 0.0)
                    m7_scores.append(1.0 if is_refusal else 0.0)
                else:
                    matched = sum(1 for t in req_terms if t.lower() in ans.lower())
                    total = len(req_terms) if req_terms else 1
                    m1_scores.append(score_m1_faithfulness(matched, total))

                # M2 Citation: checks presence of expected book/page
                if grp == "A":
                    # Group A has no citations
                    m2_scores.append(0.0)
                else:
                    if is_neg:
                        m2_scores.append(1.0)
                    else:
                        exp_book = q.get("expected_book", "")
                        exp_p = q.get("expected_page", 0)
                        has_book = exp_book in ans or exp_book == "multidomain"
                        has_page = f"p.{exp_p}" in ans or f"page {exp_p}" in ans or f"p.{exp_p-1}" in ans or f"p.{exp_p+1}" in ans
                        m2_scores.append(1.0 if (has_book and has_page) else (0.5 if has_book else 0.0))

                # M3 Rule recall
                exp_rules = q.get("expected_rules", [])
                if not exp_rules or is_neg:
                    m3_scores.append(1.0)
                else:
                    if grp in ("A", "B"):
                        # No rules tool in A or B
                        m3_scores.append(0.0)
                    else:
                        act_rule_ids = [r.get("rule_id", "") if isinstance(r, dict) else getattr(r, "rule_id", "") for r in traj.activated_rules]
                        found_rules = sum(1 for r in exp_rules if (r in ans or r in act_rule_ids))
                        m3_scores.append(score_m3_rule_recall(found_rules, len(exp_rules)))

            mean_m1 = sum(m1_scores) / len(m1_scores) if m1_scores else 0.0
            mean_m2 = sum(m2_scores) / len(m2_scores) if m2_scores else 0.0
            mean_m3 = sum(m3_scores) / len(m3_scores) if m3_scores else 0.0
            mean_m7 = sum(m7_scores) / len(m7_scores) if m7_scores else 1.0

            group_results[grp] = {
                "M1_Faithfulness": round(mean_m1 * 100, 1),
                "M2_Citation": round(mean_m2 * 100, 1),
                "M3_RuleRecall": round(mean_m3 * 100, 1),
                "M7_Refusal": round(mean_m7 * 100, 1),
                "n": len(sample_questions),
            }

        # Calculate Deltas
        deltas = {}
        if "A" in group_results and "C" in group_results:
            deltas["delta_A_to_C"] = {
                "M1": round(group_results["C"]["M1_Faithfulness"] - group_results["A"]["M1_Faithfulness"], 1),
                "M2": round(group_results["C"]["M2_Citation"] - group_results["A"]["M2_Citation"], 1),
                "M3": round(group_results["C"]["M3_RuleRecall"] - group_results["A"]["M3_RuleRecall"], 1),
                "M7": round(group_results["C"]["M7_Refusal"] - group_results["A"]["M7_Refusal"], 1),
            }
        if "B" in group_results and "C" in group_results:
            deltas["delta_B_to_C"] = {
                "M1": round(group_results["C"]["M1_Faithfulness"] - group_results["B"]["M1_Faithfulness"], 1),
                "M2": round(group_results["C"]["M2_Citation"] - group_results["B"]["M2_Citation"], 1),
                "M3": round(group_results["C"]["M3_RuleRecall"] - group_results["B"]["M3_RuleRecall"], 1),
                "M7": round(group_results["C"]["M7_Refusal"] - group_results["B"]["M7_Refusal"], 1),
            }

        out = {
            "sample_size": len(sample_questions),
            "groups": group_results,
            "deltas": deltas,
            "meets_delta_target": deltas.get("delta_A_to_C", {}).get("M1", 0.0) >= 20.0,
        }

        # Save to qa/raw/baseline_results.json
        out_file = Path("qa/raw/baseline_results.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        print("\n=== Baseline Comparison Summary ===")
        print(f"Sample size: {len(sample_questions)}")
        for g, vals in group_results.items():
            print(f"Group {g}: M1={vals['M1_Faithfulness']}% | M2={vals['M2_Citation']}% | M3={vals['M3_RuleRecall']}% | M7={vals['M7_Refusal']}%")
        if "delta_A_to_C" in deltas:
            print(f"Delta A->C: M1=+{deltas['delta_A_to_C']['M1']}pp | M2=+{deltas['delta_A_to_C']['M2']}pp | M3=+{deltas['delta_A_to_C']['M3']}pp")
            print(f"Target >= 20pp Faithfulness: {'PASS' if out['meets_delta_target'] else 'FAIL'}")

        return out


def main():
    parser = argparse.ArgumentParser(description="Run baseline evaluation (Group A/B/C)")
    parser.add_argument("--dataset", default="qa/golden_full_dataset.json")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--group", choices=["A", "B", "C", "all"], default="all")
    args = parser.parse_args()

    groups = ["A", "B", "C"] if args.group == "all" else [args.group]
    run_baseline_evaluation(args.dataset, sample_size=args.samples, seed=args.seed, groups=groups)


if __name__ == "__main__":
    main()
