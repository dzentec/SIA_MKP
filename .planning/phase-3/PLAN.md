# Phase 3: mkp-server — 4-Tier Knowledge Base, Rules Engine & 9 MCP Tools

**Phase Goal:** Полнофункциональный локальный сервер базы знаний и правил `mkp-server`: импорт архивов `.bookpack.zip` стандарта v0.2, blue-green пересборка гибридных индексов (LanceDB Chunks & Rules + NetworkX Graph), 9 инструментов FastMCP (пространства имен `documents/` и `rules/`), поддержка 4-уровневой модели контента (`T1: Base` 🟢 MVP, `T2: Yacht` 🟡 Stub, `T2.5: Voyage` 🟡 Stub, `T3: Personal` 🟡 Stub), статическая отдача Guardrails, безопасность (path traversal protection) и CLI управление.

**Source of Truth:** `HLD_MKP-R_v3.1_1of2.md` & `HLD_MKP-R_v3.1_2of2.md` (HLD v3.1, разделы 4, 7, 8, 13, 14), `REQUIREMENTS.md` (REQ-S01..REQ-S11, REQ-R01..REQ-R06).  
**Dependencies:** Phase 0 (PoC), Phase 1 (`mkp-builder` Core), Phase 2 (`mkp-builder` Triplets & Export), **Phase 2.1 (`mkp-builder` Rules Pipeline & Bookpack v0.2)**.

---

## Tasks Breakdown

| # | Task | Requirements | Deliverables | Checkpoint |
|---|------|--------------|--------------|------------|
| **T3-01** | **Base Directory & v0.2 Registry Manager** | REQ-S01, REQ-S10, REQ-S11 | `src/mkp_server/base.py`, `src/mkp_server/models.py` | Создание и валидация структуры базы (`base.json`, `books/`, `pack/` со слоями `base/`, `yacht/`, `voyage/`, `personal/`, `derived/`, `inbox/`, `logs/`), ротируемый логгер |
| **T3-02** | **Bookpack v0.2 Ingestion & Pack Merger** | REQ-S01, REQ-S02, REQ-S03, REQ-S04 | `src/mkp_server/importer.py`, `src/mkp_server/verifier.py` | Импорт `.bookpack.zip` v0.2 с валидацией `checksums.sha256` и `manifest.yaml`, слияние chunks, triplets, claims, rules, guardrails; `remove-book`, `verify` |
| **T3-03** | **LanceDB Hybrid Search & Embedder** | REQ-S05, REQ-C03 | `src/mkp_server/search.py` | Гибридный поиск по чанкам (`passage:`/`query:` префиксы, `multilingual-e5-large`, FTS, RRFReranker, top_k ≤ 20, фильтрация по `tier`, `book_id`, `lang`) |
| **T3-04** | **Knowledge Graph & Rules Store** | REQ-S06, REQ-R01..R04 | `src/mkp_server/graph.py`, `src/mkp_server/rules_store.py` | NetworkX MultiDiGraph для триплетов + индекс правил `RuleStore` (поиск по `archetype`, `telemetry`, `domain`, `status`, `tier`, `region`) |
| **T3-05** | **Blue-Green Index Lifecycle & Atomic Swap** | REQ-S07 | `src/mkp_server/lifecycle.py` | Фоновая пересборка индексов в `derived_new/`, смоук-тест (поиск + rules), атомарная смена `derived_new/` → `derived/` с in-memory hot reload |
| **T3-06** | **FastMCP Server & 9 Tools (Documents + Rules)** | REQ-S08, REQ-S09 | `src/mkp_server/server.py` | 9 FastMCP инструментов (4 `documents/`, 5 `rules/`), контракты Stub для T2/T2.5/T3 (возврат `[]`), защита от Path Traversal, `stdio` и `http://127.0.0.1:<port>` |
| **T3-07** | **Server CLI & Entry Points** | REQ-S01..S11, REQ-C02 | `src/mkp_server/cli.py`, `pyproject.toml` | Typer CLI (`mkp-server serve/import/remove-book/verify/list-books/query-rules/guardrails`), регистрация entrypoint |
| **T3-08** | **Automated Tests & Contract Validation** | REQ-S01..S11, REQ-R01..R06 | `tests/test_server.py` | Сквозные тесты: импорт v0.2 → проверка 9 MCP-инструментов, stub-поведение, поиск правил, компиляция guardrails, blue-green пересборка |

---

## Task Details

