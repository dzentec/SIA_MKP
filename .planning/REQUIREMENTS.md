# REQUIREMENTS — Maritime Knowledge Pipeline with Rules (MKP-R)

**Source:** HLD v3.1 (`HLD_MKP-R_v3.1_1of2.md` & `HLD_MKP-R_v3.1_2of2.md`)  
**Scope:** v1/MVP = все требования из Phase 0–4 + Phase 2.1 (Rules Pipeline)

---

## Продукт 1: `mkp-builder`

### Базовый конвейер (Base Documents Pipeline)

#### REQ-B01 — Layout Parsing
Парсить PDF/EPUB/DOCX через Docling ≥ 2.15 с `generate_picture_images=True`, `images_scale=2.0`. Именование ассетов: `{book_id}_p{page_num}_fig{idx}.png`. Таблицы экспортировать в Markdown с привязкой к странице.
**Scope:** v1

#### REQ-B02 — OCR Routing (профили фонда)
Поддержать три профиля: `digital` (OCR отключён), `scanned` (full-page OCR), `mixed` (автоопределение по текстовой плотности). OCR-движок конфигурируемый: RapidOCR / Tesseract `rus+eng`. Итоговый движок фиксируется в `book_metadata.json`.
**Scope:** v1

#### REQ-B03 — VLM Annotation (union-схема)
Аннотировать каждую фигуру через Ollama (qwen2.5vl:7b, Q4_K_M). Таксономия: `maneuver | knot | equipment | polar | map | table_figure | other`. Discriminated union JSON (Pydantic). Кэш по ключу SHA-256(image) + model_tag + prompt_ver. Таймаут 45 с, num_predict: 512, OLLAMA_FLASH_ATTENTION=1.
**Scope:** v1

#### REQ-B04 — Трёхступенчатая верификация (100 %)
1. Pydantic schema-валидация каждого VLM-ответа.
2. Текстовая согласованность (LLM, 100 %).
3. Визуальный критик (та же VLM, num_predict: 96, 100 %).
`needs_review=true` → типизированный блок обнуляется, схема в `qa_review_queue.jsonl`. Acceptance gate: `needs_review ≤ 5 %`.
**Scope:** v1

