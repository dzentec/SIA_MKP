# REQUIREMENTS — Maritime Knowledge Pipeline with Rules (MKP-R)

**Source:** HLD v3.1 + DIFF v3.3 + DIFF v3.3.1 (HLD v3.3.1)  
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

#### REQ-B07 — Экспорт `.bookpack.zip` / `.zst` v0.3.0
Упаковка артефакта стандарта v0.3.0: `manifest.yaml` (bookpack_version: "0.3.0", generation, parent_hash, compatibility matrix, base/user hashes), `checksums.sha256`, `signature.ed25519` (I13), per-artifact hashes (`base/chunks.sha256`, `base/rules.sha256`, `base/guardrails.sha256`), `base/` (chunks, triplets, claims, rules, graph, guardrails), `yacht/` (stub []), `voyage/` (stub []), `personal/` (stub []), `assets/`.
**Scope:** v1 (Phase 2.1)

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

#### REQ-R01 — Онтология и схемы правил (v0.3.0)
YAML-онтология (`sia_ontology.yaml`, `sia_relations.yaml`, `mapping.yaml`) и строгие Pydantic схемы: `Claim`, `Cluster`, `RuleTrigger`, `RuleAction`, `RuleSource`, `Rule` (с полями `deprecated`, `orphaned`), `CompatibilityInfo`, `ManifestV3`.
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
Инструмент CLI для валидации и ручного ревью правил (`status="approved"`). Проверка числовых порогов триггеров на соответствие цитатам. Формирование 15+ эталонных правил T1 (Golden Rules).
**Scope:** v1 (Phase 2.1)

---

### Обновление конвейера и двухступенчатый критик (v2 / Phase 6)

#### REQ-BLD-V2-01 — Устранение 5 критических дефектов генерации
1. **Нормализация идентификаторов:** Устранение двойных префиксов `RULE_RULE-` через `normalize_rule_id(raw_id)`.
2. **Типобезопасность триггеров:** `RuleTrigger.value` поддерживает `float | int | str | list[float] | list[str]`.
3. **Сериализация противоречий:** Корректное сохранение и экспорт `contradictions` в `cluster.py`.
4. **Фильтрация Claims:** Строгая фильтрация не сопоставленных утверждений (`mapped=True` для синтеза).
5. **Валидация порогов:** Исключение придуманных чисел; разрешение базовых булевых констант (0.0/1.0) только в допустимых контекстах.
**Scope:** Phase 6

#### REQ-BLD-V2-02 — OllamaManager (Single-GPU Sequential Loader)
Управление VRAM бюджетом (≤ 30 GB) на одной GPU (RTX 5090 32GB / RTX 4090 24GB). Последовательная загрузка и выгрузка моделей (`keep_alive: 0`), гарантия присутствия в памяти ровно одной 32B модели, трекинг задержки переключения и устойчивость к сбоям API.
**Scope:** Phase 6

#### REQ-BLD-V2-03 — Подсистема критика (Critic Subsystem Core)
Модель вердикта `CriticVerdict` (`keep`, `reject`, `uncertain`, `fix`), абстрактный интерфейс `BaseCritic`, надежный парсер `_extract_json()` для извлечения ответов из reasoning-логов DeepSeek-R1 (`<think>...</think>`), гарантия абсолютного **fail-open** (любая ошибка критика транслируется в `keep`/`uncertain` без падения пайплайна).
**Scope:** Phase 6

#### REQ-BLD-V2-04 — Cluster Critic (Stage 5.2)
Рецензирование и предварительная фильтрация кластеров утверждений специализированным морским промптом до синтеза правил. Отсечение справочных цитат, описаний конструкций яхты и дублирующихся тем (сокращение с ~1000 до 50–100 кластеров).
**Scope:** Phase 6

#### REQ-BLD-V2-05 — Rule Critic (Stage 5.4)
Рецензирование и нормализация синтезированных правил (проверка триггеров, действий, severity, домена и дубликатов). Автоматическое исправление через `suggested_fix` и отсев недействующих гипотез (сокращение с 600+ до **40–50 верифицированных операционных правил** на книгу).
**Scope:** Phase 6

