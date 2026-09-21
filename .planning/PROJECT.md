# PROJECT: Maritime Knowledge Pipeline with Rules (MKP-R)

**Code:** MKP-R  
**Status:** In Progress (Phase 0, 1, 2 Complete; Phase 2.1 Defined)  
**Created:** 2026-09-20  
**Updated:** 2026-09-21  
**HLD Source:** `.init_doc/HLD_MKP-R_v3.1_1of2.md` & `.init_doc/HLD_MKP-R_v3.1_2of2.md` (HLD v3.1, единственный источник истины)

---

## Что строим

Система превращает морскую литературу, регламенты и судовые мануалы в структурированную офлайн-базу знаний и правил, предоставляя её автономному яхтенному советнику (SIA Advisor) через протокол MCP и статические guardrails. **100 % офлайн, Windows 11.**

Два самостоятельных продукта в одном репозитории:

| Продукт | Роль | Выход |
|---|---|---|
| **`mkp-builder`** | Парсинг → OCR → VLM → Чанкинг → Триплеты → Claims → Кластеризация → Синтез правил → Review → Guardrails → Экспорт | `.bookpack.zip` (v0.2) |
| **`mkp-server`** | Импорт архивов → Построение индексов (векторных, графовых, правил) → Обслуживание агентов по MCP (9 инструментов) | Работающая база + MCP-сервер |

Единица поставки — **самодостаточный `.bookpack.zip` v0.2**.

---

## Четырёхуровневая модель контента (4-Tier Content Hierarchy)

| Уровень | Описание | Правила | Статус |
|---|---|---|---|
| **T1: Base** | Морские книги, COLREGs, физика, MDA-002 | `approved` (полная трассировка) | 🟢 **MVP** |
| **T2: Yacht** | Мануалы судна (двигатель, электрика, риггинг) | `hypothesis` (`auto_marked`) | 🟡 **Stub** (пустые `[]`) |
| **T2.5: Voyage** | Лоции, круизные гайды, региональные правила | `region`-aware правила | 🟡 **Stub** (пустые `[]`) |
| **T3: Personal** | Справочники, кулинария, медицина | Без правил (search only) | 🟡 **Stub** (поиск чанков) |

---

## Зачем это нужно и ключевые принципы

1. **Zero Hallucination & Non-lie Policy**: Советник никогда не выдумывает правила. Каждое действие и порог трассируются до цитаты первоисточника (`RuleSource`: `doc_id`, `page`, `chunk_id`, `quote`). При отсутствии правила система честно отвечает «не найдено».
2. **Три уровня доставки знаний**:
   - **Static Guardrails**: ≤ 8000 символов критических/warning правил T1 в системном промпте (работают даже при сбое MCP).
   - **Dynamic Rules (`query_rules`)**: поиск применимых правил по контексту, телеметрии судна и архетипу.
   - **Search Chunks (`search_chunks`)**: семантический гибридный поиск по чанкам для развёрнутых объяснений.
3. **Замороженные контракты (Stub-паттерн)**: Формат Bookpack v0.2 и сигнатуры всех 9 MCP-инструментов зафиксированы с первого дня. Stub-уровни возвращают корректный пустой результат без ошибок.
4. **Zero Data Loss (визуальный слой)**: Каждая иллюстрация сохраняется в PNG и аннотируется VLM.
5. **Идемпотентность и кэширование**: Повторные прогоны не вызывают LLM/VLM заново.
6. **Blue-Green индексация**: Сервер не прерывает обслуживание во время пересборки индексов.

---

## Стек технологий

| Компонент | Версия / Спецификация | Продукт |
|---|---|---|
| Python | 3.11 / 3.14.4 | оба |
| Docling | ≥ 2.15 (RapidOCR) | builder |
| Tesseract / RapidOCR | `rus+eng` | builder |
| Ollama (VLM: qwen2.5vl:7b, Text: qwen2.5:7b) | Q4_K_M, FLASH_ATTENTION=1 | builder |
| Sentence-Transformers (multilingual-e5-large) | dim=1024, `query:`/`passage:` | server |
| LanceDB | ≥ 0.17 / 0.38+ | server |
| Graph Engine | NetworkX + `triplets.jsonl` (в перспективе LadybugDB) | server |
| FastMCP | ≥ 2.2 (pinned) | server |
| Rich / Typer | CLI & TUI прогресс-бары | оба |
| Windows 11 | Локальная офлайн-среда | оба |

---

## Контракт артефакта `.bookpack.zip` (v0.2)

```
bookpack.zip
├── manifest.yaml          # паспорт (bookpack_version: "0.2.0", schema_version: "1.0")
├── checksums.sha256       # контрольные суммы
├── base/                  # 🟢 T1 Base (заполнен в MVP)
│   ├── chunks.jsonl
│   ├── triplets.jsonl
│   ├── claims.jsonl
│   ├── rules.jsonl
│   ├── graph.duckdb / jsonl
│   └── guardrails.md      # скомпилированный промпт (≤8000 симв.)
├── yacht/                 # 🟡 T2 Yacht (stub: пустые [])
├── voyage/                # 🟡 T2.5 Voyage (stub: пустые [])
├── personal/              # 🟡 T3 Personal (stub: пустые [])
└── assets/                # PNG-фигуры
```

---

## MCP-инструменты сервера (9 инструментов)

1. **`documents/search_chunks(query, top_k=5, tier=None)`** — семантический гибридный поиск по чанкам.
2. **`documents/get_diagram_image(doc_id, page)`** — получение иллюстрации (с защитой от path traversal).
3. **`documents/get_related_entities(entity_id)`** — граф связей сущности.
4. **`documents/get_book_manifest(doc_id)`** — метаданные документа.
5. **`rules/query_rules(archetype, telemetry, domain, tier, region, status)`** — правила по текущему контексту.
6. **`rules/get_rule(rule_id)`** — получение правила по ID.
7. **`rules/get_rule_provenance(rule_id)`** — точные цитаты и источники правила.
8. **`rules/list_conflicts(rule_id)`** — конфликтующие правила.
9. **`rules/get_guardrails()`** — скомпилированные static guardrails.

---

## Критерии готовности MVP

1. `mkp-builder` выполняет полный конвейер: парсинг → VLM → чанки → триплеты → claims → кластеризация → синтез правил → компиляция guardrails → экспорт `.bookpack.zip` v0.2.
2. `mkp-server` импортирует архив, строит LanceDB + Graph + Rules индексы, отдаёт все 9 MCP-инструментов.
3. 15+ верифицированных правил T1 с цитатами.
4. Golden Dataset: Hallucination rate = 0, Rule recall ≥ 0.8, Citation rate ≥ 0.9.
