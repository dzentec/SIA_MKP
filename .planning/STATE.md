# STATE — MKP-R Project

**Updated:** 2026-09-21  
**Current Phase:** 2.1 (mkp-builder — Rules Pipeline & Bookpack v0.2)  
**Overall Status:** Phase 0, 1, 2 завершены. HLD v3.1 интегрирован в проект. Создан план Phase 2.1.

---

## Active Phase

**Phase 2.1 — mkp-builder (Rules Pipeline & Bookpack v0.2 Export)**

**Plan:** `.planning/phase-2.1/PLAN.md`  
**Status:** ⏳ **READY TO EXECUTE (0/8 Tasks)**

**Phase 2.1 Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T2.1-01 Ontology & Pydantic Schemas | ⏳ PENDING | `ontology/` YAML + `rules_schema.py` (Claim, Cluster, Rule, ManifestV2) |
| T2.1-02 Claims Extraction Module | ⏳ PENDING | `extract/claims.py` с Qwen2.5:7b, привязкой к онтологии и цитатам |
| T2.1-03 Claims Clustering Module | ⏳ PENDING | `synthesize/cluster.py` группировка по архетипам/доменам/сигналам |
| T2.1-04 Rule Synthesis Module | ⏳ PENDING | `synthesize/synthesize.py` синтез правил + валидация порогов триггеров |
| T2.1-05 Guardrails Compiler | ⏳ PENDING | `compile/guardrails.py` генерация `guardrails.md` (≤ 8000 символов) |
| T2.1-06 Bookpack v0.2 Export | ⏳ PENDING | `export/bookpack.py` 4-уровневая структура (`base/`, `yacht/`, `voyage/`, `personal/`) |
| T2.1-07 Rule Review CLI & Dataset | ⏳ PENDING | CLI режим ревью + 15+ эталонных правил T1 |
| T2.1-08 Tests & Pipeline Validation | ⏳ PENDING | Автотесты схем, пайплайна правил, компилятора и экспорта |

---

## Phase Status Overview

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete (7/7 PASS) |
| 1 | mkp-builder Core | ✅ Complete |
| 2 | mkp-builder Complete (Base Export) | ✅ Complete |
| 2.1 | mkp-builder Rules & Bookpack v0.2 | ⏳ Ready to execute |
| 3 | mkp-server (9 MCP Tools) | ⬜ Planned |
| 4 | QA & Acceptance | ⬜ Planned |

---

## Key Decisions (HLD v3.1 + PoC)

| Decision | Value | Source |
|----------|-------|--------|
| HLD Architecture | **HLD MKP-R v3.1** | `.init_doc/HLD_MKP-R_v3.1_*.md` |
| Bookpack format | **v0.2.0** (`manifest.yaml`, 4-tier folders) | HLD v3.1 §7.3 |
| Content Tiers | T1: Base (MVP), T2: Yacht (Stub), T2.5: Voyage (Stub), T3: Personal (Stub) | HLD v3.1 §4 |
| MCP Tools set | **9 tools** (4 documents/ + 5 rules/) | HLD v3.1 §8 |
| Rule validation | Строгая проверка порогов триггеров по цитатам claims | HLD v3.1 §9.3 |
| Guardrails limit | ≤ 8000 символов, только T1 approved | HLD v3.1 §8.4 |
| Embedding model | intfloat/multilingual-e5-large, dim=1024 | HLD §7.1 |
| Embedding backend | **sentence-transformers** | PoC T0-04 |
| Embedding prefixes | `query:` / `passage:` обязательны | PoC T0-04 |
| VLM model | qwen2.5vl:7b Q4_K_M (OLLAMA_FLASH_ATTENTION=1) | PoC T0-02 |
| Text model | qwen2.5:7b | HLD §4.5 |
| Vector DB | LanceDB ≥ 0.38 | HLD §7.2 |
| Graph Engine | **NetworkX + triplets.jsonl** | PoC T0-06 |
| Python version | **3.14.4** | Project setup |
