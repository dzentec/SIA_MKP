# ROADMAP — Maritime Knowledge Pipeline with Rules (MKP-R)

**6 phases** | **38 requirements mapped** | All MVP requirements covered ✅

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 0 | PoC & Validation | Закрыть все технические риски до начала основной разработки | REQ-P0-01..07 | 7 (✅ PASS) |
| 1 | mkp-builder Core | Парсинг + VLM + верификация + чанкинг + TUI | REQ-B01..05, B08..09, C01..02, C03..04 | 5 (✅ PASS) |
| 2 | mkp-builder Triplets & Base Export | Триплеты + экспорт артефакта v1.5 + Golden Dataset base | REQ-B06..07, B10, QA-01 | 4 (✅ PASS) |
| 2.1 | mkp-builder Rules & Bookpack v0.2 | Онтология + Claims + Кластеризация + Синтез правил + Guardrails + Bookpack v0.2 | REQ-R01..06, REQ-B07 | 5 |
| 3 | mkp-server | База + импорт v0.2 + индексы (LanceDB/Graph/Rules) + 9 MCP-инструментов | REQ-S01..11, REQ-S08 | 6 |
| 4 | QA & Acceptance | Сквозной прогон Golden Dataset + 15+ эталонных правил + ручной аудит | REQ-QA-01, QA-02 | 5 |

---

## Phase 0: PoC & Validation (✅ Завершено)
**Goal:** Проверить все технические риски из HLD §14. 7 из 7 тестов пройдены успешно.

---

## Phase 1: mkp-builder — Core Pipeline (✅ Завершено)
**Goal:** Рабочий конвейер парсинг → VLM-аннотация → трёхступенчатая верификация → чанкинг с TUI и логированием.

---

## Phase 2: mkp-builder — Triplets & Base Export (✅ Завершено)
**Goal:** Экстракция триплетов (GraphRAG), упаковка базового артефакта, финализация CLI.

---

## Phase 2.1: mkp-builder — Rules Pipeline & Bookpack v0.2
**Goal:** Онтология, извлечение атомарных утверждений (Claims), кластеризация, синтез формализованных правил (Rules), компиляция Guardrails (≤ 8000 символов), экспорт артефакта `.bookpack.zip` стандарта v0.2 (4 уровня контента: T1 Base + Stubs T2/T2.5/T3).  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-2.1/PLAN.md`

**Requirements:** REQ-R01, REQ-R02, REQ-R03, REQ-R04, REQ-R05, REQ-R06, REQ-B07

**Success Criteria:**
1. Онтология (`ontology/`) и Pydantic-модели (`mkp_common/rules_schema.py`) финализированы.
2. `claims.py` извлекает атомарные утверждения с точными цитатами и маппингом на онтологию.
3. `synthesize.py` формирует объекты `Rule` со строгой валидацией числовых порогов триггеров.
4. `guardrails.py` компилирует markdown-файл правил (≤ 8000 символов).
5. Экспортер упаковывает `.bookpack.zip` v0.2 с каталогами `base/`, `yacht/` (stub), `voyage/` (stub), `personal/` (stub) и `manifest.yaml`.
6. Сформирован набор из 15+ верифицированных правил T1.

---

## Phase 3: mkp-server — 4-Tier Knowledge Base & 9 MCP Tools
**Goal:** Полнофункциональный сервер: импорт архивов v0.2, blue-green пересборка индексов (LanceDB + NetworkX Graph + Rules Store), 9 MCP-инструментов (documents/ и rules/), stub-обработка T2/T2.5/T3, verify, remove-book.  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-3/PLAN.md`

**Requirements:** REQ-S01, REQ-S02, REQ-S03, REQ-S04, REQ-S05, REQ-S06, REQ-S07, REQ-S08, REQ-S09, REQ-S10, REQ-S11

**Success Criteria:**
1. `mkp-server import <zip> --base C:\marine_base` импортирует v0.2, строит векторный, графовый и rules индексы.
2. Работают 4 инструмента namespace `documents/`: `search_chunks`, `get_diagram_image`, `get_related_entities`, `get_book_manifest`.
3. Работают 5 инструментов namespace `rules/`: `query_rules`, `get_rule`, `get_rule_provenance`, `list_conflicts`, `get_guardrails`.
4. Запросы по `tier=T2/T2.5/T3` возвращают корректные пустые результаты `[]` без ошибок.
5. Blue-green пересборка и защита от path traversal подтверждены тестами.

---

## Phase 4: QA & Acceptance
**Goal:** Сквозной прогон Golden Dataset через `mkp-server`, аудит точности правил и триплетов, финальный отчёт приёмки.  
**Mode:** qa  
**Duration:** 1 день  

**Requirements:** REQ-QA-01, REQ-QA-02

**Success Criteria:**
1. Hallucination rate = 0 на Golden Dataset.
2. Rule recall ≥ 0.8; Citation rate ≥ 0.9.
3. 15+ правил с полной трассируемостью до первоисточника.
4. Отчёт приёмки (`acceptance_report.md`) зафиксирован.
