# Phase 3: mkp-server — 4-Tier Knowledge Base, Storage Lifecycle & 10 MCP Tools

**Phase Goal:** Полнофункциональный локальный сервер базы знаний и правил `mkp-server`: управление 4-уровневым хранилищем `/storage/` (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`), импорт архивов и дельт стандарта **v0.3.0** с обязательной верификацией цифровой подписи **Ed25519** (I13) и матрицы совместимости (I14), транзакционный конвейер обновления с **WAL, fsync каталогов, atomic swap и гарантированным Rollback (Инварианты I0–I11)**, построение гибридных индексов (LanceDB Chunks & Rules + NetworkX Graph), **10 инструментов FastMCP** (пространства имен `documents/`, `rules/` и `system/`), изоляция T1 от модификаций и отслеживание разрыва связей (Orphaning & Tombstones).

**Source of Truth:** HLD v3.1, DIFF v3.3, DIFF v3.3.1 (Инварианты I0–I14), `REQUIREMENTS.md` (REQ-S01..REQ-S13).  
**Dependencies:** Phase 0 (PoC), Phase 1 (`mkp-builder` Core), Phase 2 (`mkp-builder` Triplets & Export), **Phase 2.1 (`mkp-builder` Rules Pipeline & Bookpack v0.3)**.

---

## Tasks Breakdown

| # | Task | Requirements | Deliverables | Checkpoint |
|---|------|--------------|--------------|------------|
| **T3-01** | **Storage Architecture & v0.3 Registry Manager** | REQ-S01, REQ-S10, REQ-S11 | `src/mkp_server/storage.py`, `src/mkp_server/models.py` | 4-уровневая структура `/storage/` (`active/`, `backup/`, `staging/`, `fallback/`, `failed/`, `logs/`), реестр `base.json`, ротируемый логгер |
| **T3-02** | **Update Ingestion, Ed25519 & Compatibility Check** | REQ-S02, REQ-S03, REQ-S04, REQ-S12 | `src/mkp_server/importer.py`, `src/mkp_server/security.py`, `src/mkp_server/verifier.py` | Верификация Ed25519 (I13), проверка compatibility matrix (I14), прием монолитного Bookpack v0.3.0, `T1-delta` и `User-delta`, per-artifact sha256 |
| **T3-03** | **LanceDB Hybrid Search & E5 Embedder** | REQ-S05, REQ-C03 | `src/mkp_server/search.py` | Гибридный поиск по чанкам (`passage:`/`query:` префиксы, `multilingual-e5-large`, FTS, RRFReranker, top_k ≤ 20, фильтрация по `tier`, `book_id`, `lang`) |
| **T3-04** | **Knowledge Graph & Rules Store** | REQ-S06, REQ-R01..R04, REQ-S12 | `src/mkp_server/graph.py`, `src/mkp_server/rules_store.py` | NetworkX MultiDiGraph для триплетов + индекс правил `RuleStore` (поиск по `archetype`, `telemetry`, `domain`, `status`, `tier`, `region`, обработка `orphaned` правил) |
| **T3-05** | **WAL, Atomic Swap & Rollback Lifecycle** | REQ-S07 | `src/mkp_server/wal.py`, `src/mkp_server/lifecycle.py`, `src/mkp_server/rollback.py` | Журнал `apply.wal` с `fsync(dirname)`, `backup_verified` (I9), атомарная подмена `renameat2(RENAME_EXCHANGE)` / `mv` + `fsync`, авто-откат при сбое, ручной rollback (I5) |
| **T3-06** | **FastMCP Server & 10 Tools** | REQ-S08, REQ-S09, REQ-S12, REQ-S13 | `src/mkp_server/server.py` | 10 FastMCP инструментов (4 `documents/`, 5 `rules/`, 1 `system/get_bookpack_info`), изоляция T1 (read-only), защита от Path Traversal, `stdio` и `http://127.0.0.1:<port>` |
| **T3-07** | **Server CLI & Entry Points** | REQ-S01..S13, REQ-C02 | `src/mkp_server/cli.py`, `pyproject.toml` | Typer CLI (`mkp-server serve/import/rollback/verify/remove-book/list-books/query-rules/guardrails/info`), регистрация entrypoint |
| **T3-08** | **Automated Tests & Invariants Validation** | REQ-S01..S13 | `tests/test_server.py`, `tests/test_invariants.py` | Комплексные тесты инвариантов I0–I14 (откат при сбое apply, WAL-recovery после power-loss, Ed25519 отказ, проверка 10 MCP инструментов, orphaning) |

---

## Task Details

### T3-01: Storage Architecture & v0.3 Registry Manager (REQ-S01, REQ-S10, REQ-S11)
- Создание и управление структурой `/storage/`:
  ```
  <storage_dir>/
  ├── active/
  │   ├── server/                   # Активный бинарник / код сервера
  │   ├── bookpack/
  │   │   ├── manifest.yaml         # v0.3.0
  │   │   ├── checksums.sha256
  │   │   ├── signature.ed25519     # Подпись пакета
  │   │   ├── base/                 # T1 Base (chunks, triplets, claims, rules, guardrails.md)
  │   │   ├── yacht/                # T2 Yacht
  │   │   ├── voyage/               # T2.5 Voyage
  │   │   ├── personal/             # T3 Personal
  │   │   └── assets/               # PNG-диаграммы
  │   └── derived/                  # LanceDB таблицы и Graph
  ├── backup/                       # Резервная копия поколения N-1 (ровно 1 backup)
  │   ├── server/
  │   ├── bookpack/
  │   └── derived/
  ├── staging/                      # Изолированное применение обновлений / дельт
  ├── fallback/                     # R/O аварийный образ (SquashFS)
  ├── failed/                       # Сохранённые аварийные дампы для диагностики
  ├── logs/                         # mcp_server.log, recovery.log
  └── apply.wal                     # Write-Ahead Log транзакций
  ```
- Модели данных: `StorageConfig`, `BaseRegistry`, `BookRecord`, `GenerationManifest`, `BookpackInfo`.

### T3-02: Update Ingestion, Ed25519 & Compatibility Check (REQ-S02, REQ-S03, REQ-S04, REQ-S12)
- **Модуль безопасности (`security.py`):**
  - Проверка цифровой подписи Ed25519 (`signature.ed25519`) по зашитому публичному ключу сервиса (**Инвариант I13**). При ошибке подписи — немедленный отказ и логирование.
- **Матрица совместимости (`verifier.py`):**
  - Валидация блока `compatibility` манифеста до начала распаковки (**Инвариант I14**).
- **Импорт дельт и пакетов:**
  - Поддержка применения `T1-delta` (замена `base/` без повреждения пользовательских слоев).
  - Поддержка `User-delta` (обновление `yacht/`, `voyage/`, `personal/`).
  - Поддержка монолитных архивов Bookpack v0.3.0 (`.zip` и `.zst`).
  - Проверка per-artifact контрольных сумм SHA-256 (**Инвариант I3**).

### T3-03: LanceDB Hybrid Search & E5 Embedder (REQ-S05, REQ-C03)
- Инициализация `sentence-transformers` с моделью `intfloat/multilingual-e5-large` (dim=1024).
- Префиксы: `passage: ` при индексации, `query: ` при входящем запросе.
- Полнотекстовый индекс (FTS) по полям `text_content`, `ocr_text`, `vlm_description`.
- Гибридное ранжирование через `RRFReranker` (Dense + Sparse).
- Поддержка фильтрации по `tier` (`T1`, `T2`, `T2.5`, `T3`), `book_id` и `lang`. Ограничение `top_k ≤ 20`.

### T3-04: Knowledge Graph & Rules Store (REQ-S06, REQ-R01..R04, REQ-S12)
- **Knowledge Graph:**
  - Загрузка `triplets.jsonl` в `networkx.MultiDiGraph`.
  - Поиск связей с сохранением полной трассировки (`provenance`).
- **Rules Store & Orphaning:**
  - Загрузка правил и поддержка матчинга:
    - Фильтрация по `archetype`, домену (`safety`, `trim`, `reefing`, `maneuver`), региону.
    - Вычисление условий телеметрии (`tws`, `heel` и др.) с учетом `triggers_logic`.
  - **User-layer Orphaning:** если T1 обновлен, а чанк удален, связанные пользовательские правила получают флаг `orphaned=true` и отдаются с предупреждением, но не удаляются.
  - T1 удаленные чанки помечаются `deprecated=true` (tombstone) на 2 релиза.

### T3-05: WAL, Atomic Swap & Rollback Lifecycle (REQ-S07, Инварианты I0–I11)
- **Конвейер транзакции (`wal.py`, `lifecycle.py`):**
  1. Pre-flight check (место на диске ≥ 2× active + delta).
  2. Валидация подписи Ed25519 (I13) и compatibility (I14).
  3. WAL: `START apply`.
  4. Создание `backup/` и его валидация SHA-256 -> WAL: `backup_verified` (I3, I9).
  5. Применение дельты/пакета в `staging/` -> WAL: `staging_created`.
  6. Consistency check в `staging/` -> WAL: `consistency_ok`.
  7. Остановка сервера -> WAL: `server_stopped`.
  8. Atomic swap: `renameat2(RENAME_EXCHANGE)` / `mv` с обязательным `fsync` директорий.
  9. Запуск сервера и smoke-тест -> WAL: `DONE`.
- **Модуль отката (`rollback.py`):**
  - Автоматический откат при сбое smoke-теста к `backup/`.
  - Ручной откат одной кнопкой/командой при валидном backup (I5).
  - Поддержка 3-х сценариев при поврежденном backup (I5 / §B.6: рискованный откат / сброс base / factory reset).
  - Сохранение WAL после rollback для аудита (I10).
  - Recovery при старте после аварийного отключения питания (I7).

### T3-06: FastMCP Server & 10 Tools (REQ-S08, REQ-S09, REQ-S12, REQ-S13)
- Инициализация `FastMCP("mkp-server")`.
- Реализация **10 инструментов**:
  1. **`search_chunks(query: str, top_k: int = 5, tier: Optional[str] = None)`** — семантический гибридный поиск.
  2. **`get_diagram_image(doc_id: str, page: int)`** (и по `image_name`) — отдача PNG с защитой от Path Traversal.
  3. **`get_related_entities(entity_id: str)`** — граф связей сущности из NetworkX.
  4. **`get_book_manifest(doc_id: str)`** — метаданные документа и книги.
  5. **`query_rules(archetype: str, telemetry: dict[str, float], domain: Optional[str] = None, tier: Optional[Literal["T1", "T2", "T2.5"]] = None, region: Optional[str] = None, status: str = "approved")`** — применимые правила.
  6. **`get_rule(rule_id: str)`** — детальная карточка правила по его ID.
  7. **`get_rule_provenance(rule_id: str)`** — массив `RuleSource` с точными цитатами первоисточника.
  8. **`list_conflicts(rule_id: str)`** — список конфликтующих правил.
  9. **`get_guardrails()`** — отдача скомпилированного `guardrails.md` (≤ 8000 символов).
  10. **`get_bookpack_info()`** — системные метаданные (`generation`, версии `t1_version`, `t1_hash`, хеши `user_layers`, доступные обновления).
- **Изоляция:** Пользовательские MCP-инструменты строго read-only для слоя T1 (отсутствуют методы изменения T1).

### T3-07: Server CLI & Entry Points (REQ-S01..S13, REQ-C02)
- Команды CLI `mkp-server`:
  - `mkp-server serve --storage <PATH> [--transport stdio|http] [--port 8000]`
  - `mkp-server import <PACKAGE_PATH> --storage <PATH> [--replace]`
  - `mkp-server rollback --storage <PATH> [--mode auto|base-reset|factory]`
  - `mkp-server verify --storage <PATH>`
  - `mkp-server info --storage <PATH>`
  - `mkp-server remove-book <BOOK_ID> --storage <PATH> [--purge]`
  - `mkp-server query-rules --storage <PATH> --archetype <ARCHETYPE> --telemetry '{"tws": 24}'`
  - `mkp-server guardrails --storage <PATH>`

### T3-08: Automated Tests & Invariants Validation (REQ-S01..S13)
- Комплекс тестов в `tests/test_server.py` и `tests/test_invariants.py`:
  - `test_storage_init`: проверка создания структуры `/storage/`.
  - `test_ed25519_verification`: проверка подписи (I13), отказ при поврежденной подписи.
  - `test_compatibility_validation`: проверка совместимости схемы и версий (I14).
  - `test_wal_and_recovery`: эмуляция сбоя на каждом шаге конвейера и проверка восстановления (I0, I7, I9, I10).
  - `test_atomic_swap_and_rollback`: ручной и авто-откат к `backup/` и `fallback/` (I1, I5, I8, I11).
  - `test_mcp_10_tools`: проверка работы всех 10 инструментов FastMCP.
  - `test_orphaning_detection`: проверка пометки правил `orphaned=true` при модификации T1.

---

## Success Criteria (Критерии завершения Phase 3)
1. Сервер успешно управляет структурой `/storage/` и выполняет раздельный импорт дельт и пакетов v0.3.0.
2. Все 15 инвариантов надежности (I0–I14) верифицированы тестами: Ed25519 подпись, compatibility matrix, WAL с `fsync(dirname)`, `backup_verified`, атомарная подмена и rollback.
3. Все 10 MCP-инструментов возвращают валидные ответы согласно контрактам HLD v3.3.1.
4. Слой T1 полностью защищен от пользовательских модификаций.
5. Path Traversal атаки надежно блокируются.
6. Набор тестов `pytest tests/test_server.py tests/test_invariants.py` проходит со 100% успехом.
