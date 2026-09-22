# MKP-R — Maritime Knowledge Pipeline with Rules

**Maritime Knowledge Pipeline with Rules (MKP-R)** — это 100% автономный (offline-first) конвейер для преобразования морской литературы, регламентов и судовой документации (PDF, EPUB, DOCX) в структурированную базу знаний и формализованных правил для **автономного яхтенного советника (SIA Advisor)** с обслуживанием по протоколу **Model Context Protocol (MCP)**.

---

## 🧭 Архитектура системы (HLD v3.3.1)

Система разделена на два независимых продукта в одном репозитории:

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
| **`T1: Base`** | `base/` | Морская классика, книги по парусам, физика, COLREGs, регламенты | Chunks + Triplets + Claims + **Approved Golden Rules** + **Guardrails** (Read-Only для пользователя) | 🟢 **MVP (Готово)** |
| **`T2: Yacht`** | `yacht/` | Мануалы судна: двигатель (Yanmar, Volvo), электрика (Victron), риггинг | Chunks + Claims + **Hypothesis Rules (`auto_marked`)** | 🟡 **Stub** (пустые `[]`) |
| **`T2.5: Voyage`** | `voyage/` | Лоции, Cruising Guides, альманахи, региональные правила | Chunks + Claims + **Region Rules (`region: caribbean/...`)** | 🟡 **Stub** (пустые `[]`) |
| **`T3: Personal`** | `personal/` | Справочники, кулинария, судовая медицина | **Только Chunks для поиска** (генерация правил пропускается) | 🟡 **Stub** (поиск чанков) |

---

## 🔒 Ключевые принципы и гарантии (Инварианты v3.3.1)

1. **Zero Hallucination Policy (Non-lie Policy):** Советник никогда не выдумывает правила. Каждое правило и порог строго проверяются по цитатам первоисточника (`RuleSource`: `doc_id`, `page`, `chunk_id`, `quote`). Выдуманные пороги отсекаются валидатором.
2. **Три уровня доставки знаний:**
   * **Слой 1 (Static Guardrails):** Скомпилированный markdown (`guardrails.md` ≤ 8000 симв.) внедряется прямо в системный промпт — безопасность гарантирована даже при сбое MCP.
   * **Слой 2 (Dynamic `query_rules`):** Запрос правил по текущей телеметрии (`tws`, `heel_angle`) и архетипу судна.
   * **Слой 3 (Deep `search_chunks`):** Семантический гибридный поиск по первоисточникам для развёрнутых объяснений.
3. **Цифровая безопасность (Инвариант I13):** Все пакеты и манифесты подписываются ключом Ed25519 (`signature.ed25519`) по схеме RFC 8032 с защитой от подделки на USB-носителях.
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
| **VLM (Vision-LLM)** | Qwen2.5-VL | `qwen2.5vl:7b Q4_K_M` via Ollama | Распознавание и структурирование морских схем |
| **Текстовая LLM** | Qwen2.5 | `qwen2.5:7b Q4_K_M` via Ollama | Извлечение триплетов, claims и синтез правил |
| **Embeddings** | Sentence-Transformers | `intfloat/multilingual-e5-large` (1024-dim) | Плотные векторные представления (`passage:` / `query:`) |
| **Vector DB** | LanceDB | `≥ 0.38` | Гибридный векторный и полнотекстовый поиск (FTS) |
| **Graph Engine** | NetworkX | `latest` | Граф знаний сущностей, морских терминов и связей |
| **MCP Server** | FastMCP | `≥ 2.2` (pinned) | Обслуживание бортового ИИ-советника |
| **Парсинг PDF/DOCX** | Docling | `≥ 2.15` (RapidOCR) | Извлечение структуры, таблиц и координат |
| **CLI & TUI** | Typer + Click + Rich | `latest` | TUI с интерактивным выбором категорий и таблицами ревью |

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

