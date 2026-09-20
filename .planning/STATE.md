# STATE — MKP Project

**Updated:** 2026-09-20  
**Current Phase:** 0 (PoC & Validation) — **✅ COMPLETE (7/7 PASS)**  
**Overall Status:** Phase 0 завершена. Готовы к Phase 1.

---

## Active Phase

**Phase 0 — PoC & Validation**

**Plan:** `.planning/phase-0/PLAN.md`  
**Report:** `.planning/phase-0/POC_REPORT.md` — заполнен (6/7 задач)  
**PoC scripts:** `poc/p0_0*.py`

**PoC Progress:**
| Task | Status | Key Finding |
|------|--------|-------------|
| T0-01 Docling crop | ✅ PASS | 50 crops, `page_range=(s,e)` API |
| T0-02 VLM qwen2.5vl:7b | ✅ PASS | JSON=100%, type=100%, avg 2.9s с FA |
| T0-03 LanceDB FTS | ✅ PASS | EN recall=97.5%, default tokenizer |
| T0-04 e5-large embeddings | ✅ PASS | EN→EN recall=1.000, sentence-transformers |
| T0-05 OCR comparison | ✅ PASS | RapidOCR via Docling работает |
| T0-06 LadybugDB/NetworkX | ✅ PASS | LadybugDB нет на Win/Py3.14, NetworkX как v1 |
| T0-07 EPUB geometry | ✅ PASS | 88 spine items, ebooklib + zipfile workaround |

**Next step:** git commit финальных результатов → открыть Phase 1

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ✅ Complete |
| 1 | mkp-builder Core | ⏳ Ready to start |
| 2 | mkp-builder Complete | ⬜ Not started |
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
