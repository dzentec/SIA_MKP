# MKP-R — Maritime Knowledge Pipeline with Rules

**Maritime Knowledge Pipeline with Rules (MKP-R)** — это 100% автономный (offline-first) конвейер для преобразования морской литературы, регламентов и судовой документации (PDF, EPUB, DOCX) в структурированную базу знаний и формализованных правил для **автономного яхтенного советника (SIA Advisor)** с обслуживанием по протоколу **Model Context Protocol (MCP)**.

---

## 🧭 Архитектура системы (HLD v3.3.1)

Система разделена на два независимых продукта в едином монорепозитории и набор инструментов облачной оркестрации:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      mkp-builder (offline, на берегу)                       │
│                                                                             │
│  [Парсинг] → [3-ст. Фильтрация схем (CPU→7B→32B)] → [OCR] → [VLM Аннотация] │
│  → [3-ст. Верификация] → [Чанкинг] → [Триплеты] → [Claims]                  │
│  → [Кластеризация + ClusterCritic] → [Синтез правил + RuleCritic 32B]       │
│  → [Fallback v4.2 & HealthMonitor] → [Guardrails] → [Подпись Ed25519]       │
│  → [Экспорт Signed Bookpack v0.3.0 (.zip / .zst)]                           │
│                                      │                                      │
│                                      ▼                                      │
│                      ┌──────────────────────────────┐                       │
│                      │    .bookpack.zip v0.3.0      │                       │
│                      │ (base/, yacht/, voyage/, ...)│                       │
│                      │  + manifest.yaml + checksums │                       │
│                      │  + signature.ed25519         │                       │
│                      └──────────────┬───────────────┘                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │ (Передача на яхту: USB / Wi-Fi / OTA)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       mkp-server (on board, read-only)                      │
│                                                                             │
│  • Storage Lifecycle: active/ (N), backup/ (N-1), fallback/ (SquashFS R/O)  │
│  • Transactional WAL & Atomic Swap (renameat2) + Auto-Rollback (I0–I14)    │
│  • LanceDB (гибридный векторный + FTS поиск по чанкам и правилам)           │
│  • Knowledge Graph (NetworkX граф сущностей и морских терминов)             │
│  • RuleStore (движок сопоставления правил по телеметрии яхты)               │
│  • 10 FastMCP инструментов (documents/, rules/, system/)                    │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ (MCP протокол на English)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SIA Advisor (Локальная LLM на борту)                   │
│                                                                             │
│  1. Static Guardrails (≤ 8000 символов критических правил в промпте)        │
│  2. Dynamic Rules (query_rules по ветру, крену, парусам и архетипу)         │
│  3. Deep Search (search_chunks для подробных цитат и объяснений)            │
│  4. Multilingual UX (общение со шкипером на его родном языке)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📚 Четырёхуровневая модель контента (4-Tier Hierarchy)

| Категория (Tier) | Папка в Bookpack | Типы документов | Что генерируется | Статус |
|---|---|---|---|---|
| **`T1: Base`** | `base/` | Морская классика, книги по парусам, физика, COLREGs, регламенты | Chunks + Triplets + Claims + **Approved Golden Rules** + **Guardrails** (Read-Only для пользователя) | 🟢 **Готово** |
| **`T2: Yacht`** | `yacht/` | Мануалы судна: двигатель (Yanmar, Volvo), электрика (Victron), риггинг | Chunks + Claims + **Hypothesis Rules (`auto_marked`)** | 🟡 **Stub** |
| **`T2.5: Voyage`** | `voyage/` | Лоции, Cruising Guides, альманахи, региональные правила | Chunks + Claims + **Region Rules (`region: caribbean/...`)** | 🟡 **Stub** |
| **`T3: Personal`** | `personal/` | Справочники, кулинария, судовая медицина | **Только Chunks для поиска** (генерация правил пропускается) | 🟡 **Stub** |

---

## 🔒 Ключевые принципы и гарантии (Инварианты v3.3.1 & v4.2)

