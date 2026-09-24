# MKP-R — Maritime Knowledge Pipeline with Rules

**Maritime Knowledge Pipeline with Rules (MKP-R)** — это 100% автономный (offline-first) конвейер для преобразования морской литературы, регламентов и судовой документации (PDF, EPUB, DOCX) в структурированную базу знаний и формализованных правил для **автономного яхтенного советника (SIA Advisor)** с обслуживанием по протоколу **Model Context Protocol (MCP)**.

---

## 🧭 Архитектура системы (HLD v3.3.1)

Система разделена на два независимых продукта в едином монорепозитории:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      mkp-builder (offline, на берегу)                       │
│                                                                             │
│  [Парсинг] → [OCR] → [VLM Аннотация] → [3-ст. Верификация] → [Чанкинг] →    │
│  → [Триплеты] → [Claims] → [Кластеризация] → [Синтез правил] → [Guardrails] │
│  → [Подпись Ed25519 (I13)] → [Экспорт Signed Bookpack v0.3.0 (.zip / .zst)] │
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

## 🔒 Ключевые принципы и гарантии (Инварианты v3.3.1)

1. **Zero Hallucination Policy (Non-lie Policy):** Советник никогда не выдумывает правила. Каждое правило и числовой порог строго проверяются по цитатам первоисточника (`RuleSource`: `doc_id`, `page`, `chunk_id`, `quote`). Выдуманные пороги отсекаются валидатором.
2. **Три уровня доставки знаний:**
   * **Слой 1 (Static Guardrails):** Скомпилированный markdown (`guardrails.md` ≤ 8000 симв.) внедряется прямо в системный промпт — безопасность гарантирована даже при сбое MCP.
   * **Слой 2 (Dynamic `query_rules`):** Запрос правил по текущей телеметрии (`tws`, `heel_angle`) и архетипу судна.
   * **Слой 3 (Deep `search_chunks`):** Семантический гибридный поиск по первоисточникам для развёрнутых объяснений.
