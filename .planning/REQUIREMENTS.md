# REQUIREMENTS — Maritime Knowledge Pack (MKP) v1

**Source:** HLD v1.5 (`HLD_Tools_MCP_v1.5.md`)  
**Scope:** v1 = все требования из раздела 13 (Phase 0–4) считаются обязательными для v1

---

## Продукт 1: `mkp-builder`

### REQ-B01 — Layout Parsing
Парсить PDF/EPUB/DOCX через Docling ≥ 2.15 с `generate_picture_images=True`, `images_scale=2.0`. Именование ассетов: `{book_id}_p{page_num}_fig{idx}.png`. Таблицы экспортировать в Markdown с привязкой к странице.
**Scope:** v1

### REQ-B02 — OCR Routing (профили фонда)
Поддержать три профиля: `digital` (OCR отключён), `scanned` (full-page OCR), `mixed` (автоопределение по текстовой плотности). OCR-движок конфигурируемый: RapidOCR / Tesseract `rus+eng`. Итоговый движок фиксируется в `book_metadata.json`.
**Scope:** v1

### REQ-B03 — VLM Annotation (union-схема)
Аннотировать каждую фигуру через Ollama (qwen2.5vl:7b, Q4_K_M). Таксономия: `maneuver | knot | equipment | polar | map | table_figure | other`. Discriminated union JSON (Pydantic). Кэш по ключу SHA-256(image) + model_tag + prompt_ver. Таймаут 45 с, num_predict: 512, OLLAMA_FLASH_ATTENTION=1.
**Scope:** v1

### REQ-B04 — Трёхступенчатая верификация (100 %)
1. Pydantic schema-валидация каждого VLM-ответа.
2. Текстовая согласованность (LLM, 100 %).
3. Визуальный критик (та же VLM, num_predict: 96, 100 %).
`needs_review=true` → типизированный блок обнуляется, схема в `qa_review_queue.jsonl`.
Верификация кэшируется. Acceptance gate: `needs_review ≤ 5 %`.
**Scope:** v1

