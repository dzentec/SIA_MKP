# STATE — MKP-R Project

**Updated:** 2026-09-24  
**Current Phase:** Phase 6 — MKP-Builder Pipeline Upgrade, Dual-Stage Critic & Fallback Subsystem (v4.2)  
**Overall Status:** Фазы 0–5 успешно завершены (100% тестов PASS, бенчмарк v1.1 PASS). Выполняется Phase 6: устранение 5 критических багов генерации правил, single-GPU `OllamaManager`, двухступенчатый критик (`ClusterCritic` + `RuleCritic` 32B), подсистема аварийного останова Fallback v4.2, TUI-сигнализация и звуковые оповещения.

---

## Current Phase: Phase 6 — MKP-Builder Pipeline Upgrade, Dual-Stage Critic & Fallback Subsystem (v4.2)
**Plan:** `.planning/phase-6/PLAN.md`  
**Spec:** `.init_doc/MKP_Builder update.md`, `.init_doc/MKP_Builder update(critic_code).md`, `.init_doc/MKP_Builder update_Fallback Specification v4.2.md`  
**Status:** 🟡 **IN PROGRESS**

**Phase 6 Planned Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T6-01 Core Bug Patches & Schema Alignment | ⏳ READY | 5 багфиксов (`synthesize.py`, `rules_schema.py`, `cluster.py`, `claims.py`) |
| T6-02 Single-GPU OllamaManager | ⏳ READY | `ollama_manager.py` (последовательная загрузка моделей в VRAM ≤ 30GB, warmup, latency metrics) |
| T6-03 Configuration & Presets | ⏳ READY | `config.py` (пресеты `full`, `basic`, `fast`, `KillSwitchConfig`, CLI флаги) |
| T6-04 Dual-Stage Critic Subsystem | ⏳ READY | `critic/` (`verdict.py`, `base.py`, `prompts.py`, `cluster_critic.py`, `rule_critic.py`, `registry.py`) |
| T6-05 Fallback & Health Monitoring Subsystem | ⏳ READY | `fallback/` (`health.py`, `killswitch.py`, `vlm_tracker.py`, `retry.py`, `pod_stopper.py`, `shutdown.py`, `logger.py`, `batch.py`) |
| T6-06 TUI Signal Watcher & Sound Alerts | ⏳ READY | `mkp_tui/` (`watcher.py`, `sound.py`, `renderer.py` для аварийного останова) |
| T6-07 Pipeline Integration & Funnel Metrics | ⏳ READY | `metrics.py`, интеграция 6 фаз + KillSwitch в `pipeline.py` и `cli.py`, расширенный отчет `ingest_report.md` |
| T6-08 Comprehensive Testing & Acceptance | ⏳ READY | Unit-тесты критиков, парсера JSON, KillSwitch, VLM tracker, CircuitBreaker, TUI watcher и сквозная валидация |

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
| 5 | Full Evaluation & Quality Benchmark | ✅ Complete (5/5 Tasks PASS) |
| 6 | MKP-Builder Pipeline Upgrade, Critic & Fallback (v4.2) | 🟡 In Progress |
| 7 | RUNPOD-H: Hybrid MKP Builder (RunPod + OpenRouter) | ⚪ Planned (Plan ready) |

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
