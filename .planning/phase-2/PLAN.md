# PLAN — Phase 2: `mkp-builder` Complete (Triplets, Export & Golden Dataset)
# Maritime Knowledge Pack (MKP)

**Phase:** 2  
**Mode:** standard  
**Duration:** 2 дня  
**Requirements:** REQ-B06, REQ-B07, REQ-B10, REQ-QA-01  
**Source of truth:** `.init_doc/HLD_Tools_MCP_v1.5.md` §4.5, §4.6, §5, §11  

---

## Цель

1. Реализовать извлечение графовых триплетов (GraphRAG) через текстовую модель Ollama (`qwen2.5:7b`).
2. Реализовать упаковку и валидацию `.bookpack.zip` с манифестом целостности `files_sha256` (schema_version "1.5").
3. Добавить команду `mkp-builder export` и обновить `mkp-builder build` для автоматического создания архива.
4. Сформировать Golden Dataset (30 стратифицированных вопросов) для приёмочного тестирования.

---

## Задачи по волнам

### Wave 1: Triplet Extraction Engine (`REQ-B06`, `REQ-B09`)
- **T2-01:** Модуль экстракции триплетов (`src/mkp_builder/triplets.py`):
  - Промпт 2.0 для Ollama `qwen2.5:7b`.
  - Таксономии: Сущности (Парус, Снасть, Манёвр, ВетровойРежим, Узел, Опасность), Отношения (УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ, ТРЕБУЕТ_ДЕЙСТВИЯ, ПРИМЕНЯЕТСЯ_ПРИ, СВЯЗАН_С).
  - Нормализация сущностей и дедупликация триплетов.
  - Привязка provenance (`book_id`, `page_number`, `chunk_id`, `location_ref`).
  - SHA-256 кэширование запросов.

### Wave 2: Archive Packager & Manifest (`REQ-B07`, `REQ-C01`)
- **T2-02:** Экспортёр `.bookpack.zip` (`src/mkp_builder/exporter.py`):
  - Формирование `bookpack.json` с подсчётом `counts` и хешей `files_sha256`.
  - Упаковка в `.bookpack.zip` (`bookpack.json`, `book_metadata.json`, `pages.jsonl`, `chunks.jsonl`, `triplets.jsonl`, `qa_review_queue.jsonl`, `assets/`).
  - Функция проверки целостности архива `verify_bookpack_archive()`.

### Wave 3: CLI Export & Pipeline Integration (`REQ-B08`, `REQ-B10`)
- **T2-03:** Интеграция в оркестратор и CLI:
  - Добавление этапов экстракции триплетов и экспорта архива в `BuilderPipeline`.
  - CLI команда `mkp-builder export --book-id <id> --out <dir>`.
  - Обновление Rich TUI со счётчиками триплетов и статусом экспорта.

### Wave 4: Golden Dataset Creation (`REQ-QA-01`)
- **T2-04:** Сборка эталонного датасета `qa/golden_dataset.json` (30 вопросов со стратификацией по диаграммам, языкам, сканам, EPUB и графам).

### Wave 5: Tests & Verification
- **T2-05:** Модульные и интеграционные тесты (`tests/test_triplets.py`, `tests/test_export.py`, `tests/test_golden_dataset.py`).
