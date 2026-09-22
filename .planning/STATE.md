# STATE — MKP-R Project

**Updated:** 2026-09-23  
**Current Phase:** Phase 5 — Full Evaluation & Quality Benchmark (Planning Ready)  
**Overall Status:** Фазы 0–4 завершены (100% тестов PASS — 40/40). Сформирован и утвержден детальный план Phase 5 по спецификации MKP-R Full Evaluation Spec v1.1.

---

## Current Phase: Phase 5 — Full Evaluation & Quality Benchmark
**Plan:** `.planning/phase-5/PLAN.md`  
**Spec:** `.init_doc/MKP-R Full Evaluation Spec v1.1_1of2.md`, `.init_doc/MKP-R Full Evaluation Spec v1.1_2of2.md`  
**Status:** ⏳ **READY TO EXECUTE (5 Tasks Planned)**

**Phase 5 Planned Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T5-01 Dataset & Rubrics Engineering | ⏳ PENDING | `qa/golden_full_dataset.json` (95–110 вопросов, 7 блоков), `qa/regression_pool.json`, `qa/rubrics.py`, `qa/config.yaml` |
| T5-02 Offline MCP Agent & Baselines | ⏳ PENDING | `qa/offline_mcp_agent.py` (Qwen 10 MCP tools), `qa/baseline_runner.py` (Group A/B/C), `qa/leakage_check.py` (< 30%) |
| T5-03 Gemini LLM-as-a-Judge Engine | ⏳ PENDING | `qa/eval_judge.py` (M1–M8, M4 3-judge rubric agreement, 95% Wilson/Bootstrap CI, 10% human audit calibration) |
| T5-04 Full Orchestrator & Markdown Report | ⏳ PENDING | `qa/full_eval_runner.py` ($N=3$ runs, median aggregation, regression check, `qa/reports/full_eval_report.md`) |
| T5-05 Execution, Verification & Sign-Off | ⏳ PENDING | Сквозной прогон бенчмарка, верификация критериев успеха и фиксация UAT |

---

## Phase Status Overview

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete (7/7 PASS) |
| 1 | mkp-builder Core | ✅ Complete |
| 2 | mkp-builder Complete (Base Export) | ✅ Complete |
| 2.1 | mkp-builder Rules & Bookpack v0.3 | ✅ Complete (8/8 PASS) |
| 3 | mkp-server (10 MCP Tools, Storage & WAL) | ✅ Complete (8/8 PASS) |
| 4 | QA & Acceptance | ✅ Complete (4/4 PASS) |
| 5 | Full Evaluation & Quality Benchmark | ⏳ Ready to Execute (0/5 Tasks) |

---

## Key Decisions (HLD v3.3.1 + PoC)

| Decision | Value | Source |
|----------|-------|--------|
| HLD Architecture | **HLD MKP-R v3.3.1** (DIFF v3.3 + DIFF v3.3.1 Инварианты) | `.init_doc/DIFF*` |
| Bookpack format | **v0.3.0** (`generation`, `parent_hash`, `compatibility`, `signature.ed25519`, per-artifact sha256) | HLD v3.3 §H.4, I13, I14 |
| Ed25519 Security | Pure-Python RFC 8032 signer (zero native deps, 100% offline) | Phase 2.1 (I13) |
| Storage Architecture | 4-уровневая (`active/`, `backup/`, `fallback/` SquashFS R/O, `staging/`, `failed/`) | HLD v3.3 §D, I8, I11 |
| Rollback & Recovery | WAL с `fsync` директорий, `renameat2` atomic swap, 1 backup (N-1), авто/ручной откат | HLD v3.3 §B/C, v3.3.1 I0–I10 |
| Content Tiers | T1: Base (MVP, Read-Only), T2: Yacht (Stub), T2.5: Voyage (Stub), T3: Personal (Stub) | HLD v3.3 §A.3, §4 |
| MCP Tools set | **10 tools** (4 documents/ + 5 rules/ + 1 system/ `get_bookpack_info`) | HLD v3.3 §H.5 |
| User-layer Orphaning | User-правила помечаются `orphaned=true` без удаления; Tombstones в T1 на 2 релиза | HLD v3.3 §G |
| Update Policy | Force-update запрещен в море (I12); Opt-in телеметрия с preview | HLD v3.3 §F, I12 |
| Rule validation | Строгая проверка порогов триггеров по цитатам claims | HLD v3.1 §9.3 |
| Guardrails limit | ≤ 8000 символов, только T1 approved | HLD v3.1 §8.4 |
| Embedding model | intfloat/multilingual-e5-large, dim=1024 (`query:`/`passage:`) | PoC T0-04 |
| VLM model | qwen2.5vl:7b Q4_K_M (OLLAMA_FLASH_ATTENTION=1) | PoC T0-02 |
| Text model | qwen2.5:7b | HLD §4.5 |
| Vector DB | LanceDB ≥ 0.38 | HLD §7.2 |
| Graph Engine | **NetworkX + triplets.jsonl** | PoC T0-06 |
| Python version | **3.14.4 / 3.11** | Project setup |
