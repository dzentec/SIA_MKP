# TESTING — Test Suites, Fixtures, Benchmarks & Evaluation

## Automated Test Suites (`pytest`)
- **Location:** `tests/`
- **Total Automated Tests:** 45 tests (100% PASS).
- **Execution Command:**
  ```bash
  pytest tests/ -v
  ```

### Test Suite Breakdown:
1. **`test_builder.py`**:
   - Tests document parsers (PDF, EPUB, DOCX), layout extraction, OCR fallbacks, and text chunking logic.
2. **`test_rules_pipeline.py`**:
   - Validates claim extraction, semantic clustering, formal rule synthesis, threshold checking against quotes, and static guardrails compilation.
3. **`test_export.py`**:
   - Validates `.bookpack.zip` packaging, `manifest.yaml` generation, per-artifact sha256 generation, and pure-Python RFC 8032 Ed25519 signing/verification.
4. **`test_server.py`**:
   - Validates all 10 FastMCP tools across `documents/`, `rules/`, and `system/` namespaces.
   - Tests LanceDB vector & FTS hybrid retrieval, NetworkX graph queries, and RuleStore matching.
5. **`test_invariants.py` & `test_qa_invariants_stress.py`**:
   - Stress-tests WAL recovery, sudden power cut simulations during import, directory `fsync`, atomic swap, and rollback mechanisms (Invariants I0–I14).
6. **`test_eval_dataset.py` & `test_eval_judge.py`**:
   - Validates stratification, question difficulty, and schema integrity of QA datasets.
   - Tests multi-judge evaluation calibration, rubric agreement, and confidence interval math.
7. **`test_runpod_orchestrator.py`**:
   - Mocks and validates RunPod GraphQL API communication, pod lifecycle, SSH/SCP commands, and auto-shutdown logic.

---

## Evaluation & Benchmarking Infrastructure (`qa/`)

### Benchmark Commands:
- **Phase 4 Acceptance Benchmark:**
  ```bash
  python qa/run_acceptance.py
  ```
- **Phase 5 Full Live Benchmark (114 questions):**
  ```bash
  python qa/run_full_live_benchmark.py
  ```
- **Real Books Benchmark (Dedekam Seamanship & Sail Trim):**
  ```bash
  python qa/run_real_books_test.py
  ```
- **Data Contamination & Leakage Check:**
  ```bash
  python qa/leakage_check.py
  ```

### Key Evaluation Datasets:
- **`golden_dataset.json`**: 30 stratified questions spanning seamanship, rules, sail trim, and safety.
- **`golden_full_dataset.json`**: 114 comprehensive benchmark questions across 7 topic blocks.
- **`golden_rules.json`**: 15 ground-truth verified maritime rules with verbatim quotes.
- **`regression_pool.json`**: Regression pool targeting previously failed edge cases.

### Evaluation Metrics (Spec v1.1):
- **M1 (Hallucination Rate):** Target `< 5.0%` -> **Achieved: 0.0%** (PASS)
- **M2 (Citation Rate):** Target `> 90.0%` -> **Achieved: 100.0%** (PASS)
- **M3 (Search Recall @ 3):** Target `> 85.0%` -> **Achieved: 100.0%** (PASS)
- **M4 (Safety Compliance Rate):** Target `100.0%` -> **Achieved: 100.0%** (PASS)
- **M5 (Delta vs Direct Baseline):** Target `> +30.0 pp` -> **Achieved: +91.3 pp** (PASS)
- **M6 (Data Leakage):** Target `< 30.0%` -> **Achieved: 11.0%** (PASS)