```bash
# Импорт подписанного пакета v0.3.0 в хранилище /storage/
mkp-server import "work/demo/out/dedekam_seamanship.bookpack.zip" \
  --storage "C:\marine_storage"

# Запуск MCP-сервера по протоколу stdio (для Claude Desktop / Open WebUI)
mkp-server serve --storage "C:\marine_storage"

# Откат к резервной копии (при необходимости)
mkp-server rollback --storage "C:\marine_storage" --mode auto
```

---

## 🧪 Тестирование

```bash
# Запуск всех 22 тестов проекта
pytest tests/ -v
```

### Структура тестов:
- `tests/test_parsers.py` — Проверка парсинга PDF, EPUB, DOCX и кропа схем.
- `tests/test_builder.py` — Проверка чанкера, верификатора и сквозного конвейера.
- `tests/test_triplets.py` — Извлечение графовых триплетов и нормализация.
- `tests/test_rules_pipeline.py` — Валидация Claims, онтологии, синтеза правил, Guardrails, per-artifact sha256 и подписи Ed25519.
- `tests/test_golden_dataset.py` — Валидация точности на 30 эталонных вопросах и 15+ Golden Rules.
- `tests/test_export.py` — Тестирование целостности архивов и детекции повреждений.

---

## 📂 Структура проекта

```
Doc2Rag/
├── .planning/               # GSD-планирование (PROJECT.md, ROADMAP.md, REQUIREMENTS.md, STATE.md)
│   ├── phase-0/             # Отчеты и скрипты PoC валидации
│   ├── phase-1/             # Планы базового конвейера
│   ├── phase-2/             # Планы триплетов и экспорта
│   ├── phase-2.1/           # План конвейера правил и Bookpack v0.3
│   └── phase-3/             # План MCP-сервера (хранилище, WAL, 10 инструментов)
├── ontology/                # Англоязычная онтология предметной области (YAML)
│   ├── sia_ontology.yaml    # Домены, архетипы, телеметрия, действия, аварии
│   ├── sia_relations.yaml   # Предикаты и отношения
│   └── mapping.yaml         # Двуязычный словарь синонимов (EN & RU)
├── qa/
│   └── golden_dataset.json  # 30 стратифицированных вопросов и эталонные правила
├── src/
│   ├── mkp_common/          # Pydantic-схемы (Claims, Rules, ManifestV3), LocationRef, логгер
│   ├── mkp_builder/         # Конвейер сборщика (парсинг, OCR, VLM, claims, synthesize, guardrails, export)
│   │   ├── extract/         # Извлечение Claims
│   │   ├── synthesize/      # Кластеризация и синтез правил
│   │   ├── compile/         # Компиляция статических Guardrails
│   │   └── export/          # Подписание Ed25519 и упаковка Bookpack v0.3.0
│   └── mkp_server/          # MCP-сервер (хранилище, WAL, LanceDB, NetworkX, 10 MCP tools)
├── tests/                   # Набор тестов pytest (22 теста)
├── poc/                     # Скрипты PoC валидации и утилиты запуска
└── pyproject.toml           # Конфигурация проекта, CLI entrypoints и зависимости
```

---

## 📋 Статус проекта

* ✅ **Phase 0:** PoC & Validation (7/7 проверок пройдено).
* ✅ **Phase 1:** `mkp-builder` Core (Парсинг + VLM + Верификация + Чанкинг).
* ✅ **Phase 2:** `mkp-builder` Complete (Триплеты + Экспорт базового архива).
* ✅ **Phase 2.1:** `mkp-builder` Rules Pipeline & Signed Bookpack v0.3.0 (8/8 задач PASS, 100% тестов).
* ⏳ **Phase 3:** `mkp-server` 4-Tier Storage, WAL/Rollback (I0–I14) & 10 FastMCP Tools.
* ⬜ **Phase 4:** QA & Acceptance (Сквозной прогон Golden Dataset + 15 эталонных правил).