### REQ-B05 — Chunking (section/table-aware)
max_tokens=512, overlap=64. Таблицы — отдельные чанки. `lang` чанка = язык доминирующего текста. `location_ref` для каждого чанка (pdf:pN / docx:pN / epub:sN#anchor).
**Scope:** v1

### REQ-B06 — Triplet Extraction (GraphRAG)
Извлечение триплетов через текстовую модель Ollama (qwen2.5:7b). Таксономия сущностей: Парус, Снасть, Манёвр, ВетровойРежим, Узел, Опасность. Отношения: УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ, ТРЕБУЕТ_ДЕЙСТВИЯ, ПРИМЕНЯЕТСЯ_ПРИ, СВЯЗАН_С. Нормализация + дедупликация. Provenance: book_id, page_number, chunk_id, location_ref.
**Scope:** v1

### REQ-B07 — Экспорт `.bookpack.zip`
Упаковать: bookpack.json (schema_version: "1.5"), book_metadata.json, pages.jsonl, chunks.jsonl, triplets.jsonl, qa_review_queue.jsonl, assets/. Манифест `files_sha256`. Индексы **не** строить.
**Scope:** v1

### REQ-B08 — TUI (rich) + логирование
Прогресс-бары для каждого этапа (Parse/OCR/Figures/VLM/Verify/Chunks/Triplets) со счётчиками, кэш-попаданиями, ETA, `needs_review`-флагом. Файловый лог: `work/logs/builder_<ts>.log` (DEBUG), 10 последних. `ingest_report.md` по завершении. `--headless` режим.
**Scope:** v1

### REQ-B09 — Идемпотентность и кэширование
Повторный запуск на той же книге не вызывает модели заново (кэш по ключу). `--force` сбрасывает кэш.
**Scope:** v1

### REQ-B10 — CLI
`mkp-builder build --book <файл> --profile <digital|scanned|mixed> --lang <ru|en|mixed> --out <папка> [--force] [--headless]`  
`mkp-builder export --book-id <id> --out <папка>`
**Scope:** v1

---

## Продукт 2: `mkp-server`

### REQ-S01 — Структура базы
Создать и поддерживать структуру: `base.json` (реестр), `books/` (каноника по книгам), `pack/` (объединённый слой), `derived/` (активные индексы), `derived_new/` (временные при пересборке), `inbox/` (архивы).
**Scope:** v1

### REQ-S02 — Импорт `.bookpack.zip`
Валидация (files_sha256, schema_version-мажор, embed_model). Дедупликация по book_id (--replace). Распаковка в `books/<book_id>/`. Слияние `pack/`. Пересборка индексов в `derived_new/` (blue-green). Коды выхода: 0, 3, 4, 5, 6.
**Scope:** v1

### REQ-S03 — Удаление книги (`remove-book`)
Проверить наличие, показать объём удаления, подтвердить (или --yes). Пересборка pack/ и индексов blue-green. По умолчанию архив остаётся в inbox/; --purge удаляет. Код 4 если book_id не найден.
**Scope:** v1

### REQ-S04 — Verify
`mkp-server verify --base <путь>` — проверить манифест pack/ и build_info.json без запуска сервиса.
**Scope:** v1

### REQ-S05 — Эмбеддинг и гибридный поиск (LanceDB)
Модель: `intfloat/multilingual-e5-large` (dim=1024). Обязательные префиксы: `passage:` при индексации, `query:` при запросе. FTS по полям text_content, ocr_text, vlm_description. RRFReranker. Лимит top_k ≤ 20. Фильтры по book_id и lang.
**Scope:** v1

### REQ-S06 — Граф знаний (LadybugDB)
Построение из `triplets.jsonl` при пересборке. Только параметризованные Cypher-запросы. Fallback: `triplets.jsonl` + NetworkX при недоступности LadybugDB.
**Scope:** v1

### REQ-S07 — Blue-green пересборка индексов
Во время пересборки MCP отдаёт старую базу из `derived/`. Переключение атомарное после смоук-теста (1 запрос). При сбое — откат. Политика: всегда полный ребилд из `pack/`.
**Scope:** v1

### REQ-S08 — MCP-инструменты (5 штук)
- `search_maritime_knowledge(query, book_id?, lang?, top_k=5)` → SearchResponse
- `get_diagram_image(image_name)` → Image (PNG); защита от path traversal
- `get_entity_relations(entity_name)` → list[dict]
- `read_page_context(book_id, page_number, location_ref?)` → PageContext
- `list_books()` → list[dict]
Все вызовы логируются.
**Scope:** v1

### REQ-S09 — Транспорты
По умолчанию stdio. `--transport http --port N` — streamable-http, строго 127.0.0.1.
**Scope:** v1

### REQ-S10 — Множественные тематики
Одна база = одна тематика. Первый импорт задаёт модель эмбеддинга и тему (`--topic`). Разные тематики → разные базы → разные экземпляры сервера.
**Scope:** v1

### REQ-S11 — Логирование сервера
`<база>/logs/mcp_server.log`, RotatingFileHandler 10 МБ × 5. INFO. Формат: `%(asctime)s %(levelname)s [%(stage)s] %(message)s`.
**Scope:** v1

---

## Общее / Инфраструктура

### REQ-C01 — Общий модуль `mkp-common`
Pydantic-модели (chunks, pages, triplets, bookpack), location_ref утилиты, валидация манифестов, логирование.
**Scope:** v1

### REQ-C02 — pyproject.toml
Один репозиторий, два entry-point: `mkp-builder` и `mkp-server`. Две группы зависимостей: `.[builder]` и `.[server]`.
**Scope:** v1

### REQ-C03 — Двуязычность
Поддержка ru/en на всех уровнях (книга/страница/чанк). `terms` в VLM-ответе всегда двуязычный. Кросс-языковый поиск через multilingual-e5-large.
**Scope:** v1

### REQ-C04 — Windows 11 офлайн
Длинные пути включены. Пути в конфигурации MCP — абсолютные. После однократной загрузки весов — 100 % офлайн.
**Scope:** v1

---

## Phase 0 — PoC (обязательные проверки перед Phase 1)

### REQ-P0-01 — Docling figure crop
Кроп схем (scale=2.0) на 1 главе PDF, включая векторную графику. Качество и полнота.
**Scope:** v1 (PoC)

### REQ-P0-02 — VLM стабильность
qwen2.5vl:7b: JSON-режим, отсутствие зацикливания, OLLAMA_FLASH_ATTENTION=1. Точность diagram_type ≥ 0.95 на сэмпле ≥ 10 изображений каждого из 7 типов. Неприменимые блоки = null.
**Scope:** v1 (PoC)

### REQ-P0-03 — LanceDB FTS кириллица
Проверка токенизации кириллицы. При неудовлетворительном результате — ngram-токенизатор.
**Scope:** v1 (PoC)

### REQ-P0-04 — e5-large RU↔EN
Качество эмбеддингов с/без префиксов query:/passage: на RU↔EN парах.
**Scope:** v1 (PoC)

### REQ-P0-05 — OCR кириллицы
Сравнение RapidOCR vs Tesseract `rus+eng` на скане. Выбор движка.
**Scope:** v1 (PoC)

### REQ-P0-06 — LadybugDB Windows/Python 3.11
Колёса доступны. Реальные Cypher-запросы: CRUD, параметризованный MATCH, чтение после перезаписи.
**Scope:** v1 (PoC)

### REQ-P0-07 — EPUB геометрия
Карта спайна, привязка фигур, виртуальная нумерация страниц.
**Scope:** v1 (PoC)

---

## QA & Acceptance

### REQ-QA-01 — Golden Dataset
30 вопросов со стратификацией: ≥1 на каждый diagram_type, ≥1 по скану, ≥1 по EPUB, запросы RU и EN, ≥3 графовых вопроса.
**Scope:** v1

### REQ-QA-02 — Метрики приёмки
- needs_review ≤ 5 % после первичного прогона
- Ручной разбор вся очередь qa_review_queue + выборка 50 схем → 0 % критических галлюцинаций
- Точность триплетов ≥ 0.90 (выборка 50)
- Recall@5 ≥ 0.90; Figure-Hit-Rate ≥ 0.95
**Scope:** v1