3. **Цифровая безопасность (Инвариант I13):** Все пакеты и манифесты подписываются ключом Ed25519 (`signature.ed25519`) по схеме RFC 8032 с защитой от подделки на USB-носителях (0 native deps, 100% offline).
4. **Транзакционный конвейер и Rollback (Инварианты I0–I14):** 
   * 4-уровневое хранилище (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`).
   * Журнал `apply.wal` с обязательным `fsync` директорий.
   * Атомарная замена через `renameat2(RENAME_EXCHANGE)` / `mv` + `fsync`.
   * Автоматический откат при сбое запуска и ручной откат в одну команду (I5).
5. **User-layer Orphaning & Tombstones:** При обновлении T1 связанные пользовательские правила помечаются `orphaned=true` без автоматического удаления, а удалённые T1 чанки сохраняются как tombstones (`deprecated=true`) на 2 релиза.
6. **Запрет Force-update в море (Инвариант I12):** Любое обновление требует подтверждения шкипера.
7. **Zero Data Loss (визуальный слой):** Каждая схема сохраняется в PNG (scale=2.0) и получает VLM-описание с 3-ступенчатой верификацией.

---

## 🛠 Используемый стек технологий

| Компонент | Технология | Версия / Модель | Назначение |
| :--- | :--- | :--- | :--- |
| **Среда выполнения** | Python | `3.11+ / 3.14` | Основной runtime |
| **Криптография** | Pure Python Ed25519 | RFC 8032 | Цифровая подпись пакетов (0 native deps, 100% offline) |
| **VLM (Vision-LLM)** | Qwen2.5-VL | `qwen2.5vl:7b` / `32b` via Ollama/vLLM | Распознавание и структурирование морских схем |
| **Текстовая LLM** | Qwen2.5 | `qwen2.5:7b` / `32b` via Ollama | Извлечение триплетов, claims и синтез правил |
| **Embeddings** | FastEmbed / Sentence-Transformers | `intfloat/multilingual-e5-large` (1024-dim) | Плотные векторные представления (`passage:` / `query:`) |
| **Vector DB** | LanceDB | `≥ 0.38` | Гибридный векторный и полнотекстовый поиск (FTS) |
| **Graph Engine** | NetworkX | `latest` | Граф знаний сущностей, морских терминов и связей |
| **MCP Server** | FastMCP | `≥ 2.2` (pinned) | Обслуживание бортового ИИ-советника |
| **Парсинг PDF/DOCX/EPUB** | Docling + RapidOCR | `≥ 2.15` | Извлечение структуры, таблиц, схем и координат |
| **CLI & TUI** | Typer + Click + Rich | `latest` | TUI с интерактивным выбором категорий и таблицами ревью |

---

## 📁 Подробная структура проекта

```
Doc2Rag/
├── .planning/                  # GSD-планирование, спецификации фаз и матрицы UAT
│   ├── PROJECT.md              # Видение проекта, скоуп и ключевые архитектурные решения
│   ├── ROADMAP.md              # Дорожная карта всех фаз (Phase 0–5)
│   ├── REQUIREMENTS.md         # Реестр формальных требований и инвариантов
│   ├── STATE.md                # Текущий статус выполнения задач и решений
│   └── phase-*/                # Детальные планы (PLAN.md) и отчеты приемки (UAT.md) по фазам
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
│   │   ├── cli.py              # CLI интерфейс (`mkp-builder build`, `mkp-builder review-rules`)
│   │   ├── tui.py              # Интерактивный Rich TUI (выбор категории T1–T3, прогресс)
│   │   ├── pipeline.py         # Главный оркестратор стадий сборки документа
│   │   ├── ocr.py              # Модуль OCR (RapidOCR) для сканов и неразмеченного текста
│   │   ├── chunker.py          # Иерархический семантический чанкинг с перекрытиями
│   │   ├── triplets.py         # Извлечение триплетов знаний (субъект-предикат-объект)
│   │   ├── review.py           # Rich-таблицы для визуального ревью сгенерированных правил
│   │   ├── parsers/            # Мультиформатные парсеры документов
│   │   │   ├── base.py         # Базовый абстрактный класс BaseDocumentParser
│   │   │   ├── pdf_parser.py   # Docling PDF парсер (таблицы, координаты, извлечение фигур)
│   │   │   ├── epub_parser.py  # Парсер структуры EPUB (XHTML, оглавление, иллюстрации)
│   │   │   └── docx_parser.py  # DOCX парсер структурированных документов
│   │   ├── vlm/                # Модуль мультимодального анализа диаграмм
│   │   │   ├── client.py       # Клиент Ollama VLM API
│   │   │   ├── annotator.py    # Генерация описаний схем и извлечение числовых значений
│   │   │   └── verifier.py     # 3-ступенчатая валидация качества визуальных аннотаций
│   │   ├── extract/            # Извлечение атомарных утверждений (Claims)
│   │   │   └── claims.py       # Извлечение фактов из текста и схем с привязкой к онтологии
│   │   ├── synthesize/         # Кластеризация и синтез формальных правил
│   │   │   ├── cluster.py      # Семантическая кластеризация связанных утверждений
│   │   │   └── synthesize.py   # Синтез правил (триггеры, действия, пороги, цитаты первоисточника)
│   │   ├── compile/            # Компиляция системных ограничений
│   │   │   └── guardrails.py   # Сборка `guardrails.md` (≤ 8000 символов, только Approved T1)
│   │   └── export/             # Упаковка и криптографическая подпись артефактов
│   │       ├── bookpack.py     # Сборка архива `.bookpack.zip` v0.3.0 с контрольными суммами
│   │       └── signer.py       # Ed25519 подпись и валидация манифеста (RFC 8032)
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
│       ├── verifier.py         # Верификация целостности активного хранилища
│       ├── lifecycle.py        # Управление жизненным циклом, самодиагностика и health checks
│       └── models.py           # Серверные схемы запросов, ответов и метаданных
│
├── qa/                         # Модули приемочного тестирования, бенчмарков и датасетов
│   ├── config.yaml             # Конфигурация порогов метрик и параметров бенчмарка
│   ├── rubrics.py              # Формальные рубрики оценивания (M1–M8, M4 agreement, 5-балльная шкала)
│   ├── golden_dataset.json     # 30 стратифицированных вопросов (MVP QA)
│   ├── golden_full_dataset.json # 114 всесторонних вопросов (7 блоков тем, Spec v1.1)
│   ├── golden_rules.json       # 15 верифицированных правил T1 с точными цитатами
│   ├── regression_pool.json    # Пул регрессионных и граничных тестов
│   ├── offline_mcp_agent.py    # Автономный агент на базе локальной LLM с вызовами 10 MCP tools
│   ├── eval_judge.py           # LLM-as-a-Judge движок (Gemini/Local) с доверительными интервалами CI
│   ├── evaluator.py            # Модуль расчета агрегированных метрик качества
│   ├── full_eval_runner.py     # Оркестратор полного бенчмарка ($N=3$ прогона, медиана, регрессии)
│   ├── run_full_live_benchmark.py # Скрипт запуска полного живого бенчмарка
│   ├── run_real_books_test.py  # Тестирование на полных реальных книгах
│   ├── run_acceptance.py       # Автоматический запуск приемочного набора тестов
│   ├── baseline_runner.py      # Сравнение с базовыми моделями (Direct LLM vs MCP Agent)
│   ├── leakage_check.py        # Проверка отсутствия утечки данных между датасетами
│   ├── demo_e2e.py             # Интерактивная сквозная демонстрация 10 MCP-инструментов
│   ├── reports/                # Итоговые markdown-отчеты бенчмарков
│   │   ├── full_eval_report.md # Отчет полного бенчмарка (Phase 5)
│   │   ├── live_full_eval_report.md # Результаты живого прогона на полном датасете
│   │   ├── real_books_eval_report.md # Результаты на книгах Dedekam Seamanship и Sail Trim
│   │   └── failures_detail.md  # Детальный разбор единичных сбоев и классификация ошибок
│   └── raw/                    # Сырые логи и ответы агента в формате JSONL
│
├── tools/                      # Вспомогательные утилиты и облачная оркестрация
│   └── runpod/                 # Облачный конвейер для тяжелых моделей (Qwen2.5-VL 32B на RTX 4090/A5000)
│       ├── runpod_orchestrator.py # Оркестратор управления подами, SSH/SCP передачей и запуском
│       ├── runpod_api.py       # GraphQL API клиент (управление состоянием подов и биллингом)
│       ├── runpod_manager.py   # Высокоуровневый менеджер запуска, мониторинга и авто-останова
│       ├── run_build_32b.py    # Автономный скрипт пайплайна на 32B VLM внутри облака
│       ├── tui.py              # Rich TUI дашборд реального времени (GPU, vRAM, прогресс)
│       ├── logger.py           # Сессионный логгер с метриками t/s
│       ├── AGENT_GUIDE.md      # Руководство по управлению RunPod для ИИ-агентов
│       └── RUNPOD_TUI_PLAN.md  # Архитектурный план и спецификация TUI-монитора
│
├── tests/                      # Набор автоматизированных тестов pytest (45 тестов)
│   ├── test_builder.py         # Тесты парсеров, OCR, чанкера и сборщика
│   ├── test_export.py          # Тесты упаковки bookpack и Ed25519 подписи (RFC 8032)
│   ├── test_rules_pipeline.py  # Тесты извлечения claims, кластеризации и синтеза правил
│   ├── test_server.py          # Тесты 10 MCP-инструментов, LanceDB и графа
│   ├── test_invariants.py      # Проверка архитектурных инвариантов I0–I14
│   ├── test_qa_invariants_stress.py # Стресс-тестирование WAL, аварийного отключения и отката
│   ├── test_eval_dataset.py    # Валидация структуры и стратификации датасетов
│   ├── test_eval_judge.py      # Тесты работы оценочного судьи и калибровки рубрик
│   └── test_runpod_orchestrator.py # Тесты облачной оркестрации и API RunPod
│
├── poc/                        # Скрипты PoC валидации и проверки гипотез (Phase 0)
│   ├── p0_01_docling_crop.py   # Проверка качества кропа схем через Docling
│   ├── p0_02_vlm_stability.py  # Проверка стабильности и структурирования Qwen2.5-VL
│   ├── p0_03_lancedb_fts.py    # Проверка гибридного поиска LanceDB
│   ├── p0_04_e5_embeddings.py  # Проверка E5-large эмбеддингов
│   ├── p0_05_ocr_compare.py    # Сравнение OCR движков
│   ├── p0_06_ladybugdb.py      # Проверка графовых структур NetworkX
│   ├── p0_07_epub_geometry.py  # Проверка извлечения геометрии из EPUB
│   └── start_ollama.py         # Скрипт запуска локального Ollama с Flash Attention
│
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

```bash
# Интерактивная сборка (TUI предложит выбрать категорию T1/T2/T2.5/T3)
mkp-builder build --book "path/to/manual.pdf" --out "work/demo"

# Пакетная сборка с явным указанием категории T1 Base
mkp-builder build \
  --book "path/to/Illustrated_Seamanship.epub" \
  --tier "T1" \
  --profile "digital" \
  --lang "en" \
  --out "work/demo"

# Просмотр и ревью извлеченных правил через Rich CLI
mkp-builder review-rules --rules "work/demo/books/dedekam_seamanship/rules.jsonl"
```

### 4. Запуск MCP-сервера (`mkp-server`)

Сервер автоматически подхватывает настройки из `server_config.yaml` (по умолчанию `data/live_server_storage` для разработки):

```bash
# Просмотр сводного дашборда состояния хранилища (автоматически из server_config.yaml)
mkp-server info

# Явное указание другого хранилища или файла настроек
mkp-server info --storage "data/live_server_storage"
mkp-server info --config "server_config.yaml"

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

## 🧪 Тестирование и бенчмарки

```bash
# Запуск всех 45 автоматизированных тестов проекта
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

## ☁️ RunPod Cloud Pipeline (Zero-Touch GPU Orchestration)

Для тяжелой обработки реальных иллюстрированных книг с использованием флагманской мультимодальной модели **Qwen2.5-VL 32B** разработан модуль облачной оркестрации [`tools/runpod/`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/tools/runpod):

* **Zero-Touch автоматизация:** Поднимает или переиспользует под на **NVIDIA RTX 4090 / A5000 (24GB VRAM)**, автоматически находит шаблон `base_sia_mkp`, передает книги по прямому SCP и запускает конвейер.
* **Auto-Stop & Защита баланса:** По завершении экспорта и скачивания готовых `.bookpack.zip` под **автоматически выключается через RunPod API**, останавливая тарификацию ($0/час).
* **Интерактивный TUI дашборд:** Отображение в реальном времени состояния GPU, VRAM, t/s и хода обработки страниц через Rich TUI.
* **Локальное логирование:** Сессии фиксируются в `tools/runpod/logs/session_*.log` с сохранением метрик GPU, скорости генерации (t/s) и контекста ошибок.
* **Документация и спецификация:**
  * 📄 [`tools/runpod/AGENT_GUIDE.md`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/tools/runpod/AGENT_GUIDE.md) — Исчерпывающее руководство для ИИ-агентов.
  * 📄 [`tools/runpod/RUNPOD_TUI_PLAN.md`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/tools/runpod/RUNPOD_TUI_PLAN.md) — Спецификация интерактивного Rich TUI дашборда и телеметрии.

---

## 📋 Статус проекта

* ✅ **Phase 0:** PoC & Validation (7/7 проверок пройдено).
* ✅ **Phase 1:** `mkp-builder` Core (Парсинг + VLM + Верификация + Чанкинг).
* ✅ **Phase 2:** `mkp-builder` Complete (Триплеты + Экспорт базового архива).
* ✅ **Phase 2.1:** `mkp-builder` Rules Pipeline & Signed Bookpack v0.3.0 (8/8 задач PASS, 100% тестов).
* ✅ **Phase 3:** `mkp-server` 4-Tier Storage, WAL/Rollback (I0–I14) & 10 FastMCP Tools (8/8 задач PASS).
* ✅ **Phase 4:** QA & Acceptance (100% PASS, 0% Hallucinations, 15/15 Инвариантов, `acceptance_report.md`).
* ✅ **Phase 5:** Full Evaluation & Quality Benchmark (Spec v1.1, 114 вопросов, Offline MCP Agent, Gemini LLM-as-a-Judge, `full_eval_report.md`).


