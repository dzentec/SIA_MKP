"""Data Leakage Checker for MKP-R Full Evaluation Spec v1.1 (§16 Leakage Check).

Evaluates whether the base model has memorized the manual texts without external retrieval:
- Runs 20 questions from Block 1 (Sail Trim) and Block 2 (Seamanship) with MCP disabled (Group A).
- Calculates Faithfulness (Leakage rate).
- Target: Leakage < 30% (Dataset validity threshold < 50%).
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
from qa.rubrics import score_m1_faithfulness
from mkp_server.server import MKPServerEngine


def run_leakage_check(
    dataset_path: Path | str = "qa/golden_full_dataset.json",
    sample_size: int = 20,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute leakage check on Block 1 & 2 without MCP tools."""
    ds_file = Path(dataset_path)
    with open(ds_file, "r", encoding="utf-8") as f:
        full_data = json.load(f)

    # Filter Block 1 and Block 2 questions
    b1_b2_items = [
        q for q in full_data
        if (q.get("block", "").startswith("Block 1") or q.get("block", "").startswith("Block 2"))
        and not q.get("is_deferred")
    ]

    random.seed(seed)
    if len(b1_b2_items) > sample_size:
        sample_questions = random.sample(b1_b2_items, sample_size)
    else:
        sample_questions = b1_b2_items

    print(f"--- Running Leakage Check ({len(sample_questions)} questions from Block 1 & 2, MCP Disabled) ---")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        storage_root = Path(tmp_dir) / "leakage_storage"
        setup_golden_storage(storage_root)
        engine = MKPServerEngine(storage_root)
        agent = OfflineMcpAgent(engine=engine, seed=seed)

        m1_scores = []
        detailed_records = []

        for q in sample_questions:
            traj = agent.run_query(q, group="A")
            ans = traj.answer
            req_terms = q.get("must_contain_terms", [])
            matched = sum(1 for t in req_terms if t.lower() in ans.lower())
            total = len(req_terms) if req_terms else 1
            score = score_m1_faithfulness(matched, total)
            m1_scores.append(score)

            detailed_records.append({
                "q_id": q["id"],
                "query": q["query"],
                "score": score,
                "matched_terms": matched,
                "total_terms": total,
            })

        mean_leakage = (sum(m1_scores) / len(m1_scores)) if m1_scores else 0.0
        leakage_pct = round(mean_leakage * 100, 1)

        is_valid = leakage_pct < 30.0
        is_acceptable = leakage_pct < 50.0

        status = "VALID (< 30%)" if is_valid else ("ACCEPTABLE (< 50%)" if is_acceptable else "INVALID (>= 50%)")

        results = {
            "sample_size": len(sample_questions),
            "leakage_rate_pct": leakage_pct,
            "threshold_target_pct": 30.0,
            "threshold_max_pct": 50.0,
            "status": status,
            "passed": is_valid,
            "details": detailed_records,
        }

        out_file = Path("qa/raw/leakage_results.json")
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print("\n=== Data Leakage Check Summary ===")
        print(f"Sample: {len(sample_questions)} questions (Block 1 + Block 2)")
        print(f"MCP Access: DISABLED (Group A)")
        print(f"M1 Faithfulness (Memorization Rate): {leakage_pct}% (Target: < 30%)")
        print(f"Status: {status} — {'PASS' if is_valid else 'FAIL'}")

        return results


def main():
    parser = argparse.ArgumentParser(description="Run Data Leakage Check")
    parser.add_argument("--dataset", default="qa/golden_full_dataset.json")
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    run_leakage_check(args.dataset, sample_size=args.samples, seed=args.seed)


if __name__ == "__main__":
    main()