#### REQ-B05 — Chunking (section/table-aware)
max_tokens=512, overlap=64. Таблицы — отдельные чанки. `lang` чанка = язык доминирующего текста. `location_ref` для каждого чанка (pdf:pN / docx:pN / epub:sN#anchor).
**Scope:** v1

#### REQ-B06 — Triplet Extraction (GraphRAG)
Извлечение триплетов через текстовую модель Ollama (qwen2.5:7b). Таксономия сущностей: Парус, Снасть, Манёвр, ВетровойРежим, Узел, Опасность. Отношения: УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ, ТРЕБУЕТ_ДЕЙСТВИЯ, ПРИМЕНЯЕТСЯ_ПРИ, СВЯЗАН_С. Нормализация + дедупликация. Provenance: book_id, page_number, chunk_id, location_ref.
**Scope:** v1

#### REQ-B07 — Экспорт `.bookpack.zip` v0.2
Упаковка артефакта v0.2: `manifest.yaml` (bookpack_version: "0.2.0"), `checksums.sha256`, `base/` (chunks, triplets, claims, rules, graph, guardrails), `yacht/` (stub []), `voyage/` (stub []), `personal/` (stub []), `assets/`.
**Scope:** v1

#### REQ-B08 — TUI (rich) + Интерактивный выбор категории + логирование
- TUI на базе Rich: интерактивный выбор категории документа (`T1: Base`, `T2: Yacht`, `T2.5: Voyage`, `T3: Personal`) и региона (`--region` для T2.5) при запуске без флагов.
- Прогресс-бары для каждого этапа конвейера со счётчиками, кэш-попаданиями, ETA, `needs_review`-флагом.
- Файловый лог: `work/logs/builder_<ts>.log`.
**Scope:** v1

#### REQ-B09 — Идемпотентность и кэширование
Повторный запуск на той же книге не вызывает модели заново (кэш по SHA-256 + model + prompt_ver). `--force` сбрасывает кэш.
**Scope:** v1

#### REQ-B10 — CLI
`mkp-builder build --book <файл> [--tier <T1|T2|T2.5|T3>] [--region <name>] --profile <digital|scanned|mixed> --lang <ru|en|mixed> --out <папка> [--force] [--headless]`  
`mkp-builder export --book-id <id> --out <папка>`
**Scope:** v1

---

### Конвейер синтеза правил (Rules Pipeline)

#### REQ-R01 — Онтология и схемы правил
YAML-онтология (`sia_ontology.yaml`, `sia_relations.yaml`, `mapping.yaml`) и строгие Pydantic схемы: `Claim`, `Cluster`, `RuleTrigger`, `RuleAction`, `RuleSource`, `Rule`, `Manifest`.
**Scope:** v1 (Phase 2.1)

#### REQ-R02 — Извлечение атомарных утверждений (Claims Extraction)
Модуль `claims.py`: извлечение `Claim` из чанков текста через Qwen2.5-7B с валидацией схемы, онтологическим маппингом (`mapped=True/False`), уверенностью (`confidence`), привязкой точной цитаты `quote` (≤200 симв.), `doc_id`, `page`, `chunk_id`. Для документов `T3` генерация claims пропускается.
**Scope:** v1 (Phase 2.1)

#### REQ-R03 — Кластеризация утверждений (Claims Clustering)
Модуль `cluster.py`: группировка claims по темам, архетипам судов (`archetype`), сигналам телеметрии и доменам (`safety`, `trim`, `reefing`, `maneuver`). Детекция противоречий (`contradictions`) между источниками.
**Scope:** v1 (Phase 2.1)

#### REQ-R04 — Синтез правил (Rule Synthesis)
Модуль `synthesize.py`: синтез объекта `Rule` из кластера утверждений. Определение `triggers` (строго из цитат, без придумывания чисел), `triggers_logic` (ALL/ANY), `actions`, `severity` (critical/warning/info), `uncertainty` (verified/hypothesis), `sources` и `conflicts_with`.
**Scope:** v1 (Phase 2.1)

#### REQ-R05 — Компиляция статических Guardrails
Модуль `guardrails.py`: компиляция критических и warning правил T1 со статусом `approved` в `guardrails.md` / `compiled_system_prompt.md` объёмом ≤ 8000 символов для системного промпта советника.
**Scope:** v1 (Phase 2.1)

#### REQ-R06 — CLI ревью правил и аудит MDA-002
Инструмент CLI для валидации и ручного ревью правил (`status="approved"`). Проверка числовых порогов триггеров на соответствие цитатам. Формирование 15+ эталонных правил T1.
**Scope:** v1 (Phase 2.1)

---

## Продукт 2: `mkp-server`

#### REQ-S01 — Структура базы и реестр
Создать и поддерживать структуру: `base.json` (реестр), `books/` (книжные слои), `pack/` (объединённый слой), `derived/` (активные индексы), `derived_new/` (временные blue-green), `inbox/` (архивы).
**Scope:** v1

#### REQ-S02 — Импорт `.bookpack.zip` v0.2
Валидация (`checksums.sha256`, manifest, schema_version). Распаковка слоёв (`base/`, `yacht/`, `voyage/`, `personal/`). Слияние `pack/`. Пересборка индексов в `derived_new/` (blue-green).
**Scope:** v1

#### REQ-S03 — Удаление книги (`remove-book`)
Проверка наличия, подтверждение удаления, пересборка pack/ и индексов blue-green.
**Scope:** v1

#### REQ-S04 — Verify
`mkp-server verify --base <путь>` — проверка манифеста pack/, целостности и build_info.json без запуска сервиса.
**Scope:** v1

#### REQ-S05 — Эмбеддинги и гибридный поиск (LanceDB)
Модель `intfloat/multilingual-e5-large` (dim=1024) через `sentence-transformers`. Обязательные префиксы `passage:` / `query:`. Полнотекстовый поиск FTS + векторный поиск с RRFReranker.
**Scope:** v1

#### REQ-S06 — Граф знаний (NetworkX / LadybugDB)
Построение графа сущностей и связей из `triplets.jsonl` при пересборке. Обход графа и поиск связей.
**Scope:** v1

#### REQ-S07 — Blue-Green пересборка индексов
MCP сервер продолжает обслуживать запросы из `derived/` во время фоновой пересборки в `derived_new/`. Атомарный swap после прохождения smoke-теста.
**Scope:** v1

#### REQ-S08 — Набор MCP-инструментов (9 инструментов)
- **Documents namespace (🟢 MVP):**
  1. `search_chunks(query, top_k=5, tier=None)`
  2. `get_diagram_image(doc_id, page)` (с защитой от path traversal)
  3. `get_related_entities(entity_id)`
  4. `get_book_manifest(doc_id)`
- **Rules namespace (🟢 MVP для T1 / 🟡 Stub для T2/T2.5):**
  5. `query_rules(archetype, telemetry, domain=None, tier=None, region=None, status="approved")`
  6. `get_rule(rule_id)`
  7. `get_rule_provenance(rule_id)`
  8. `list_conflicts(rule_id)`
  9. `get_guardrails()`
**Scope:** v1

#### REQ-S09 — Транспорты
По умолчанию stdio. `--transport http --port N` — streamable-http, строго 127.0.0.1.
**Scope:** v1

#### REQ-S10 — Множественные тематики
Одна база = одна тематика (`--topic`).
**Scope:** v1

#### REQ-S11 — Логирование сервера
`<база>/logs/mcp_server.log`, RotatingFileHandler 10 МБ × 5.
**Scope:** v1

---

## Общее / Инфраструктура

#### REQ-C01 — Общий модуль `mkp-common`
Pydantic-модели (chunks, pages, triplets, claims, rules, bookpack v0.2 manifest), location_ref утилиты, валидация манифестов, логирование.
**Scope:** v1

#### REQ-C02 — pyproject.toml
Два консольных входа (`mkp-builder`, `mkp-server`), зависимости `.[builder]` и `.[server]`.
**Scope:** v1

#### REQ-C03 — Двуязычность
Поддержка RU/EN, кросс-языковые эмбеддинги.
**Scope:** v1

#### REQ-C04 — Windows 11 100% Офлайн
Полная автономность после загрузки весов, локальный Ollama, LanceDB, NetworkX.
**Scope:** v1

---

## Phase 0 — PoC (✅ Завершено)
- REQ-P0-01 (Docling crop), REQ-P0-02 (VLM qwen2.5-vl), REQ-P0-03 (LanceDB FTS), REQ-P0-04 (e5-large), REQ-P0-05 (OCR), REQ-P0-06 (Graph engine), REQ-P0-07 (EPUB).

---

## QA & Acceptance

#### REQ-QA-01 — Golden Dataset & Rules Ground Truth
Набор из 30+ вопросов и 15+ эталонных правил T1 с полной верификацией источников и цитат.
**Scope:** v1

#### REQ-QA-02 — Метрики приёмки
- Hallucination rate = 0 на Golden Dataset
- Rule recall ≥ 0.8; Citation rate ≥ 0.9
- needs_review ≤ 5 % после первичного прогона
- Точность триплетов ≥ 0.90
- Static guardrails корректно компилируются (≤ 8000 символов)
**Scope:** v1
