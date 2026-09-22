# STATE — MKP-R Project

**Updated:** 2026-09-22  
**Current Phase:** 2.1 (mkp-builder — Rules Pipeline & Bookpack v0.3 Export)  
**Overall Status:** Phase 0, 1, 2 завершены. HLD v3.3.1 (Инварианты I0–I14) полностью интегрирован в проект. План Phase 2.1 обновлен и готов к выполнению.

---

## Active Phase

**Phase 2.1 — mkp-builder (Rules Pipeline & Bookpack v0.3 Export)**

**Plan:** `.planning/phase-2.1/PLAN.md`  
**Status:** ⏳ **READY TO EXECUTE (0/8 Tasks)**

**Phase 2.1 Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T2.1-01 Ontology & Pydantic Schemas | ⏳ PENDING | `ontology/` YAML + `rules_schema.py` (Claim, Cluster, Rule, CompatibilityInfo, ManifestV3) |
| T2.1-02 Claims Extraction Module | ⏳ PENDING | `extract/claims.py` с Qwen2.5:7b, привязкой к онтологии и цитатам |
| T2.1-03 Claims Clustering Module | ⏳ PENDING | `synthesize/cluster.py` группировка по архетипам/доменам/сигналам |
| T2.1-04 Rule Synthesis Module | ⏳ PENDING | `synthesize/synthesize.py` синтез правил + валидация порогов триггеров |
| T2.1-05 Guardrails Compiler | ⏳ PENDING | `compile/guardrails.py` генерация `guardrails.md` (≤ 8000 символов) |
| T2.1-06 Bookpack v0.3 Export & Ed25519 | ⏳ PENDING | `export/bookpack.py` 4-уровневая структура (`base/`, `yacht/`, `voyage/`, `personal/`), per-artifact sha256, Ed25519 подпись (I13) |
| T2.1-07 Rule Review CLI & Dataset | ⏳ PENDING | CLI режим ревью + 15+ эталонных правил T1 (Golden Rules) |
| T2.1-08 Tests & Pipeline Validation | ⏳ PENDING | Автотесты схем ManifestV3, Ed25519, пайплайна правил, компилятора и экспорта |

---

## Phase Status Overview

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete (7/7 PASS) |
| 1 | mkp-builder Core | ✅ Complete |
| 2 | mkp-builder Complete (Base Export) | ✅ Complete |
| 2.1 | mkp-builder Rules & Bookpack v0.3 | ⏳ Ready to execute |
| 3 | mkp-server (10 MCP Tools, Storage & WAL) | ⬜ Planned |
| 4 | QA & Acceptance | ⬜ Planned |

---

## Key Decisions (HLD v3.3.1 + PoC)

| Decision | Value | Source |
|----------|-------|--------|
| HLD Architecture | **HLD MKP-R v3.3.1** (DIFF v3.3 + DIFF v3.3.1 Инварианты) | `.init_doc/DIFF*` |
| Bookpack format | **v0.3.0** (`generation`, `parent_hash`, `compatibility`, `signature.ed25519`, per-artifact sha256) | HLD v3.3 §H.4, I13, I14 |
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
