# Phase 3: mkp-server — Database, Indexing & FastMCP Server

**Phase Goal:** Полнофункциональный локальный сервер базы знаний `mkp-server`: импорт `.bookpack.zip` архивов, blue-green пересборка гибридных индексов (LanceDB + NetworkX Graph), 5 инструментов FastMCP (`search_maritime_knowledge`, `get_diagram_image`, `get_entity_relations`, `read_page_context`, `list_books`), безопасность (path traversal protection), CLI управление и версионирование.

**Source of Truth:** `HLD_Tools_MCP_v1.5.md` (раздел 7, 8, 9), `REQUIREMENTS.md` (REQ-S01..REQ-S11, REQ-C02..REQ-C04).  
**Dependencies:** Phase 0 (PoC), Phase 1 (`mkp-builder` Core), Phase 2 (`mkp-builder` Export & Triplets).

---

## Tasks Breakdown

| # | Task | Requirements | Deliverables | Checkpoint |
|---|------|--------------|--------------|------------|
| **T3-01** | **Base Directory & Registry Manager** | REQ-S01, REQ-S10, REQ-S11 | `src/mkp_server/base.py`, `src/mkp_server/models.py` | Создание и валидация структуры базы (`base.json`, `books/`, `pack/`, `derived/`, `inbox/`, `logs/`), ротируемый логгер сервера |
| **T3-02** | **Archive Ingestion, Pack Merger & Verification** | REQ-S01, REQ-S02, REQ-S03, REQ-S04 | `src/mkp_server/importer.py`, `src/mkp_server/verifier.py` | Импорт `.bookpack.zip` с проверкой SHA-256, слияние в `pack/`, удаление книги (`remove-book`), автономный `verify` без запуска сервиса |
| **T3-03** | **LanceDB Hybrid Search & E5 Embedder** | REQ-S05, REQ-C03 | `src/mkp_server/search.py` | Гибридный поиск в LanceDB (`passage:`/`query:` префиксы, `multilingual-e5-large`, FTS, RRFReranker, top_k ≤ 20, фильтрация по `book_id` и `lang`) |
| **T3-04** | **Knowledge Graph Engine (GraphRAG)** | REQ-S06 | `src/mkp_server/graph.py` | Загрузка `triplets.jsonl` в граф NetworkX, многошаговый поиск связей, поиск смежных сущностей по типам |
| **T3-05** | **Blue-Green Index Lifecycle & Atomic Swap** | REQ-S07 | `src/mkp_server/lifecycle.py` | Фоновая пересборка индексов в `derived_new/`, смоук-тест, атомарная смена `derived_new/` → `derived/` с горячей перезагрузкой в памяти |
| **T3-06** | **FastMCP Tools & Transports** | REQ-S08, REQ-S09 | `src/mkp_server/server.py` | 5 инструментов FastMCP с валидацией Pydantic, строгая защита `get_diagram_image` от Path Traversal, поддержка `stdio` и `http://127.0.0.1:<port>` |
| **T3-07** | **Server CLI & Entry Points** | REQ-S01..S11, REQ-C02 | `src/mkp_server/cli.py`, `pyproject.toml` | Typer CLI (`mkp-server serve/import/remove-book/verify/list-books`), регистрация CLI команды `mkp-server` |
| **T3-08** | **Automated Tests & Contract Validation** | REQ-S01..S11 | `tests/test_server.py` | Сквозные тесты: сборка в билдере → импорт архива → проверка поиска, графа, картинок через FastMCP и пересборки blue-green |

---

## Task Details

### T3-01: Base Directory & Registry Manager (REQ-S01, REQ-S10, REQ-S11)
- Создание канонической файловой структуры базы:
  ```
  <base_dir>/
  ├── base.json                 # Реестр книг, топик, версия схемы 1.5, модель эмбеддингов
  ├── inbox/                    # Хранилище исходных .bookpack.zip архивов
  ├── books/                    # Распакованные канонические данные книг
  │   └── <book_id>/
  ├── pack/                     # Объединенный слой для пересборки индексов
  │   ├── pack_manifest.json
  │   ├── chunks.jsonl
  │   ├── pages.jsonl
  │   ├── triplets.jsonl
  │   └── assets/
  ├── derived/                  # Текущие активные индексы LanceDB и Graph
  ├── derived_new/              # Временная папка сборки (blue-green)
  └── logs/
      └── mcp_server.log        # Ротируемый лог 10 МБ x 5
  ```
- Модели данных: `BaseRegistry`, `BookRecord`, `BuildInfo`, `ImportResult`.

### T3-02: Ingestion, Pack Merger & Verification (REQ-S02, REQ-S03, REQ-S04)
- **Импорт:**
  - Валидация `files_sha256` из `bookpack.json` в архиве.
  - Проверка совместимости `schema_version` (1.x) и `embed_model`.
  - Распаковка книги в `books/<book_id>/`.
  - Сохранение копии архива в `inbox/`.
  - Слияние файлов всех зарегистрированных книг в единый слой `pack/`.
  - Коды возврата CLI: `0` (успех), `3` (несовместимая схема), `4` (книга уже существует без `--replace`), `5` (ошибка SHA-256), `6` (внутренняя ошибка).