#### REQ-BLD-V2-06 — Пресеты конфигурации, YAML-файл, CLI и воронка метрик
Поддержка полного файла настроек `builder_config.yaml` со всеми порогами Fallback v4.2, таймаутами и параметрами моделей. Пресеты `full` (32B VLM + 32B Extractor + 32B Critic), `basic` (32B baseline, critic disabled), `fast` (7B/14B). Флаги CLI `--config`, `--preset` и `--critic/--no-critic`. Сбор полной воронки конверсии `PipelineMetrics` и генерация расширенного отчета `ingest_report.md`.
**Scope:** Phase 6

#### REQ-BLD-V2-07 — Подсистема мониторинга здоровья и KillSwitch (Fallback v4.2)
Модули `src/mkp_builder/fallback/`: `HealthMonitor` (CPU >85%, GPU util <50%, Offload >30s, VRAM >98%), `KillSwitch` (StopReason enum, StopEvent), `EventLogger` (`work/fallback_events.jsonl`), `RetryHelper` (1 retry с коротким таймаутом, primary/retry/hard limit по этапам).
**Scope:** Phase 6

#### REQ-BLD-V2-08 — VLM Fail-Policy и Batch Circuit Breaker
Модули `VLMFailTracker` (1–4 ошибки VLM -> skip картинки + запись в `work/vlm/vlm_failures.jsonl`, 5 ошибок подряд -> STOP) и `BatchCircuitBreaker` (1 упавшая книга -> пропуск, 2 упавшие книги подряд -> STOP batch + Pod stop).
**Scope:** Phase 6

#### REQ-BLD-V2-09 — RunPod PodStopper и сохранение аварийного состояния
Модули `PodStopper` (вызов RunPod REST/GraphQL API для остановки пода с 30s grace period) и `ShutdownOrchestrator` (сохранение частичного состояния книги, генерация `work/tui_signal.json` и `work/pipeline_stopped.jsonl`).
**Scope:** Phase 6

#### REQ-BLD-V2-10 — TUI Signal Watcher и звуковая сигнализация
Модули `src/mkp_tui/`: `SignalWatcher` (`watchdog` на `tui_signal.json`), `AlertSound` (`winsound` на Windows / terminal bell на Linux с разделением warning/error/critical/success и флагом `--no-sound`), рендеринг экрана аварийного останова с таблицей провалов VLM.
**Scope:** Phase 6

#### REQ-BLD-V2-11 — Трёхступенчатая фильтрация изображений (Clean RUNPOD)
Модули `src/mkp_builder/filters/`: `RuleBasedImageFilter` (FILTER 1 на CPU: edge density/concentration, аспект, размер, selective OCR номеров страниц, perceptual hash dedup; сохранение ценных ЧБ схем) $\to$ `VLMImageFilter` (FILTER 2 на GPU: `qwen2.5vl:7b`, классификация diagram/rigging/photo/cover/map, `extract_worthy: bool`, strict fail-open) $\to$ существующая аннотация VLM 32B (FILTER 3). Сокращение потока с 226 до ~50 картинок (экономия 1+ ч GPU), логирование `image_filter_rejects.jsonl` и `image_filter_summary.json`.
**Scope:** Phase 6

---

### RUNPOD-H: Гибридный конвейер (RunPod + OpenRouter / Phase 7)

#### REQ-HYB-01 — OpenRouter API Client & Infrastructure
`src/mkp_builder/openrouter/client.py`, `rate_limiter.py`, `circuit_breaker.py`: Httpx-клиент с повторными попытками, экспоненциальным backoff, чтением `Retry-After` (429), моментальным остановом при 402/401. Token Bucket Rate Limiter (150 req / 10s, 15 RPS). Circuit Breaker (5 ошибок подряд $\to$ OPEN, 300s cooldown, HALF_OPEN recovery).
**Scope:** Phase 7

#### REQ-HYB-02 — Balance Guard & Cost Tracking
`src/mkp_builder/openrouter/balance_guard.py`, `cost_tracker.py`: Мониторинг кредитов через `/credits` каждые 5 минут, останов при остатке < $10 или < стоимости книги. Повызовный лог затрат в `costs.jsonl` на основе `total_cost` от OpenRouter, генерация `summary_{book_id}.json`.
**Scope:** Phase 7

