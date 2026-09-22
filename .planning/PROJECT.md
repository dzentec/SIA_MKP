# PROJECT: Maritime Knowledge Pipeline with Rules (MKP-R)

**Code:** MKP-R  
**Status:** In Progress (Phase 0, 1, 2 Complete; Phase 2.1 Defined)  
**Created:** 2026-09-20  
**Updated:** 2026-09-22  
**HLD Source:** `.init_doc/HLD_MKP-R_v3.1_1of2.md`, `.init_doc/HLD_MKP-R_v3.1_2of2.md`, `.init_doc/DIFF HLD MKP-R v3.1 to v3.3.md`, `.init_doc/DIFF v3.3 to v3.3.1 — Обновление инвариантов.md` (HLD v3.3.1)

---

## Что строим

Система превращает морскую литературу, регламенты и судовые мануалы в структурированную офлайн-базу знаний и правил, предоставляя её автономному яхтенному советнику (SIA Advisor) через протокол MCP и статические guardrails. **100 % офлайн, Windows 11.**

Два самостоятельных продукта в одном репозитории:

| Продукт | Роль | Выход |
|---|---|---|
| **`mkp-builder`** | Парсинг → OCR → VLM → Чанкинг → Триплеты → Claims → Кластеризация → Синтез правил → Review → Guardrails → Подпись Ed25519 → Экспорт | `.bookpack.zip` / `.zst` (v0.3.0) |
| **`mkp-server`** | Импорт архивов и дельт (T1, User, Server) → Управление хранилищем (`active/`, `backup/`, `fallback/`, WAL) → Построение индексов → Обслуживание агентов по MCP (10 инструментов) | Работающая база + MCP-сервер |

Единица поставки — **самодостаточный и подписанный `.bookpack.zip` / `.zst` v0.3.0** с поддержкой раздельных дельт.

---

## Четырёхуровневая модель контента (4-Tier Content Hierarchy)

| Уровень | Описание | Правила | Статус |
|---|---|---|---|
| **T1: Base** | Морские книги, COLREGs, физика, MDA-002 | `approved` (полная трассировка, read-only для пользователя) | 🟢 **MVP** |
| **T2: Yacht** | Мануалы судна (двигатель, электрика, риггинг) | `hypothesis` (`auto_marked`) | 🟡 **Stub** (пустые `[]`) |
| **T2.5: Voyage** | Лоции, круизные гайды, региональные правила | `region`-aware правила | 🟡 **Stub** (пустые `[]`) |
| **T3: Personal** | Справочники, кулинария, медицина | Без правил (search only) | 🟡 **Stub** (поиск чанков) |

---

## Зачем это нужно и ключевые принципы (Инварианты v3.3.1)

1. **Zero Hallucination & Non-lie Policy**: Советник никогда не выдумывает правила. Каждое действие и порог трассируются до цитаты первоисточника (`RuleSource`: `doc_id`, `page`, `chunk_id`, `quote`). При отсутствии правила система честно отвечает «не найдено».
2. **Три уровня доставки знаний**:
   - **Static Guardrails**: ≤ 8000 символов критических/warning правил T1 в системном промпте (работают даже при сбое MCP).
   - **Dynamic Rules (`query_rules`)**: поиск применимых правил по контексту, телеметрии судна и архетипу.
   - **Search Chunks (`search_chunks`)**: семантический гибридный поиск по чанкам для развёрнутых объяснений.
3. **Раздельное обновление и жизненный цикл T1**: T1 поставляется сервисом и неизменяем пользователем. Дельты `T1-delta` и `User-delta` применяются независимо.
4. **Безопасность и целостность (I13, I14)**: Обязательная цифровая подпись Ed25519 (`signature.ed25519`), проверка матрицы совместимости (`compatibility`) до применения, per-artifact SHA-256.
5. **Гарантированный Rollback и WAL (I0–I10)**: 1 верифицированный backup (N-1), транзакционный WAL с fsync директорий, атомарная замена `renameat2(RENAME_EXCHANGE)` / `mv` + `fsync`, автоматический и ручной откат (одной кнопкой при валидном backup).
6. **Многоуровневая защита от сбоев (I8, I11)**: Цепочка восстановления `active` → `backup` → `fallback` (SquashFS R/O) → `USB factory`.
7. **User-layer Orphaning & Tombstones**: При обновлении T1 связанные user-правила не удаляются, а получают статус `orphaned=true`. Удаленные T1 элементы сохраняются как tombstones (`deprecated=true`) на 2 релиза.
8. **Запрет Force-update в море (I12)**: Любое обновление требует явного подтверждения шкипера.
9. **Zero Data Loss (визуальный слой)**: Каждая иллюстрация сохраняется в PNG и аннотируется VLM.
10. **Blue-Green пересборка индексов**: Сервер не прерывает обслуживание во время фоновой пересборки.

