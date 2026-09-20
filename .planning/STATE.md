# STATE — MKP Project

**Updated:** 2026-09-20  
**Current Phase:** 0 (PoC & Validation) — **✅ COMPLETE (7/7 PASS)**  
**Overall Status:** Phase 0 завершена. Готовы к Phase 1.

---

## Active Phase

**Phase 3 — mkp-server (Database, Indexing & FastMCP Server)**

**Plan:** `.planning/phase-3/PLAN.md`  
**Status:** ⏳ **READY TO EXECUTE (0/8 Tasks)**

**Phase 3 Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T3-01 Base Registry & Structure | ⏳ PENDING | Canonical directory layout, `base.json`, rotating server logger |
| T3-02 Ingestion, Merge & Verify | ⏳ PENDING | `.bookpack.zip` ingestion, `pack/` merger, `remove-book`, `verify` |
| T3-03 LanceDB Hybrid Search | ⏳ PENDING | `multilingual-e5-large` embedder (`passage:`/`query:`), FTS, RRFReranker |
| T3-04 Knowledge Graph Engine | ⏳ PENDING | NetworkX GraphRAG, multi-hop entity traversal, provenance |
| T3-05 Blue-Green Lifecycle | ⏳ PENDING | Build in `derived_new/`, smoke test, atomic swap & in-memory hot reload |
| T3-06 FastMCP Server & 5 Tools | ⏳ PENDING | FastMCP tools, path traversal protection, stdio & streamable-http |
| T3-07 Server CLI & Entrypoint | ⏳ PENDING | `mkp-server` Typer CLI (`serve/import/remove-book/verify/list-books`) |
| T3-08 Tests & Contract Validation | ⏳ PENDING | Automated test suite for server, hybrid search, graph, and MCP tools |

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete |
| 1 | mkp-builder Core | ✅ Complete |
| 2 | mkp-builder Complete | ✅ Complete |
| 3 | mkp-server | ⏳ Ready to execute |
| 4 | QA & Acceptance | ⬜ Not started |

---

## Key Decisions (обновлено по результатам Phase 0)

| Decision | Value | Source |
|----------|-------|--------|
| Schema version | 1.5 | HLD v1.5 |
| Источники | **Английский язык** | User decision 2026-09-20 |
| Embedding model | intfloat/multilingual-e5-large, dim=1024 | HLD §7.1 |
| Embedding backend | **sentence-transformers** (НЕ fastembed) | PoC T0-04 |
| Embedding prefixes | `query:` / `passage:` обязательны | PoC T0-04 |
| VLM model | qwen2.5vl:7b Q4_K_M | HLD §3 |
| Text model | qwen2.5:7b | HLD §4.5 |
| Ollama | v0.34.2 portable, D:\Ollama\ | PoC T0-02 |
| Ollama models dir | D:\AI_models\ollama | User decision |
| OLLAMA_FLASH_ATTENTION | **=1 обязательно** (87% speedup, 2.9s avg, без него таймауты 45s) | PoC T0-02 |
| VLM JSON schema | упростить: `{diagram_type, description, details}` | PoC T0-02 |
| Vector DB | LanceDB ≥ 0.38 | HLD §7.2 |
| FTS tokenizer | **default** (EN corpus) | PoC T0-03 |
| Graph DB | **NetworkX + triplets.jsonl** (LadybugDB нет на Win/Py3.14) | PoC T0-06 |
| OCR engine (Docling) | **RapidOcrOptions()** | PoC T0-05 |
| OCR engine (standalone) | Tesseract 5.4, D:\Tesseract\ | PoC T0-05 |
| Python version | **3.14.4** | User decision |
| EPUB parsing | ebooklib (spine) + zipfile (images), Docling EPUB bug | PoC T0-07 |

---

## Open Questions — ЗАКРЫТЫ по результатам Phase 0

- [x] Версия LadybugDB → NetworkX v1, LadybugDB при доступности
- [x] OCR-движок → RapidOcrOptions() в Docling
- [x] FTS-токенизатор → default (английский корпус)
- [x] GPU VRAM → RTX 2060 6GB VRAM доступна (достаточно для 7B Q4)
- [x] VLM стабильность → 100% JSON, FLASH_ATTENTION обязателен
- [x] Язык источников → Английский

## Open Questions — Новые

- [ ] Нужна ли поддержка кириллических запросов к английским документам?