#### REQ-HYB-03 — OpenRouter Batch API Subsystem
`src/mkp_builder/openrouter/batch_client.py`: Асинхронная отправка кластеров и правил на DeepSeek R1 (`deepseek/deepseek-r1-0528`), загрузка файлов (`POST /files`), создание батча (`POST /batches`), поллинг (24h SLA), скачивание и парсинг результатов.
**Scope:** Phase 7

#### REQ-HYB-04 — PC Shutdown Persistence & Batch Recovery
`src/mkp_builder/openrouter/checkpoint.py`: Сохранение `pending_batch.json`, позволяющее безопасно выключать ПК во время обработки батча на серверах OpenRouter. Возобновление поллинга при перезапуске, экран истории батчей `BatchesView` (hotkey `l`) с ручным скачиванием.
**Scope:** Phase 7

#### REQ-HYB-05 — 12-Stage Hybrid Phase Pipeline
`src/mkp_builder/openrouter/phase.py`: Оркестрация 12 этапов (Filter2 Qwen VL 7B, VLM 32B, Claims Qwen 72B, Triplets Qwen 72B, Clustering local, Cluster Critic R1 Batch, Synthesize Qwen 72B, Rule Critic R1 Batch, Validation local, Guardrails local, Assemble bookpack v0.3.0, Ed25519 signing on PC) с чекпоинтами `checkpoints/{book_id}_state.json`.
**Scope:** Phase 7

#### REQ-HYB-06 — Rich TUI OpenRouter Monitor & Sound
`src/mkp_tui_openrouter/`: Изолированный Rich-интерфейс с живым дашбордом (прогресс 12 этапов, стоимость в $, rate limiter, circuit breaker, live log), горячими клавишами (`q/b/s/r/l/d/i`), звуковыми оповещениями (`winsound`) и экраном истории батчей.
**Scope:** Phase 7

#### REQ-HYB-07 — Config, CLI & Pipeline Auto-Start
`src/mkp_builder/openrouter/config.py`, `cli.py`, патч `pipeline.py`: Команда `python -m mkp_builder.openrouter.cli run`, автоматический старт OpenRouter-фазы после выгрузки с RunPod при наличии `OPENROUTER_API_KEY`, мульти-книжный `BatchCircuitBreaker` (2 ошибки подряд $\to$ STOP).
**Scope:** Phase 7

#### REQ-HYB-08 — Mock Integration Test Suite
`tests/openrouter/`: 100% покрытие тестами всех компонентов OpenRouter (клиент, rate limiter, circuit breaker, balance guard, cost tracker, batch client, partial failure 95/5, checkpoint resume, E2E мок-тест).
**Scope:** Phase 7

#### REQ-HYB-09 — Трёхступенчатая фильтрация изображений (RUNPOD-H / OpenRouter)
Модули `tools/openrouter/filters/`: `OpenRouterBackend` (кодирование base64, rate limiting, cost tracking), `RuleBasedImageFilter` (FILTER 1 на CPU), `VLMImageFilter` (FILTER 2: `qwen/qwen-2.5-vl-7b-instruct` через OpenRouter, strict fail-open), `VLMAnnotator` (FILTER 3: `qwen/qwen-2.5-vl-32b-instruct` через OpenRouter). Стоимость VLM этапа $\le \$0.07$ на книгу, логирование `image_filter_rejects.jsonl`.
**Scope:** Phase 7

---

## Продукт 2: `mkp-server`

#### REQ-S01 — Архитектура хранилища `/storage/`
Поддерживать 4-уровневую структуру каталогов на судне: `active/` (текущий bookpack и сервер), `backup/` (резервная копия предыдущего поколения, глубина N-1), `staging/` (временное применение обновлений), `fallback/` (неизменяемый заводской образ SquashFS R/O), `failed/` (сохранение сбоев), `logs/` и журнал транзакций `apply.wal` (I8, I11).
**Scope:** v1 (Phase 3)

