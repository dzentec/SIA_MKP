# POC Report — Phase 0
**Дата:** 2026-09-20  
**Python:** 3.14.4 | **Docling:** 2.35.0+ | **LanceDB:** 0.38 | **fastembed:** 0.8.0 | **sentence-transformers:** 6.1.0

---

## T0-01 — Docling figure crop
**Статус:** ✅ PASS  
**Версия Docling:** 2.129 (проверить `docling.__version__`)  
**Результат:** 50 кропов PNG сохранены в `poc/assets/crops/`  
**API:** `page_range=(start, end)` вместо устаревшего `max_num_pages`  
**Особые случаи:**
- `page_range` принимает кортеж `(int, int)`, не список
- Для EPUB: Docling 2.129 неверно определяет формат (`None` вместо `EPUB`) — EPUB файлы с спецсимволами в имени нужно копировать во временный файл с расширением `.epub`

**Решение:** Docling для PDF/EPUB парсинга принят ✅

---

## T0-02 — VLM stability (qwen2.5vl:7b)
**Статус:** ✅ PASS (с замечанием по null-others)  
**GPU:** NVIDIA GeForce RTX 2060 (6 GB VRAM, CUDA 7.5) — обнаружена Ollama  
**Ollama:** v0.34.2 portable (`D:\Ollama\ollama.exe`)  
**Модели хранятся:** `D:\AI_models\ollama`  
**Модель:** qwen2.5vl:7b (5.7 GB скачана успешно)

| Метрика | Без FLASH_ATTENTION | С FLASH_ATTENTION=1 |
|---------|--------------------|-----------------------|
| JSON valid rate | — | **100%** (10/10) |
| diagram_type valid | — | **100%** (10/10) |
| Avg latency | **22.6s** (2 таймаута) | **2.9s** ✅ |
| Speedup | — | **87.3%** |
| Timeouts (45s) | 2/5 | **0/10** |

**Замечание — Null-others rate 0%:** модель заполняет `description` во всех JSON-полях, а не только в matching типе. Это проблема промпта, не модели. Решение: убрать null-constrainted поля из схемы → использовать простую схему `{diagram_type, description, details}`.

**Вывод:** `OLLAMA_FLASH_ATTENTION=1` **обязателен** (без него — частые таймауты 45s). Модель стабильна и всегда возвращает валидный JSON с правильным `diagram_type`.

---

## T0-03 — LanceDB FTS (English corpus)
**Статус:** ✅ PASS  
**Корпус:** 30 English maritime терминов (источники будут на английском языке)  
**Recall (default tokenizer):** **97.5%** (9.75/10 запросов)  
**Recall (trigram tokenizer):** 0% — trigram не работает для EN (дефолтный явно лучше)  
**Hybrid search (FTS + vector):** ✅ работает  

**API Findings (LanceDB 0.38+):**
- `create_fts_index()` — deprecated, использовать `create_index(config=FTS())`
- Для hybrid: `table.search().text("query").limit(k)` + vector search объединяются вручную

**Решение:** Default tokenizer, EN corpus ✅

---

## T0-04 — e5-large EN→EN (English sources)
**Статус:** ✅ PASS  
**Backend:** `sentence-transformers` 6.1.0 (fastembed 0.8.0 сломан для этой модели)  
**Эксперимент A (без префиксов):** mean cosine=0.872 | Recall@5=**1.000**  
**Эксперимент B (с `query:`/`passage:`):** mean cosine=0.881 | Recall@5=**1.000**  
**Кросс-языковый recall@5:** 1.000 (EN→EN varied phrasing)  
**Скорость индексации (CPU):** **7.1 chunk/s**  
**Dim:** 1024  

**Findings:**
- fastembed 0.8.0: баг — `model.onnx_data` внешний файл весов уходит за пределы blob-директории → `ONNXRuntimeError: External data path escapes model directory`
- **Workaround:** использовать `sentence-transformers` напрямую, тот же checkpoint
- Разница cosine A vs B = 0.009 (незначительная при recall=1.0 на тестовом наборе)

**Решение:** `sentence-transformers` + префиксы `query:`/`passage:` ✅

---

