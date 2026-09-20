# PLAN — Phase 1: `mkp-builder` Core Pipeline
# Maritime Knowledge Pack (MKP)

**Phase:** 1  
**Mode:** standard  
**Duration:** 2.5–3 дня  
**Requirements:** REQ-B01, REQ-B02, REQ-B03, REQ-B04, REQ-B05, REQ-B08, REQ-B09, REQ-C01, REQ-C02, REQ-C03, REQ-C04  
**Source of truth:** `.init_doc/HLD_Tools_MCP_v1.5.md` §4, §5, §9, §13  

---

## Цель

Построить рабочий конвейер: парсинг документов (PDF/EPUB/DOCX) → OCR-маршрутизация → VLM-аннотация → 3-ступенчатая верификация → чанкинг с TUI (Rich) и логированием.
Результат: `chunks.jsonl` + `pages.jsonl` + `qa_review_queue.jsonl` + ассеты в рабочей директории.

---

## Задачи по волнам

### Wave 1: Foundation & Shared Contract (`mkp-common`)
- **T1-01 (REQ-C01, REQ-C02, REQ-C04):** `pyproject.toml`, структура пакетов `src/mkp_common`, `src/mkp_builder`, `src/mkp_server`. Pydantic v2 модели данных (`ChunkRecord`, `PageRecord`, `VlmAnnotation`, `VerificationResult`, `QaReviewItem`, `BookMetadata`, `BookpackManifest`).
- **T1-02 (REQ-C01, REQ-B09):** Утилиты `LocationRef` (`pdf:pN`, `docx:pN`, `epub:sN#anchor`), персистентный SHA-256 кэш (`work/cache/vlm_cache.json`) и логирование.

### Wave 2: Document Ingestion & Figures
- **T1-03 (REQ-B01, REQ-C03):** Парсинг PDF (Docling `generate_picture_images=True`, `images_scale=2.0`, `{book_id}_p{page_num}_fig{idx}.png`, таблицы в MD), EPUB (ebooklib spine map + zipfile fallback), DOCX.
- **T1-04 (REQ-B02):** OCR-маршрутизация: профили `digital`, `scanned`, `mixed` (порог плотности текста). RapidOCR (`RapidOcrOptions`) / Tesseract.

### Wave 3: VLM Annotation & 3-Stage Verification
- **T1-05 (REQ-B03, REQ-C03):** VLM аннотация через Ollama (`qwen2.5vl:7b`, Prompt 2.0, discriminated union: `maneuver`, `knot`, `equipment`, `polar`, `map`, `table_figure`, `other`, `OLLAMA_FLASH_ATTENTION=1`).
- **T1-06 (REQ-B04):** Трёхступенчатая верификация: 1) Pydantic схема; 2) Текстовая согласованность (`qwen2.5:7b`); 3) Визуальный критик (`qwen2.5vl:7b`). Обработка `needs_review` и запись в `qa_review_queue.jsonl`.

### Wave 4: Section & Table-Aware Chunking
- **T1-07 (REQ-B05):** Чанкинг: `max_tokens=512`, `overlap=64`, сохранение границ секций, таблицы как отдельные чанки, привязка `location_ref`, язык `lang`.

### Wave 5: Builder Orchestrator, Rich TUI & CLI
- **T1-08 (REQ-B08, REQ-B09):** Оркестратор конвейера: связка всех стадий, запись `pages.jsonl`, `chunks.jsonl`, `qa_review_queue.jsonl`, логирование `work/logs/builder_<ts>.log` и `ingest_report.md`.
- **T1-09 (REQ-B08, REQ-B10):** CLI интерфейс (`mkp-builder build`) и Rich TUI (7 прогресс-баров со счётчиками, кэш-хитами, ETA, `--headless`).

### Wave 6: Integration & Verification
- **T1-10:** Сквозное тестирование на реальных книгах из `.init_doc/source_doc/`, проверка идемпотентности кэша, структуры артефактов и порога `needs_review <= 5%`.
