# ROADMAP — Maritime Knowledge Pack (MKP) v1

**5 phases** | **34 requirements mapped** | All v1 requirements covered ✅

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 0 | PoC & Validation | Закрыть все технические риски до начала основной разработки | REQ-P0-01..07 | 7 |
| 1 | mkp-builder Core | Парсинг + VLM + верификация + чанкинг + TUI | REQ-B01..05, B08..09, C01..02, C03..04 | 5 |
| 2 | mkp-builder Complete | Триплеты + экспорт артефакта + Golden Dataset | REQ-B06..07, B10, QA-01 | 4 |
| 3 | mkp-server | База + импорт/удаление + индексация + MCP-инструменты | REQ-S01..11 | 6 |
| 4 | QA & Acceptance | Сквозной прогон Golden Dataset + ручной аудит | REQ-QA-02 | 5 |

---

## Phase 0: PoC & Validation
**Goal:** Проверить все технические риски из HLD §14 перед началом основной разработки. Без Phase 0 Phase 1 начинать нельзя.  
**Mode:** spike  
**Duration:** 0.5–1 день

**Requirements:** REQ-P0-01, REQ-P0-02, REQ-P0-03, REQ-P0-04, REQ-P0-05, REQ-P0-06, REQ-P0-07

**Success Criteria:**
1. Docling crop: фигуры извлекаются корректно (PNG, scale=2.0), включая векторную графику
2. qwen2.5vl:7b: diagram_type точность ≥ 0.95 на сэмпле, JSON стабилен, нет зацикливания
3. LanceDB FTS: кириллица токенизируется приемлемо (или выбран ngram)
4. e5-large: качество поиска RU↔EN с prefix `query:`/`passage:` подтверждено
5. RapidOCR vs Tesseract: OCR-движок выбран, зафиксирован в конфиге
6. LadybugDB: колёса под Windows/Python 3.11 установлены, Cypher-запросы работают
7. EPUB: карта спайна строится, фигуры привязаны к spine_index

---

## Phase 1: mkp-builder — Core Pipeline
**Goal:** Рабочий конвейер парсинг → VLM-аннотация → трёхступенчатая верификация → чанкинг с TUI и логированием. Выход: `chunks.jsonl` + `pages.jsonl` + ассеты.  
**Mode:** standard  
**Duration:** 2.5–3 дня (с буфером)  
**UI hint:** no

**Requirements:** REQ-B01, REQ-B02, REQ-B03, REQ-B04, REQ-B05, REQ-B08, REQ-B09, REQ-C01, REQ-C02, REQ-C03, REQ-C04

**Success Criteria:**
1. `mkp-builder build --book <pdf> --profile digital --lang en --out ./work` завершается без ошибок
2. TUI отображает все 7 прогресс-баров с корректными счётчиками и ETA
3. Верификация покрывает 100 % фигур; `needs_review ≤ 5 %` на тестовой книге
4. Кэш работает: повторный запуск той же книги не вызывает VLM/OCR
5. `chunks.jsonl` содержит корректные location_ref, section_path, visual_assets с VLM-данными

---

## Phase 2: mkp-builder — Triplets & Export
**Goal:** Экстракция триплетов, сборка `.bookpack.zip` с манифестом, финализация CLI. Параллельно — подготовка Golden Dataset (30 вопросов).  
**Mode:** standard  
**Duration:** 2 дня  
**UI hint:** no

**Requirements:** REQ-B06, REQ-B07, REQ-B10, REQ-QA-01

**Success Criteria:**
1. `mkp-builder build ...` создаёт валидный `.bookpack.zip` с bookpack.json schema_version "1.5"
2. `files_sha256` в манифесте совпадают с реальными файлами архива
3. `triplets.jsonl` содержит корректные триплеты с provenance (book_id, chunk_id, location_ref)
4. Golden Dataset: 30 вопросов со стратификацией по diagram_type, языку, формату книги

---

## Phase 3: mkp-server
**Goal:** Полнофункциональный сервер: импорт архивов, blue-green пересборка индексов (LanceDB + LadybugDB), 5 MCP-инструментов, verify, remove-book.  
**Mode:** standard  
**Duration:** 2 дня  
**UI hint:** no

**Requirements:** REQ-S01, REQ-S02, REQ-S03, REQ-S04, REQ-S05, REQ-S06, REQ-S07, REQ-S08, REQ-S09, REQ-S10, REQ-S11

**Success Criteria:**
1. `mkp-server import <zip> --base C:\marine_base --topic "Морское дело"` — успешный импорт (код 0), индексы построены
2. MCP-инструмент `search_maritime_knowledge` возвращает релевантные чанки с text_snippet и associated_images
3. `get_diagram_image` возвращает PNG; path traversal атака (../../etc/passwd) возвращает ошибку
4. Blue-green: во время пересборки `mkp-server --base` продолжает отвечать на запросы
5. `remove-book` корректно удаляет книгу и пересобирает индексы
6. Контрактный тест: билдер собирает архив → сервер импортирует → смоук-запросы через MCP

---

## Phase 4: QA & Acceptance
**Goal:** Сквозной прогон Golden Dataset через `mkp-server`, ручной аудит `qa_review_queue`, финальный отчёт приёмки.  
**Mode:** qa  
**Duration:** 1 день  
**UI hint:** no

**Requirements:** REQ-QA-02

**Success Criteria:**
1. needs_review ≤ 5 % после прогона всех тестовых книг
2. Вся очередь `qa_review_queue.jsonl` разобрана вручную; 0 % критических галлюцинаций в морской терминологии (в аудированной выборке)
3. Точность триплетов ≥ 0.90 на выборке 50
4. Recall@5 ≥ 0.90 на Golden Dataset; Figure-Hit-Rate ≥ 0.95
5. Отчёт приёмки (`acceptance_report.md`) создан; версии продуктов и схемы артефакта зафиксированы