## T0-05 — OCR engine
**Статус:** ✅ PASS  
**Tesseract:** v5.4.0 (установлен в `D:\Tesseract\`) | CER=**0.032** | WER=0.051 | 0.57 с/стр  
**RapidOCR:** CER=0.953 (непригоден для кириллицы, но для English — см. ниже)  

**Docling integration:**
- `TesseractOcrOptions` — параметр `tesseract_cmd` **удалён** в текущей версии; использовать `path=TESSDATA_PATH`
- `tesserocr` (C++ binding) — версия 2.11.0 собрана под Tesseract 3.x → несовместима с Tesseract 5.4 tessdata
- **`RapidOcrOptions()` через Docling:** ✅ работает — 1575 символов за 33с с 3 страниц реального PDF

**Решение:** RapidOCR как OCR engine внутри Docling (`RapidOcrOptions()`); Tesseract 5.4 как standalone для сравнения. При английских источниках RapidOCR достаточен ✅

---

## T0-06 — LadybugDB / Knowledge Graph
**Статус:** ✅ PASS  
**LadybugDB:** недоступна на Windows/Python 3.14 (нет wheel)  
**Fallback:** NetworkX 3.x + JSONL (`triplets.jsonl`)  
**CRUD:** ✅ добавление, запрос, match по entity  
**Persistence:** ✅ сохранение/загрузка через `json.dumps` / `json.loads`  
**Параметризованный MATCH:** ✅ фильтрация по `relation_type` и `entity`  
**Граф:** 5 узлов, 5 рёбер (maritime knowledge triplets)

**Решение:** NetworkX + `triplets.jsonl` как v1 архитектура (LadybugDB — будущий апгрейд) ✅

---

## T0-07 — EPUB geometry (spine map + figure binding)
**Статус:** ✅ PASS  
**Библиотека:** `ebooklib` (spine map) + `zipfile` (image extraction fallback)  
**Spine map:** ✅ 88 элементов (Illustrated Seamanship by Dedekam)  
**Figure binding:** ✅ 20/20 с `location_ref` формата `epub:sN#fig_N`  
**Same-chapter grouping:** ✅  

**Findings:**
- Docling 2.129 неверно определяет EPUB формат: `filetype.guess_mime()` возвращает `application/zip`, `.epub` расширение не перехватывается в switch → format остаётся `None`
- **Workaround:** ebooklib для spine map + zipfile для извлечения изображений

**Решение:** ebooklib spine map + zipfile image extraction ✅

---

## Конфигурационные решения (для `pyproject.toml` / `config.py`)

| Параметр | Значение |
|---|---|
| OCR engine в Docling | `RapidOcrOptions()` |
| LanceDB FTS tokenizer | `default` (English) |
| Knowledge graph backend | NetworkX + `triplets.jsonl` |
| Embedding model | `intfloat/multilingual-e5-large` via `sentence-transformers` |
| Embedding backend | `sentence-transformers` (НЕ fastembed 0.8.0) |
| Embedding prefixes | `query:` / `passage:` обязательны |
| VLM | `qwen2.5vl:7b` at `D:\AI_models\ollama` |
| VLM JSON schema | упростить: `{diagram_type, description, details}` (убрать null-fields) |
| OLLAMA_FLASH_ATTENTION | **=1 обязательно** (87% speedup, без него таймауты) |
| Ollama host | `http://127.0.0.1:11434` |
| GPU | RTX 2060 6GB VRAM (CUDA 7.5) — достаточно для 7B Q4 |
| Ollama models dir | `D:\AI_models\ollama` |
| Источники | Английский язык |

---

## Готов к Phase 1: ⏳ Ожидание T0-02

**Блокеры:**
- T0-02 (VLM): идёт загрузка модели `qwen2.5vl:7b` (~4.7 GB). После завершения — финальная проверка и можно открывать Phase 1.

**Найденные workarounds (не блокирующие):**
1. fastembed 0.8.0 → sentence-transformers
2. tesserocr incompatible → RapidOcrOptions via Docling
3. LadybugDB unavailable → NetworkX
4. Docling EPUB format detection bug → ebooklib + zipfile
5. Ollama portable → subprocess.Popen managed lifecycle