#### REQ-S02 — Импорт пакетов и дельт с верификацией Ed25519 & Compatibility
- Валидация подписи Ed25519 (`signature.ed25519`) по публичному ключу сервиса (I13).
- Валидация матрицы совместимости (`compatibility`) до применения (I14).
- Поддержка форматов: монолитный Bookpack v0.3.0, `T1-delta` (base), `User-delta` (yacht/voyage/personal), `Server-update` и `Combined-update`.
- Валидация per-artifact контрольных сумм SHA-256 (I3).
**Scope:** v1 (Phase 3)

#### REQ-S03 — Удаление книги (`remove-book`)
Проверка наличия, подтверждение удаления, пересборка активного слоя и индексов.
**Scope:** v1 (Phase 3)

#### REQ-S04 — Verify
`mkp-server verify --base <путь>` — автономная проверка манифеста, контрольных сумм и целостности индексов без запуска сервиса.
**Scope:** v1 (Phase 3)

#### REQ-S05 — Эмбеддинги и гибридный поиск (LanceDB)
Модель `intfloat/multilingual-e5-large` (dim=1024) через `sentence-transformers`. Обязательные префиксы `passage:` / `query:`. Полнотекстовый поиск FTS + векторный поиск с RRFReranker.
**Scope:** v1 (Phase 3)

#### REQ-S06 — Граф знаний и RuleStore
Построение графа сущностей из `triplets.jsonl` при пересборке. Хранилище правил `RuleStore` с матчингом по `archetype`, `telemetry`, `domain`, `status`, `tier`, `region`.
**Scope:** v1 (Phase 3)

#### REQ-S07 — Транзакционный конвейер, WAL и Rollback (Инварианты I0–I10)
- Pre-flight проверка свободного места (≥ 2× active + delta).
- Логирование всех шагов в `apply.wal` с `fsync` на файл и каталог (`fsync(dirname)`).
- Фиксация шага `backup_verified` отдельно от `backup_created` (I9).
- Атомарная подмена через `renameat2(RENAME_EXCHANGE)` или двойной `mv` + `fsync`.
- Автоматический откат к `backup/` при сбое запуска/смоук-теста.
- Ручной откат в одну команду/кнопку при валидном backup (I5); 3 опции при повреждённом backup (I5/B.6).
- Сохранение WAL после rollback для аудита (I10).
**Scope:** v1 (Phase 3)

#### REQ-S08 — Набор MCP-инструментов (10 инструментов)
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
- **System namespace (🟢 MVP):**
  10. `get_bookpack_info()` — поколение `generation`, версии, хеши слоев, статус обновлений.
- **Изоляция:** Пользовательские инструменты не имеют прав на изменение/удаление `T1 Base`.
**Scope:** v1 (Phase 3)

#### REQ-S09 — Транспорты
По умолчанию stdio. `--transport http --port N` — streamable-http, строго 127.0.0.1.
**Scope:** v1 (Phase 3)

#### REQ-S10 — Множественные тематики
Одна база = одна тематика (`--topic`).
**Scope:** v1 (Phase 3)

#### REQ-S11 — Логирование сервера
`<база>/logs/mcp_server.log`, RotatingFileHandler 10 МБ × 5.
**Scope:** v1 (Phase 3)

#### REQ-S12 — Управление связями (User-layer Orphaning & Tombstones)
- При удалении/изменении T1 чанков зависимые пользовательские правила помечаются `orphaned=true` без автоудаления.
- Удаленные элементы T1 сохраняются как tombstones (`deprecated=true`) на протяжении 2 релизов.
**Scope:** v1 (Phase 3)

#### REQ-S13 — Безопасность обновлений и телеметрия
- Запрет принудительных обновлений (force-update) в море (I12).
- Opt-in сбор логов и телеметрии с обязательным preview перед отправкой.
**Scope:** v1 (Phase 3)

---

## Общее / Инфраструктура

#### REQ-C01 — Общий модуль `mkp-common`
Pydantic-модели (chunks, pages, triplets, claims, rules, bookpack v0.3.0 manifest, compatibility), location_ref утилиты, валидация манифестов, логирование, Ed25519 верификация.
**Scope:** v1

#### REQ-C02 — pyproject.toml
Два консольных входа (`mkp-builder`, `mkp-server`), зависимости `.[builder]` и `.[server]`, zstandard и cryptography/pynacl.
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
- Прохождение тестов надежности rollback (I0–I14)
**Scope:** v1