### T3-01: Base Directory & v0.2 Registry Manager (REQ-S01, REQ-S10, REQ-S11)
- Создание файловой структуры базы под 4-уровневую модель контента:
  ```
  <base_dir>/
  ├── base.json                 # Реестр книг, топик, версия схемы v0.2, модель эмбеддингов
  ├── inbox/                    # Хранилище исходных .bookpack.zip архивов
  ├── books/                    # Распакованные данные книг
  │   └── <book_id>/
  ├── pack/                     # Объединенный слой для пересборки индексов
  │   ├── manifest.yaml
  │   ├── checksums.sha256
  │   ├── base/                 # T1 Base
  │   │   ├── chunks.jsonl
  │   │   ├── triplets.jsonl
  │   │   ├── claims.jsonl
  │   │   ├── rules.jsonl
  │   │   └── guardrails.md
  │   ├── yacht/                # T2 Yacht (stub [])
  │   ├── voyage/               # T2.5 Voyage (stub [])
  │   ├── personal/             # T3 Personal (stub [])
  │   └── assets/               # PNG-диаграммы
  ├── derived/                  # Текущие активные индексы LanceDB (chunks, rules) и Graph
  ├── derived_new/              # Временная папка сборки (blue-green)
  └── logs/
      └── mcp_server.log        # Ротируемый лог 10 МБ x 5
  ```
- Модели данных: `BaseRegistry`, `BookRecord`, `BuildInfo`, `ImportResult`.

### T3-02: Bookpack v0.2 Ingestion & Pack Merger (REQ-S01, REQ-S02, REQ-S03, REQ-S04)
- **Импорт:**
  - Валидация `checksums.sha256` и `manifest.yaml` из архива.
  - Проверка совместимости `bookpack_version` ("0.2.x") и `embed_model`.
  - Распаковка книги в `books/<book_id>/`.
  - Сохранение копии архива в `inbox/`.
  - Слияние слоёв `base/`, `yacht/`, `voyage/`, `personal/` всех книг в объединённый слой `pack/`.
  - Коды возврата CLI: `0` (успех), `3` (несовместимая схема), `4` (книга уже существует без `--replace`), `5` (ошибка контрольной суммы), `6` (внутренняя ошибка).
- **Удаление книги (`remove-book`):**
  - Удаление `books/<book_id>/`, удаление из `base.json`, опциональное удаление архива из `inbox/` (`--purge`).
  - Полный пересбор слоя `pack/`.
- **Автономный `verify`:**
  - Проверка контрольных сумм в `pack/manifest.yaml` и целостности индексов в `derived/`.

### T3-03: LanceDB Hybrid Search & E5 Embedder (REQ-S05, REQ-C03)
- Инициализация `sentence-transformers` с моделью `intfloat/multilingual-e5-large` (dim=1024).
- Префиксы: `passage: ` при индексации, `query: ` при входящем запросе.
- Полнотекстовый индекс (FTS) по полям `text_content`, `ocr_text`, `vlm_description`.
- Гибридное ранжирование через `RRFReranker` (Dense + Sparse).
- Поддержка фильтрации по `tier` (`T1`, `T2`, `T2.5`, `T3`), `book_id` и `lang`. Ограничение `top_k ≤ 20`.

### T3-04: Knowledge Graph & Rules Store (REQ-S06, REQ-R01..R04)
- **Knowledge Graph:**
  - Загрузка `triplets.jsonl` в `networkx.MultiDiGraph`.
  - Индексация сущностей и поиск отношений (1-hop, 2-hop) с provenance (`doc_id`, `page`, `chunk_id`, `location_ref`).
- **Rules Store:**
  - Загрузка `rules.jsonl` в `RuleStore` (с поддержкой векторного поиска по эмбеддингам правил).
  - Реализация матчинга правил по условиям:
    - Фильтрация по `archetype` (соответствие архетипу судна).
    - Вычисление триггеров: `telemetry` (например, `tws >= 22.0`, `heel >= 25.0`) с учетом `triggers_logic` (`ALL`/`ANY`).
    - Фильтрация по `domain` (`safety`, `trim`, `reefing`, `maneuver`), `status` (`approved`) и `region`.
  - Stub-логика: если `tier` в (`T2`, `T2.5`) — возврат `[]`.

