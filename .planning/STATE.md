# STATE — MKP-R Project

**Updated:** 2026-09-22  
**Current Phase:** Complete (All Phases 0–4 Finished)  
**Overall Status:** Phase 0, 1, 2, 2.1, 3, 4 полностью завершены (100% тестов PASS — 39/39 тестов). Все требования HLD v3.3.1 (Инварианты I0–I14) и спецификации QA/Acceptance (REQ-QA-01, REQ-QA-02, REQ-S01..S13) выполнены и верифицированы.

---

## Completed Phase: Phase 4 — QA & Acceptance (Golden Datasets, Benchmark & Invariants Stress Tests)

**Plan:** `.planning/phase-4/PLAN.md`  
**Status:** ✅ **COMPLETE (4/4 Tasks PASS)**
**Report:** `qa/acceptance_report.md`

**Phase 4 Tasks Execution Summary:**
| Task | Status | Description |
|------|--------|-------------|
| T4-01 Golden Datasets & Reference Rules | ✅ DONE | `qa/golden_rules.json` (15 верифицированных T1 правил с цитатами), `qa/golden_dataset.json` (30 стратифицированных мультиязычных вопросов по 6 типам диаграмм и 2 книгам Dedekam), `tests/test_golden_dataset.py` |
| T4-02 Acceptance Benchmarking Suite | ✅ DONE | `qa/metrics.py`, `qa/evaluator.py`, `qa/corpus_fixture.py`: расчет Hallucination rate (0.0%), Rule recall (87.5%), Citation rate (100.0%), Search recall @ 3/5 (100.0%), Triplets accuracy (100.0%), Guardrails size (340 chars <= 8000) |
| T4-03 Invariants Stress & Chaos Testing | ✅ DONE | `tests/test_qa_invariants_stress.py`: power loss injection на 11 шагах WAL, recovery поврежденного бэкапа (3 опции I5), update storm (5 последовательных обновлений), path traversal fuzzing |
| T4-04 Automated Acceptance Runner & Report | ✅ DONE | `qa/run_acceptance.py`: запуск бенчмарка в чистом окружении, автогенерация отчетов `qa/acceptance_report.md` и `.planning/phase-4/ACCEPTANCE.md` |

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