- **Удаление книги (`remove-book`):**
  - Удаление `books/<book_id>/`, удаление из `base.json`, опциональное удаление архива из `inbox/` (`--purge`).
  - Полный пересбор `pack/`.
- **Автономный `verify`:**
  - Проверка контрольных сумм в `pack/pack_manifest.json` и целостности индексов в `derived/`.

### T3-03: LanceDB Hybrid Search & E5 Embedder (REQ-S05, REQ-C03)
- Инициализация `sentence-transformers` с моделью `intfloat/multilingual-e5-large` (dim=1024).
- Обязательное форматирование префиксов:
  - `passage: ` при индексации чанков в `pack/chunks.jsonl`.
  - `query: ` при входящем поисковом запросе.
- Полнотекстовый индекс (FTS) по полям `text_content`, `ocr_text`, `vlm_description`.
- Гибридное ранжирование через `RRFReranker` с объединением Dense и Sparse скоринга.
- Фильтрация по `book_id` и `lang`, ограничение `top_k ≤ 20`.

### T3-04: Knowledge Graph Engine (REQ-S06)
- Загрузка графа связей из `pack/triplets.jsonl` в `networkx.MultiDiGraph`.
- Индексация узлов по каноническим именам и синонимам.
- Извлечение отношений:
  - Прямые и входящие связи сущности (`entity_name`).
  - 2-hop окрестность с фильтрацией по типам сущностей (Парус, Снасть, Манёвр, Узел, Опасность).
  - Provenance атрибуты (источник книги, номер страницы, `location_ref`).

### T3-05: Blue-Green Index Lifecycle (REQ-S07)
- Построение LanceDB таблицы и графа в каталоге `derived_new/`.
- Выполнение смоук-теста (1 тестовый векторный запрос и 1 графовый запрос).
- При успехе:
  - Переименование `derived/` -> `derived_old/`.
  - Переименование `derived_new/` -> `derived/`.
  - Удаление `derived_old/`.
  - Горячее обновление ссылок на индексы в запущенном экземпляре сервера (in-memory atomic switch).
- При сбое: очистка `derived_new/`, возврат ошибки, активная база продолжает работу без деградации.

### T3-06: FastMCP Server & 5 Tools (REQ-S08, REQ-S09)
- Инициализация `FastMCP("mkp-server")`.
- Реализация 5 инструментов:
  1. `search_maritime_knowledge(query, book_id=None, lang=None, top_k=5)` -> структурированный `SearchResponse` с чанками, текстом и связанными диаграммами.
  2. `get_diagram_image(image_name)` -> бинарные данные PNG изображения с валидацией имени по манифесту `pack/` и жесткой защитой от Path Traversal (блокировка `..`, `/`, `\`).
  3. `get_entity_relations(entity_name)` -> граф связей сущности.
  4. `read_page_context(book_id, page_number, location_ref=None)` -> полный текст и ассеты страницы.
  5. `list_books()` -> список доступных книг с метаданными и количеством чанков/схем.
- Поддержка транспортов: `stdio` (по умолчанию) и `http` (`streamable-http`, строго `127.0.0.1:<port>`).

### T3-07: Server CLI & Entry Points (REQ-S01..S11, REQ-C02)
- Команды CLI `mkp-server`:
  - `mkp-server serve --base <PATH> [--transport stdio|http] [--port 8000]`
  - `mkp-server import <ZIP_PATH> --base <PATH> [--topic "Topic"] [--replace]`
  - `mkp-server remove-book <BOOK_ID> --base <PATH> [--yes] [--purge]`
  - `mkp-server verify --base <PATH>`
  - `mkp-server list-books --base <PATH>`
- Конфигурация `pyproject.toml` с entry point `mkp-server = "mkp_server.cli:app"`.

### T3-08: Automated Tests & Contract Validation (REQ-S01..S11)
- Комплекс юнит- и интеграционных тестов в `tests/test_server.py`:
  - `test_base_init_and_registry`: корректность создания структуры.
  - `test_import_and_verification`: импорт `.bookpack.zip`, отказ при битом SHA-256.
  - `test_hybrid_search_e5`: проверка `query:` / `passage:` поиска.
  - `test_knowledge_graph_queries`: проверка 1-hop и 2-hop запросов.
  - `test_path_traversal_protection`: атаки `../../secret.txt`, `%2e%2e/` должны возвращать ошибку.
  - `test_blue_green_swap`: проверка непрерывности обслуживания при ребилде.
  - `test_remove_book`: удаление и автоматический пересбор.

---

## Success Criteria (Критерии завершения Phase 3)
1. `mkp-server import work/demo/out/dedekam_seamanship.bookpack.zip --base work/marine_base --topic "Морское дело"` завершается с кодом 0, база и индексы созданы.
2. `search_maritime_knowledge` находит релевантные чанки по запросам из Golden Dataset.
3. `get_diagram_image` корректно отдает PNG схем и блокирует Path Traversal.
4. Blue-green ребилд корректно переключает `derived_new` -> `derived` после смоук-теста.
5. `remove-book` корректно очищает базу и пересобирает индексы.
6. Все 100% тестов проходят (`pytest tests/ -v`).