1. **Zero Hallucination Policy (Non-lie Policy):** Советник никогда не выдумывает правила. Каждое правило и числовой порог строго проверяются по цитатам первоисточника (`RuleSource`: `doc_id`, `page`, `chunk_id`, `quote`). Выдуманные пороги отсекаются валидатором и 32B критиком.
2. **3-ступенчатая фильтрация изображений (3-Stage Image Filter):**
   * **Stage 1 (CPU, ~0.001s/img):** Эвристика по плотности границ (edge density), концентрации чернил и геометрическим пропорциям (без отсечения монохромных схем по цвету).
   * **Stage 2 (VLM 7B, ~0.8s/img):** Быстрая классификация типа изображения (диаграмма, схема, фото, декорация).
   * **Stage 3 (VLM 32B, ~2.5s/img):** Глубокая валидация и отсев декоративных элементов с fail-open fallback (`keep`).
3. **Двухэтапный критик правил (Dual-Stage Critic, Fail-Open):**
   * `ClusterCritic` (на этапе кластеризации): Проверка связности утверждений.
   * `RuleCritic` (на базе 32B LLM): Валидация точности триггеров и числовых порогов против оригинального текста. Опциональный флаг `--critic / --no-critic`.
4. **Подсистема отказоустойчивости Fallback v4.2:**
   * `HealthMonitor`, `KillSwitch`, `VLMFailTracker`, `PodStopper`, `RetryHelper` и `BatchCircuitBreaker` для защиты от сбоев GPU, перегрузок API и потери баланса.
5. **Три уровня доставки знаний:**
   * **Слой 1 (Static Guardrails):** Скомпилированный markdown (`guardrails.md` ≤ 8000 симв.) внедряется прямо в системный промпт — безопасность гарантирована даже при сбое MCP.
   * **Слой 2 (Dynamic `query_rules`):** Запрос правил по текущей телеметрии (`tws`, `heel_angle`) и архетипу судна.
   * **Слой 3 (Deep `search_chunks`):** Семантический гибридный поиск по первоисточникам для развёрнутых объяснений.