### T3-05: Blue-Green Index Lifecycle (REQ-S07)
- Построение таблиц LanceDB (`chunks`, `rules`) и графа NetworkX в каталоге `derived_new/`.
- Выполнение смоук-теста: 1 гибридный поиск по чанкам + 1 запрос к `query_rules` + 1 запрос к графу.
- При успехе: атомарный своп каталогов (`derived_new/` → `derived/`) и горячее обновление указателей в памяти.
- При сбое: очистка `derived_new/`, логирование ошибки, активный сервер продолжает обслуживать запросы без сбоев.

### T3-06: FastMCP Server & 9 Tools (REQ-S08, REQ-S09)
- Инициализация `FastMCP("mkp-server")`.
- Реализация **9 инструментов**:
  1. **`search_chunks(query: str, top_k: int = 5, tier: Optional[str] = None)`** — семантический гибридный поиск (алиас `search_maritime_knowledge` сохранен).
  2. **`get_diagram_image(doc_id: str, page: int)`** (и по `image_name`) — отдача PNG с проверкой по манифесту и строгой блокировкой Path Traversal.
  3. **`get_related_entities(entity_id: str)`** — граф связей сущности из NetworkX.
  4. **`get_book_manifest(doc_id: str)`** — метаданные документа и книги.
  5. **`query_rules(archetype: str, telemetry: dict[str, float], domain: Optional[str] = None, tier: Optional[Literal["T1", "T2", "T2.5"]] = None, region: Optional[str] = None, status: str = "approved")`** — применимые правила для советника (MVP: T1; Stub: T2/T2.5 возвращают `[]`).
  6. **`get_rule(rule_id: str)`** — детальная карточка правила по его ID.
  7. **`get_rule_provenance(rule_id: str)`** — массив `RuleSource` с точными цитатами первоисточника.
  8. **`list_conflicts(rule_id: str)`** — список конфликтующих правил.
  9. **`get_guardrails()`** — отдача скомпилированного `guardrails.md` (≤ 8000 символов).
- Поддержка транспортов: `stdio` (по умолчанию) и `http` (`streamable-http`, строго `127.0.0.1:<port>`).

### T3-07: Server CLI & Entry Points (REQ-S01..S11, REQ-C02)
- Команды CLI `mkp-server`:
  - `mkp-server serve --base <PATH> [--transport stdio|http] [--port 8000]`
  - `mkp-server import <ZIP_PATH> --base <PATH> [--topic "Topic"] [--replace]`
  - `mkp-server remove-book <BOOK_ID> --base <PATH> [--yes] [--purge]`
  - `mkp-server verify --base <PATH>`
  - `mkp-server list-books --base <PATH>`
  - `mkp-server query-rules --base <PATH> --archetype <ARCHETYPE> --telemetry '{"tws": 24}'`
  - `mkp-server guardrails --base <PATH>`
- Регистрация CLI команды в `pyproject.toml`.

### T3-08: Automated Tests & Contract Validation (REQ-S01..S11, REQ-R01..R06)
- Комплекс тестов в `tests/test_server.py`:
  - `test_base_init_v02`: инициализация структуры 4-уровневой базы.
  - `test_import_v02_archive`: импорт `.bookpack.zip` v0.2, проверка валидации `checksums.sha256`.
  - `test_hybrid_search_chunks`: проверка поиска чанков с префиксами `query:`/`passage:`.
  - `test_mcp_query_rules_t1`: проверка матчинга правил T1 по телеметрии.
  - `test_mcp_rules_stub_t2_t25`: проверка, что T2/T2.5 возвращают корректный `[]`.
  - `test_mcp_guardrails`: отдача static guardrails.
  - `test_path_traversal_protection`: блокировка атак path traversal в `get_diagram_image`.
  - `test_blue_green_lifecycle`: непрерывность обслуживания при пересборке базы.

---

## Success Criteria (Критерии завершения Phase 3)
1. `mkp-server import work/demo/out/book.bookpack.zip --base work/marine_base` завершается с кодом 0; база и индексы (векторный, граф, rules) созданы.
2. Все 9 MCP-инструментов возвращают валидные ответы согласно контрактам HLD v3.1.
3. `query_rules` корректно находит T1 правила по телеметрии и контексту, а для T2/T2.5 возвращает `[]`.
4. `get_guardrails` возвращает валидный текст системного промпта guardrails (≤ 8000 символов).
5. `get_diagram_image` отдает PNG и надежно блокирует Path Traversal атаки.
6. Blue-green ребилд корректно переключает индексы без падения сервера.
7. Все тесты `pytest tests/test_server.py` проходят со 100% успехом.
