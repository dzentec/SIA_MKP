# STATE — MKP Project

**Updated:** 2026-09-20  
**Current Phase:** 0 (PoC & Validation) — **✅ COMPLETE (7/7 PASS)**  
**Overall Status:** Phase 0 завершена. Готовы к Phase 1.

---

## Active Phase

**Phase 1 — mkp-builder Core Pipeline**

**Plan:** `.planning/phase-1/PLAN.md`  
**Status:** ✅ **COMPLETE (10/10 Tasks)**

**Phase 1 Tasks:**
| Task | Status | Description |
|------|--------|-------------|
| T1-01 pyproject & models | ✅ PASS | `pyproject.toml`, `mkp-common` Pydantic models (Schema v1.5) |
| T1-02 location_ref & cache | ✅ PASS | `LocationRef`, SHA-256 cache, rotating logger |
| T1-03 document parsers | ✅ PASS | Docling PDF + EPUB (ebooklib+zipfile) + DOCX parsers |
| T1-04 OCR routing | ✅ PASS | digital / scanned / mixed routing + RapidOCR/Tesseract |
| T1-05 VLM annotation | ✅ PASS | Ollama qwen2.5vl:7b Prompt 2.0 (discriminated union) |
| T1-06 3-stage verification | ✅ PASS | Schema + Text LLM + Visual Critic + QA queue |
| T1-07 chunking engine | ✅ PASS | section/table-aware chunking (max_tokens=512, overlap=64) |
| T1-08 orchestrator pipeline | ✅ PASS | builder pipeline coordinator (`build_book`) |
| T1-09 Rich TUI & CLI | ✅ PASS | 7 progress bars, CLI `mkp-builder build`, headless mode |
| T1-10 E2E integration test | ✅ PASS | 8 automated tests in `tests/` pass (100%) |

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete |
| 1 | mkp-builder Core | ✅ Complete |
| 2 | mkp-builder Complete | ⏳ Ready to start |
| 3 | mkp-server | ⬜ Not started |
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
