# STATE — MKP Project

**Updated:** 2026-09-20  
**Current Phase:** 0 (PoC & Validation) — **NOT STARTED**  
**Overall Status:** Initialized

---

## Active Phase

None — проект только что инициализирован.

**Next step:** Запустить Phase 0 (PoC & Validation):
- Проверить все 7 технических рисков из REQ-P0-01..07
- Доклад по 9 проверкам Phase 0 (§13 HLD) перед стартом Phase 1

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | PoC & Validation | ⬜ Not started |
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
