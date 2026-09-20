# STATE — MKP Project

**Updated:** 2026-09-20  
**Current Phase:** 0 (PoC & Validation) — **PLANNED / READY TO EXECUTE**  
**Overall Status:** Phase 0 planned

---

## Active Phase

**Phase 0 — PoC & Validation** (план готов)

**Plan:** `.planning/phase-0/PLAN.md`  
**Report template:** `.planning/phase-0/POC_REPORT.md`  
**PoC scripts:** `poc/p0_0*.py` (создать при выполнении)

**Next step:** Выполнить 7 spike-задач из PLAN.md:
1. T0-01: Docling figure crop (запускать первым — даёт изображения для T0-02)
2. T0-02..T0-07: параллельно (независимые задачи)
3. Заполнить `POC_REPORT.md` → коммит → перейти к Phase 1

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | 📋 Planned |
| 1 | mkp-builder Core | ⬜ Not started |
| 2 | mkp-builder Complete | ⬜ Not started |
| 3 | mkp-server | ⬜ Not started |
| 4 | QA & Acceptance | ⬜ Not started |

---

## Key Decisions

| Decision | Value | Source |
|----------|-------|--------|
| Schema version | 1.5 | HLD v1.5 |
| Embedding model | intfloat/multilingual-e5-large, dim=1024 | HLD §7.1 |
| VLM model | qwen2.5vl:7b Q4_K_M | HLD §3 |
| Text model | qwen2.5:7b | HLD §4.5 |
| Vector DB | LanceDB ≥ 0.17 | HLD §7.2 |
| Graph DB | LadybugDB (пин версии) + fallback NetworkX | HLD §7.3 |
| Transport (default) | stdio | HLD §1.2 |
| Indexing strategy | Full rebuild (blue-green) | HLD §7.4 |
| OCR engine | TBD — Phase 0 выбирает | HLD §4.2 |

---

## Open Questions

- [ ] Версия LadybugDB для пина (Phase 0 проверяет)
- [ ] OCR-движок: RapidOCR vs Tesseract (Phase 0 проверяет)  
- [ ] FTS-токенизатор для кириллицы: default vs ngram (Phase 0 проверяет)
- [ ] Машина сборки имеет GPU ≥ 8 ГБ VRAM?