6. **Цифровая безопасность (Инвариант I13):** Все пакеты и манифесты подписываются ключом Ed25519 (`signature.ed25519`) по схеме RFC 8032 с защитой от подделки на USB-носителях (0 native deps, 100% offline).
7. **Транзакционный конвейер и Rollback (Инварианты I0–I14):** 
   * 4-уровневое хранилище (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`).
   * Журнал `apply.wal` с обязательным `fsync` директорий.
   * Атомарная замена через `renameat2(RENAME_EXCHANGE)` / `mv` + `fsync`.
   * Автоматический откат при сбое запуска и ручной откат в одну команду (I5).
8. **User-layer Orphaning & Tombstones:** При обновлении T1 связанные пользовательские правила помечаются `orphaned=true` без автоматического удаления, а удалённые T1 чанки сохраняются как tombstones (`deprecated=true`) на 2 релиза.

---

## 🛠 Используемый стек технологий

| Компонент | Технология | Версия / Модель | Назначение |
| :--- | :--- | :--- | :--- |
| **Среда выполнения** | Python | `3.11+ / 3.14` | Основной runtime |
| **Конфигурация пайплайна** | PyYAML + Pydantic | `builder_config.yaml` | Пресеты: `local_7b`, `hybrid`, `clean_runpod`, `runpod_h`, `full_32b` |
| **Криптография** | Pure Python Ed25519 | RFC 8032 | Цифровая подпись пакетов (0 native deps, 100% offline) |
| **VLM (Vision-LLM)** | Qwen2.5-VL | `qwen2.5vl:7b` / `32b` via Ollama/OpenRouter | Распознавание, фильтрация и структурирование схем |
| **Текстовая LLM** | Qwen2.5 | `qwen2.5:7b` / `32b` via Ollama/OpenRouter | Извлечение триплетов, claims, синтез и критика правил |
| **Embeddings** | FastEmbed / Sentence-Transformers | `intfloat/multilingual-e5-large` (1024-dim) | Плотные векторные представления (`passage:` / `query:`) |
| **Vector DB** | LanceDB | `≥ 0.38` | Гибридный векторный и полнотекстовый поиск (FTS) |
| **Graph Engine** | NetworkX | `latest` | Граф знаний сущностей, морских терминов и связей |
| **MCP Server** | FastMCP | `≥ 2.2` (pinned) | Обслуживание бортового ИИ-советника |
| **Парсинг PDF/DOCX/EPUB** | Docling + RapidOCR | `≥ 2.15` | Извлечение структуры, таблиц, схем и координат |
| **CLI & TUI** | Typer + Click + Rich | `latest` | Rich TUI с мониторингом GPU/VRAM, звуковыми уведомлениями и таблицами ревью |

---

## 📁 Подробная структура проекта

```
Doc2Rag/
├── .planning/                  # GSD-планирование, спецификации фаз и матрицы UAT
│   ├── PROJECT.md              # Видение проекта, скоуп и ключевые архитектурные решения
│   ├── ROADMAP.md              # Дорожная карта всех фаз (Phase 0–7)
│   ├── REQUIREMENTS.md         # Реестр формальных требований (REQ-*, REQ-BLD-V2-*, REQ-HYB-*)
│   ├── STATE.md                # Текущий статус выполнения задач и решений
│   └── phase-*/                # Детальные планы (PLAN.md) и отчеты приемки (UAT.md) по фазам
│
├── builder_config.yaml         # Конфигурация конвейера с пресетами (local_7b, hybrid, clean_runpod, runpod_h)
├── server_config.yaml          # Конфигурация хранилища и параметров mkp-server
│
├── ontology/                   # Формальная морская онтология предметной области
│   ├── sia_ontology.yaml       # Иерархия классов, концептов и терминов яхтинга
│   ├── sia_relations.yaml      # Допустимые типы связей между морскими сущностями
│   ├── mapping.yaml            # Маппинг терминов VLM/текста на сущности онтологии
│   └── README.md               # Документация и спецификация онтологической модели
│
├── src/                        # Исходный код ядра MKP-R
│   ├── mkp_common/             # Общие структуры данных, модели и утилиты
│   │   ├── models.py           # Базовые Pydantic-схемы (Chunk, VisualAsset, BBox, DocumentMetadata)
│   │   ├── rules_schema.py     # Схемы правил (Trigger, Action, Rule, ManifestV3, Claim)
│   │   ├── location.py         # LocationRef (стандартизация ссылок на страницы, главы, координаты)
│   │   ├── logger.py           # Структурированное логирование с поддержкой контекста
│   │   └── cache.py            # Дисковый кэш тяжелых вычислений и запросов
│   │
│   ├── mkp_builder/            # Конвейер сборщика знаний и правил (на берегу)
│   │   ├── cli.py              # CLI интерфейс (`mkp-builder build`, `review-rules`, `--preset`, `--critic`)
│   │   ├── tui.py              # Интерактивный Rich TUI (выбор категории T1–T3, прогресс, звук)
│   │   ├── pipeline.py         # Главный оркестратор стадий сборки документа
│   │   ├── ollama_manager.py   # Менеджер последовательной загрузки моделей в VRAM (single-GPU)
│   │   ├── ocr.py              # Модуль OCR (RapidOCR) для сканов и неразмеченного текста
│   │   ├── chunker.py          # Иерархический семантический чанкинг с перекрытиями
│   │   ├── triplets.py         # Извлечение триплетов знаний (субъект-предикат-объект)
│   │   ├── review.py           # Rich-таблицы для визуального ревью сгенерированных правил
│   │   ├── parsers/            # Мультиформатные парсеры документов (PDF, EPUB, DOCX)
│   │   ├── filters/            # 3-ступенчатая фильтрация изображений (Stage 1 CPU, Stage 2/3 VLM)
│   │   ├── vlm/                # Мультимодальный анализ диаграмм и верификатор
│   │   ├── extract/            # Извлечение claims с привязкой к онтологии
│   │   ├── synthesize/         # Кластеризация, критика (ClusterCritic) и синтез правил (RuleCritic 32B)
│   │   ├── fallback/           # Подсистема отказоустойчивости v4.2 (HealthMonitor, RetryHelper, KillSwitch)
│   │   ├── compile/            # Компиляция системных ограничений (guardrails.md)
│   │   └── export/             # Упаковка и Ed25519 подпись .bookpack.zip v0.3.0
│   │
│   └── mkp_server/             # Бортовой сервер базы знаний и FastMCP сервисов
│       ├── cli.py              # CLI интерфейс (`mkp-server serve`, `import`, `rollback`, `info`)
│       ├── server.py           # FastMCP сервер, реализующий 10 бортовых инструментов
│       ├── storage.py          # 4-уровневое хранилище (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`)
│       ├── wal.py              # Транзакционный Write-Ahead Log с синхронизацией директорий (`fsync`)
│       ├── importer.py         # Безопасный импортер bookpack с проверкой Ed25519/sha256 и swap
│       ├── rollback.py         # Движок мгновенного отката (автоматический и ручной)
│       ├── search.py           # LanceDB гибридный поиск (векторный + FTS c e5-large префиксами)
│       ├── graph.py            # Графовый движок NetworkX для поиска связанных морских сущностей
│       ├── rules_store.py      # Сопоставитель правил по телеметрии (ветер, крен, паруса, судно)
│       ├── security.py         # Защита от Path Traversal при отдаче диаграмм и ассетов
│       └── lifecycle.py        # Управление жизненным циклом и health checks
│
├── qa/                         # Модули приемочного тестирования, бенчмарков и датасетов
│   ├── config.yaml             # Конфигурация порогов метрик и параметров бенчмарка
│   ├── rubrics.py              # Формальные рубрики оценивания (M1–M8, M4 agreement)
│   ├── golden_dataset.json     # 30 стратифицированных вопросов (MVP QA)
│   ├── golden_full_dataset.json # 114 всесторонних вопросов (7 блоков тем, Spec v1.1)
│   ├── golden_rules.json       # 15 верифицированных правил T1 с точными цитатами
│   ├── offline_mcp_agent.py    # Автономный агент на базе локальной LLM с вызовами 10 MCP tools
│   ├── eval_judge.py           # LLM-as-a-Judge движок (Gemini/Local)
│   ├── full_eval_runner.py     # Оркестратор полного бенчмарка ($N=3$ прогона, медиана, регрессии)
│   └── reports/                # Итоговые markdown-отчеты бенчмарков (full_eval_report.md)
│
├── tools/                      # Вспомогательные утилиты и облачная оркестрация
│   ├── runpod/                 # ☁️ Clean RunPod (Автономный под с GPU для локальных моделей 32B)
│   │   ├── runpod_orchestrator.py # Оркестратор управления подами, SSH/SCP передачей и запуском
│   │   ├── runpod_api.py       # GraphQL API клиент (управление состоянием подов и биллингом)
│   │   ├── runpod_manager.py   # Менеджер запуска, мониторинга и авто-останова
│   │   ├── run_build_32b.py    # Автономный скрипт пайплайна на 32B VLM внутри облака
│   │   ├── tui.py              # Rich TUI дашборд реального времени (GPU, vRAM, прогресс)
│   │   ├── logger.py           # Сессионный логгер с метриками t/s
│   │   └── AGENT_GUIDE.md      # Руководство по управлению RunPod для ИИ-агентов
│   │
│   └── openrouter/             # 🌐 RUNPOD-H (Гибридный билдер: RunPod GPU + OpenRouter API / Batch API)
│       ├── openrouter_backend.py # Бэкенд OpenRouter с RateLimiter (150/10s), CircuitBreaker и BalanceGuard (<$10)
│       ├── batch_processor.py  # Асинхронный процессор OpenRouter Batch API (24h SLA) с персистентностью
│       ├── hybrid_orchestrator.py # Оркестратор гибридного пайплайна (Docling на GPU + LLM/VLM по API)
│       ├── tui.py              # Rich TUI дашборд с мониторингом расходов ($), токенов и прогресса батчей
│       └── AGENT_GUIDE.md      # Руководство по гибридной оркестрации RUNPOD-H
│
├── tests/                      # Набор автоматизированных тестов pytest
├── pyproject.toml              # Конфигурация проекта, CLI entrypoints и зависимости
└── README.md                   # Главная документация проекта
```

---

## 📦 Структура артефакта `.bookpack.zip` (v0.3.0)

```
<book_id>.bookpack.zip (.zst)
├── manifest.yaml          # Паспорт пакета (v0.3.0, generation, compatibility, t1_hash)
├── checksums.sha256       # Контрольные суммы всех файлов
├── signature.ed25519      # Цифровая подпись Ed25519 (I13)
├── base/                  # 🟢 T1: Base
│   ├── chunks.jsonl       # Текстовые чанки с location_ref и visual_assets
│   ├── chunks.sha256      # Per-artifact контрольная сумма чанков
│   ├── triplets.jsonl     # Графовые триплеты с provenance
│   ├── claims.jsonl       # Атомарные утверждения с привязкой к онтологии
│   ├── rules.jsonl        # Формализованные правила (triggers, actions, severity)
│   ├── rules.sha256       # Per-artifact контрольная сумма правил
│   └── guardrails.md      # Скомпилированный системный промпт (≤ 8000 символов)
├── yacht/                 # 🟡 T2: Yacht (мануалы судна, stub [])
├── voyage/                # 🟡 T2.5: Voyage (лоции и гайды, stub [])
├── personal/              # 🟡 T3: Personal (справочники, search only)
└── assets/                # Извлеченные PNG-диаграммы и схемы
```

---

## 🔌 Набор MCP-инструментов сервера (10 Tools)

### Namespace `documents/`
1. `search_chunks(query: str, top_k: int = 5, tier: Optional[str] = None)` — гибридный семантический поиск по чанкам.
2. `get_diagram_image(doc_id: str, page: int)` — получение PNG-схемы с защитой от Path Traversal.
3. `get_related_entities(entity_id: str)` — связи сущности из графа знаний.
4. `get_book_manifest(doc_id: str)` — метаданные документа и книги.

### Namespace `rules/`
5. `query_rules(archetype, telemetry, domain=None, tier=None, region=None, status="approved")` — поиск применимых правил по текущим условиям судна.
6. `get_rule(rule_id: str)` — полная карточка правила по его ID.
7. `get_rule_provenance(rule_id: str)` — точные цитаты первоисточника, страница и `doc_id`.
8. `list_conflicts(rule_id: str)` — получение списка конфликтующих правил.
9. `get_guardrails()` — отдача скомпилированного текста Static Guardrails.

### Namespace `system/`
10. `get_bookpack_info()` — поколение `generation`, версии `t1_version`, `t1_hash`, хеши `user_layers`, доступные обновления.

---

## 🚀 Быстрый старт

### 1. Установка окружения

```bash
# Клонирование репозитория
cd Doc2Rag

# Создание и активация виртуального окружения
python -m venv .venv
.venv\Scripts\activate

# Установка пакета со всеми зависимостями
pip install -e ".[builder,server]"
```

### 2. Запуск локального Ollama

```bash
# Запуск Ollama с включенным Flash Attention для VLM/LLM инференса
python poc/start_ollama.py
```

### 3. Сборка книги и правил (`mkp-builder`)

Конвейер поддерживает различные пресеты выполнения (`builder_config.yaml`) и гибкое управление критиком:

```bash
# Сборка с локальным пресетом 7B (для ПК с 16GB VRAM, последовательная выгрузка моделей)
mkp-builder build \
  --book "path/to/Illustrated_Seamanship.epub" \
  --preset local_7b \
  --tier T1 \
  --out "work/demo"

# Сборка с включением/отключением 32B критика
mkp-builder build --book "path/to/manual.pdf" --critic --out "work/demo"
mkp-builder build --book "path/to/manual.pdf" --no-critic --out "work/demo"

# Просмотр и ревью извлеченных правил через Rich CLI
mkp-builder review-rules --rules "work/demo/books/dedekam_seamanship/rules.jsonl"
```

### 4. Запуск MCP-сервера (`mkp-server`)

Сервер автоматически подхватывает настройки из `server_config.yaml` (по умолчанию `data/live_server_storage` для разработки):

```bash
# Просмотр сводного дашборда состояния хранилища
mkp-server info

# Запуск MCP-сервера по протоколу stdio (для Claude Desktop / Open WebUI / СИА)
mkp-server serve --transport stdio

# Запуск MCP-сервера по протоколу HTTP/SSE
mkp-server serve --transport http --port 8000

# Интерактивный MCP Inspector в браузере
npx -y @modelcontextprotocol/inspector python -m mkp_server.cli serve

# Импорт нового подписанного пакета v0.3.0 в хранилище через WAL
mkp-server import "path/to/book.bookpack.zip"

# Откат к резервной копии (при необходимости)
mkp-server rollback --mode auto
```

---

## 🛠 Облачные инструменты и гибридные режимы (`tools/`)

В папке `tools/` размещены изолированные инструменты облачной обработки тяжелых книг:

### 1. `tools/runpod/` — Clean RunPod (Self-Contained GPU Pod)
* Автоматический деплой пода на **NVIDIA RTX 4090 / A5000 (24GB VRAM)**.
* Локальный запуск тяжелых моделей (`qwen2.5vl:32b`, `qwen2.5:32b`) внутри пода.
* **Auto-Stop & KillSwitch:** Автоматическая остановка пода при простое, завершении сборки или критических ошибках.
* **Rich TUI:** Мониторинг GPU/VRAM, скорости инференса (t/s) и прогресса страниц в реальном времени.

```bash
# Запуск сборки книги в облаке RunPod
python -m tools.runpod.runpod_manager --book "path/to/book.pdf" --tier T1
```

### 2. `tools/openrouter/` — RUNPOD-H (Hybrid Cloud + OpenRouter API)
* **Разделение труда:** Тяжелый парсинг (Docling, RapidOCR, 3-Stage Image Filter) выполняется на недорогом RunPod GPU, а инференс VLM/LLM делегируется в **OpenRouter API / Batch API** со скидкой 50%.
* **Строгий контроль бюджета:** `BalanceGuard` (остановка при остатке <$10), ограничение стоимости фильтрации изображений ($\le \$0.07$ на книгу).
* **RateLimiter & CircuitBreaker:** Лимит 150 req / 10s, асинхронные ретраи при 429/503 и персистентность состояния очередей (`pending_batch.json`, 24h SLA).

```bash
# Запуск гибридного билдера RUNPOD-H
python -m tools.openrouter.hybrid_orchestrator --book "path/to/book.pdf" --tier T1 --batch-mode
```

---

## 🧪 Тестирование и бенчмарки

```bash
# Запуск всех автоматизированных тестов проекта
pytest tests/ -v

# Запуск приемочного бенчмарка (Acceptance Suite, Phase 4)
python qa/run_acceptance.py

# Запуск полного бенчмарка по качеству (Phase 5 Full Eval)
python qa/run_full_live_benchmark.py

# Сквозная интерактивная демонстрация 10 MCP-инструментов
python qa/demo_e2e.py
```

### Сводка результатов приемочного тестирования и бенчмарка (Phase 4 & Phase 5):

| Метрика | Значение | Критерий успеха | Результат |
|---|---|---|---|
| **Hallucination Rate** | `0.0%` | `< 5.0%` | ✅ PASS |
| **Citation Precision / Rate** | `100.0%` | `> 90.0%` | ✅ PASS |
| **Search Recall @ 3** | `100.0%` | `> 85.0%` | ✅ PASS |
| **Safety Compliance Rate** | `100.0%` | `100.0%` | ✅ PASS |
| **Direct vs RAG Agent Improvement** | `+91.3 pp` | `> +30.0 pp` | ✅ PASS |
| **Knowledge Graph Accuracy** | `100.0%` | `> 90.0%` | ✅ PASS |
| **Static Guardrails Size** | `340 chars` | `≤ 8000 chars` | ✅ PASS |
| **Инварианты надежности (I0–I14)** | `15/15 PASS` | `15/15` (100% стресс-тестов WAL) | ✅ PASS |
| **Data Leakage Check** | `11.0%` | `< 30.0%` | ✅ PASS |
| **Automated Test Suite** | `45/45 PASS` | `100%` | ✅ PASS |

---

## 📋 Статус проекта и дорожная карта

* ✅ **Phase 0:** PoC & Validation (7/7 проверок пройдено).
* ✅ **Phase 1:** `mkp-builder` Core (Парсинг + VLM + Верификация + Чанкинг).
* ✅ **Phase 2:** `mkp-builder` Complete (Триплеты + Экспорт базового архива).
* ✅ **Phase 2.1:** `mkp-builder` Rules Pipeline & Signed Bookpack v0.3.0 (8/8 задач PASS, 100% тестов).
* ✅ **Phase 3:** `mkp-server` 4-Tier Storage, WAL/Rollback (I0–I14) & 10 FastMCP Tools (8/8 задач PASS).
* ✅ **Phase 4:** QA & Acceptance (100% PASS, 0% Hallucinations, 15/15 Инвариантов, `acceptance_report.md`).
* ✅ **Phase 5:** Full Evaluation & Quality Benchmark (Spec v1.1, 114 вопросов, Offline MCP Agent, Gemini LLM-as-a-Judge, `full_eval_report.md`).
* 🔄 **Phase 6:** MKP-Builder Pipeline Upgrade & Clean RUNPOD (5 багфиксов, OllamaManager для single-GPU, 3-ступенчатая фильтрация схем, двухэтапный критик правил, Fallback v4.2, `builder_config.yaml`).
* ⏳ **Phase 7:** RUNPOD-H — Hybrid MKP Builder (RunPod GPU + OpenRouter API / Batch API 24h SLA, BalanceGuard <$10, RateLimiter, 3-stage VLM filter в `tools/openrouter/`).