---

## Стек технологий

| Компонент | Версия / Спецификация | Продукт |
|---|---|---|
| Python | 3.11 / 3.14.4 | оба |
| Docling | ≥ 2.15 (RapidOCR) | builder |
| Tesseract / RapidOCR | `rus+eng` | builder |
| Ollama (VLM: qwen2.5vl:7b, Text: qwen2.5:7b) | Q4_K_M, FLASH_ATTENTION=1 | builder |
| Cryptography (Ed25519) | libsodium / cryptography | оба |
| Compression | zipfile / zstandard (`.zst`) | оба |
| Sentence-Transformers (multilingual-e5-large) | dim=1024, `query:`/`passage:` | server |
| LanceDB | ≥ 0.17 / 0.38+ | server |
| Graph Engine | NetworkX + `triplets.jsonl` (в перспективе LadybugDB) | server |
| FastMCP | ≥ 2.2 (pinned) | server |
| Rich / Typer | CLI & TUI прогресс-бары | оба |
| Windows 11 | Локальная офлайн-среда | оба |

---

## Контракт артефакта `.bookpack.zip` / `.zst` (v0.3.0)

```
bookpack.zip (.zst)
├── manifest.yaml          # паспорт v0.3.0 (generation, parent_hash, base, user, compatibility, content)
├── checksums.sha256       # контрольные суммы
├── signature.ed25519      # цифровая подпись Ed25519 (I13)
├── base/                  # 🟢 T1 Base (заполнен в MVP)
│   ├── chunks.jsonl
│   ├── chunks.sha256
│   ├── triplets.jsonl
│   ├── claims.jsonl
│   ├── rules.jsonl
│   ├── rules.sha256
│   ├── graph.duckdb / jsonl
│   └── guardrails.md      # скомпилированный промпт (≤8000 симв.)
├── yacht/                 # 🟡 T2 Yacht (stub: пустые [])
├── voyage/                # 🟡 T2.5 Voyage (stub: пустые [])
├── personal/              # 🟡 T3 Personal (stub: пустые [])
└── assets/                # PNG-фигуры
```

---

## MCP-инструменты сервера (10 инструментов)

1. **`documents/search_chunks(query, top_k=5, tier=None)`** — семантический гибридный поиск по чанкам.
2. **`documents/get_diagram_image(doc_id, page)`** — получение иллюстрации (с защитой от path traversal).
3. **`documents/get_related_entities(entity_id)`** — граф связей сущности.
4. **`documents/get_book_manifest(doc_id)`** — метаданные документа.
5. **`rules/query_rules(archetype, telemetry, domain, tier, region, status)`** — правила по текущему контексту.
6. **`rules/get_rule(rule_id)`** — получение правила по ID.
7. **`rules/get_rule_provenance(rule_id)`** — точные цитаты и источники правила.
8. **`rules/list_conflicts(rule_id)`** — конфликтующие правила.
9. **`rules/get_guardrails()`** — скомпилированные static guardrails.
10. **`system/get_bookpack_info()`** — поколение `generation`, версии, хеши слоёв и статус доступных обновлений.

---

## Критерии готовности MVP

1. `mkp-builder` выполняет полный конвейер: парсинг → VLM → чанки → триплеты → claims → кластеризация → синтез правил → компиляция guardrails → генерация Ed25519 подписи → экспорт `.bookpack.zip` v0.3.0.
2. `mkp-server` поддерживает архитектуру хранилища `/storage/`, валидацию Ed25519 и совместимости, WAL-транзакции, автоматический/ручной rollback, строит индексы и отдаёт 10 MCP-инструментов.
3. 15+ верифицированных правил T1 с цитатами.
4. Golden Dataset: Hallucination rate = 0, Rule recall ≥ 0.8, Citation rate ≥ 0.9.
