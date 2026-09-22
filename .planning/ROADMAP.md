# ROADMAP — Maritime Knowledge Pipeline with Rules (MKP-R)

**6 phases** | **40 requirements mapped** | All MVP requirements covered ✅

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 0 | PoC & Validation | Закрыть все технические риски до начала основной разработки | REQ-P0-01..07 | 7 (✅ PASS) |
| 1 | mkp-builder Core | Парсинг + VLM + верификация + чанкинг + TUI | REQ-B01..05, B08..09, C01..02, C03..04 | 5 (✅ PASS) |
| 2 | mkp-builder Triplets & Base Export | Триплеты + экспорт артефакта v1.5 + Golden Dataset base | REQ-B06..07, B10, QA-01 | 4 (✅ PASS) |
| 2.1 | mkp-builder Rules & Bookpack v0.3 | Онтология + Claims + Кластеризация + Синтез правил + Guardrails + Bookpack v0.3.0 + Ed25519 | REQ-R01..06, REQ-B07 | 6 (✅ PASS) |
| 3 | mkp-server | 4-уровневое хранилище + импорт дельт v0.3.0 + WAL/Rollback (I0–I14) + индексы + 10 MCP-инструментов | REQ-S01..13 | 7 (✅ PASS) |
| 4 | QA & Acceptance | Сквозной прогон Golden Dataset + 15+ эталонных правил + тест Rollback/WAL | REQ-QA-01, QA-02 | 5 |

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

## Phase 2.1: mkp-builder — Rules Pipeline & Bookpack v0.3
**Goal:** Онтология, извлечение атомарных утверждений (Claims), кластеризация, синтез формализованных правил (Rules), компиляция Guardrails (≤ 8000 символов), экспорт артефакта `.bookpack.zip` стандарта **v0.3.0** (4 уровня контента: T1 Base + Stubs T2/T2.5/T3), генерация **per-artifact SHA-256** и цифровой подписи **Ed25519** (I13).  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-2.1/PLAN.md`

**Requirements:** REQ-R01, REQ-R02, REQ-R03, REQ-R04, REQ-R05, REQ-R06, REQ-B07

**Success Criteria:**
1. Онтология (`ontology/`) и Pydantic-модели (`mkp_common/rules_schema.py`) финализированы (включая `CompatibilityInfo`, `ManifestV3`, поля `deprecated` и `orphaned`).
2. `claims.py` извлекает атомарные утверждения с точными цитатами и маппингом на онтологию.
3. `synthesize.py` формирует объекты `Rule` со строгой валидацией числовых порогов триггеров.
4. `guardrails.py` компилирует markdown-файл правил (≤ 8000 символов).
5. Экспортер упаковывает `.bookpack.zip` / `.zst` v0.3.0 с каталогами `base/`, `yacht/` (stub), `voyage/` (stub), `personal/` (stub), `manifest.yaml`, `checksums.sha256`, per-artifact чексуммами и подписью `signature.ed25519` (I13).
6. Сформирован набор из 15+ верифицированных правил T1 (Golden Rules).

---

## Phase 3: mkp-server — 4-Tier Knowledge Base, Storage Lifecycle & 10 MCP Tools
**Goal:** Полнофункциональный сервер: управление хранилищем `/storage/` (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`), импорт архивов и раздельных дельт v0.3.0 с верификацией Ed25519 (I13) и совместимости (I14), транзакционный конвейер с WAL и гарантированным отбоем/Rollback (I0–I10), построение индексов (LanceDB + NetworkX Graph + Rules Store), **10 MCP-инструментов** (включая `get_bookpack_info`), изоляция T1 и orphaning-контроль.  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-3/PLAN.md`

**Requirements:** REQ-S01, REQ-S02, REQ-S03, REQ-S04, REQ-S05, REQ-S06, REQ-S07, REQ-S08, REQ-S09, REQ-S10, REQ-S11, REQ-S12, REQ-S13

**Success Criteria:**
1. Управление хранилищем `/storage/` с многоуровневой защитой `active` → `backup` → `fallback` (R/O SquashFS) → `USB factory` (I8, I11).
2. `mkp-server import` поддерживает монолитные bookpack v0.3.0, `T1-delta` и `User-delta` со строгой проверкой Ed25519 (I13) и `compatibility` (I14).
3. Транзакционный конвейер обновления с WAL, `fsync` на файл и каталог, атомарной заменой (`renameat2`) и автоматическим откатом к `backup/` при сбое (I1–I10).
4. Ручной откат одной командой/кнопкой при валидном backup и поддержка 3-х сценариев при поврежденном backup (I5).
5. Работают **10 MCP-инструментов**: 4 в `documents/`, 5 в `rules/` и 1 в `system/` (`get_bookpack_info`).
6. Пользовательские MCP-инструменты изолированы от модификации слоя T1.
7. При изменении T1 зависимые пользовательские правила помечаются `orphaned=true` без удаления.

---

## Phase 4: QA & Acceptance
**Goal:** Сквозной прогон Golden Dataset через `mkp-server`, аудит точности правил и триплетов, верификация инвариантов надежности Rollback/WAL, финальный отчёт приёмки.  
**Mode:** qa  
**Duration:** 1 день  

**Requirements:** REQ-QA-01, REQ-QA-02

**Success Criteria:**
1. Hallucination rate = 0 на Golden Dataset.
2. Rule recall ≥ 0.8; Citation rate ≥ 0.9.
3. 15+ правил с полной трассируемостью до первоисточника.
4. Прохождение тестов сбоя питания / отката обновлений (I0–I14).
5. Отчёт приёмки (`acceptance_report.md`) зафиксирован.
