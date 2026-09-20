# PLAN — Phase 0: PoC & Validation
# Maritime Knowledge Pack (MKP)

**Phase:** 0
**Mode:** spike
**Duration:** 0.5–1 день
**Requirements:** REQ-P0-01..07
**Source of truth:** `.init_doc/HLD_Tools_MCP_v1.5.md` §13, §14
**Gate:** все 7 проверок должны пройти → отчёт `POC_REPORT.md` → только тогда Phase 1

---

## Цель

Закрыть все технические риски из HLD §14 **до начала основной разработки**.
Phase 0 — чистый spike: код пишется в `poc/` и **не переносится в продакшен** как есть.
Каждая проверка заканчивается явным решением «принято» / «альтернатива X» / «блокер».

---

## Структура файлов

```
.planning/phase-0/
  PLAN.md          <- этот файл
  POC_REPORT.md    <- итоговый отчёт (создаётся в конце)

poc/
  p0_01_docling_crop.py
  p0_02_vlm_stability.py
  p0_03_lancedb_fts.py
  p0_04_e5_embeddings.py
  p0_05_ocr_compare.py
  p0_06_ladybugdb.py
  p0_07_epub_geometry.py
  assets/          <- тестовые изображения и документы
  requirements_poc.txt
```

---

## Зависимости между задачами

```
P0-01 (Docling) ---> P0-02 (VLM)   [изображения от P0-01 идут в P0-02]
P0-01 (Docling) ---> P0-07 (EPUB)  [опционально - схожие инструменты]

P0-03, P0-04, P0-05, P0-06 - независимы, можно выполнять параллельно

Все 7 ---> POC_REPORT.md
```

**Волна 1 (запускать первой):** P0-01
**Волна 2 (параллельно):** P0-02, P0-03, P0-04, P0-05, P0-06, P0-07

---

## Задачи

---

### T0-01 — Docling: кроп фигур из PDF
**REQ:** REQ-P0-01
**Риск:** векторная графика может не извлекаться в растровом виде при `images_scale=2.0`

**Что делаем:**
1. Установить `docling >= 2.15`
2. Взять любую главу морского PDF (минимум 3-5 схем/рисунков, желательно с векторной графикой)
3. Написать скрипт `poc/p0_01_docling_crop.py`:
   - `PdfPipelineOptions(generate_picture_images=True, images_scale=2.0)`
   - Извлечь все `PictureItem` из документа
   - Сохранить PNG в `poc/assets/crops/` с именованием `{book_id}_p{page}_fig{idx}.png`
   - Напечатать таблицу: страница, bbox, размер файла, тип (растр/вектор если определяется)
4. Визуально проверить `poc/assets/crops/` — все ли схемы извлечены, не обрезаны ли, читаемы ли

**Acceptance criteria:**
- [ ] Все видимые в PDF фигуры представлены как PNG
- [ ] Векторная графика конвертирована в растр (не пустой файл)
- [ ] Масштаб 2.0 даёт достаточное разрешение для VLM (минимум 512x512 для типичной схемы)
- [ ] Именование `{book_id}_p{N}_fig{N}.png` работает без коллизий

---

### T0-02 — VLM: стабильность qwen2.5vl:7b
**REQ:** REQ-P0-02
**Риск:** зацикливание модели, нестабильный JSON, ошибки на неприменимых блоках
**Зависимость:** T0-01 (нужны изображения)

**Предусловие:** Ollama запущен, модель `qwen2.5vl:7b` (Q4_K_M) загружена

**Что делаем:**
1. Написать скрипт `poc/p0_02_vlm_stability.py`
2. Переменная окружения: `OLLAMA_FLASH_ATTENTION=1`
3. Промпт версии `2.0` - запрашивает JSON:
   ```json
   {
     "diagram_type": "maneuver|knot|equipment|polar|map|table_figure|other",
     "description": "...",
     "maneuver": {...} | null,
     "knot": {...} | null,
     ...остальные типы null...
   }
   ```
4. Параметры: `num_predict=512`, `format="json"`, `timeout=45s`
5. Прогнать на >= 10 изображениях из `poc/assets/crops/`
6. Зафиксировать: время ответа, валидность JSON, точность diagram_type, зависания

**Acceptance criteria:**
- [ ] JSON парсируется без исключений в >= 95% случаев
- [ ] `diagram_type` верен (ручная оценка) в >= 95% случаев
- [ ] Неприменимые блоки = `null` в >= 95% случаев
- [ ] Нет зависания > 45 с (или <= 1 случай на сэмпл)
- [ ] `OLLAMA_FLASH_ATTENTION=1` реально ускоряет (сравнить с выключенным)

---

### T0-03 — LanceDB FTS: кириллица
**REQ:** REQ-P0-03
**Риск:** встроенный токенизатор Tantivy может плохо сегментировать кириллицу

**Что делаем:**
1. Установить `lancedb >= 0.17`
2. Написать скрипт `poc/p0_03_lancedb_fts.py`:
   - 20-30 коротких текстов на русском (морская терминология)
   - Индекс с настройками по умолчанию
   - Индекс с ngram-токенизатором (min=2, max=4)
   - Поиск по: отдельным словам, словоформам (рифы/рифа/риф), составным терминам
3. Запросы: "риф", "гика шкот", "брасопить реи", EN-запрос среди RU-документов
4. Сравнить recall: default vs ngram

**Acceptance criteria:**
- [ ] Default или ngram токенизатор: recall >= 0.70 на тестовом наборе
- [ ] FTS работает вместе с векторным поиском (гибридный режим)
- [ ] Зафиксирована рекомендация: `default` или `ngram(min=2,max=4)`

---

### T0-04 — e5-large: качество RU<->EN эмбеддингов
**REQ:** REQ-P0-04
**Риск:** без обязательных префиксов `query:`/`passage:` качество деградирует

**Что делаем:**
1. Установить `fastembed`, модель `intfloat/multilingual-e5-large` (dim=1024)
2. Написать скрипт `poc/p0_04_e5_embeddings.py`
3. 10 RU-запросов + 10 соответствующих EN-пассажей (морская тематика)
4. Эксперименты:
   - A: без префиксов
   - B: с префиксами `query:` / `passage:`
   - C: кросс-языковый RU-запрос -> EN-пассажи
   - D: EN-запрос -> RU-пассажи
5. Метрика: cosine similarity правильные vs случайные пары

**Acceptance criteria:**
- [ ] Вариант B (с префиксами): mean cosine >= 0.75 для правильных пар
- [ ] Вариант B значимо лучше A (разница >= 0.05)
- [ ] Кросс-языковый RU->EN recall@5 >= 0.80
- [ ] Оценить скорость индексации на CPU (чанков/с)

---

### T0-05 — OCR: RapidOCR vs Tesseract на кириллице
**REQ:** REQ-P0-05
**Риск:** RapidOCR может плохо справляться с русским текстом на сканах

**Предусловие:** скан страницы с русским текстом (1-2 страницы)

**Что делаем:**
1. Установить `rapidocr-onnxruntime`, `pytesseract` + Tesseract с `rus+eng`
2. Написать скрипт `poc/p0_05_ocr_compare.py`
3. Прогнать оба движка через `PdfPipelineOptions(ocr_options=...)` на одинаковых изображениях
4. Метрики: CER/WER, скорость (сек/страница), качество разметки абзацев

**Acceptance criteria:**
- [ ] Выбран один движок с явным обоснованием
- [ ] CER/WER задокументированы
- [ ] Движок работает через `PdfPipelineOptions` (не обходя Docling)
- [ ] Результат зафиксирован в `POC_REPORT.md` как решение для REQ-B02

---

### T0-06 — LadybugDB: Windows/Python 3.11
**REQ:** REQ-P0-06
**Риск:** молодой форк (~11 мес.), колёса под Windows/Python 3.11 могут отсутствовать

**Что делаем:**
1. Попытаться установить: `pip install ladybugdb`
2. Если колёс нет - поискать на PyPI, GitHub Releases, альтернативные источники
3. Написать скрипт `poc/p0_06_ladybugdb.py`, проверить **реальные** Cypher-запросы:
   - CRUD: CREATE, READ, UPDATE (через MERGE), DELETE
   - Параметризованный MATCH: `db.execute("MATCH (n:Entity {name: $name}) RETURN n", {"name": "грот"})`
   - Чтение после перезаписи (проверить persistence)
   - Fallback: NetworkX + triplets.jsonl если LadybugDB недоступен
4. Зафиксировать точную версию для пина в `pyproject.toml`

**Acceptance criteria:**
- [ ] `pip install ladybugdb` успешен на Windows 11 / Python 3.11 (или workaround задокументирован)
- [ ] CRUD-запросы работают без ошибок
- [ ] Параметризованный MATCH возвращает правильный результат
- [ ] Persistence: данные сохраняются после перезапуска Python-процесса
- [ ] ИЛИ: если LadybugDB недоступен - NetworkX fallback задокументирован как основной путь v1

---

### T0-07 — EPUB: геометрия спайна и привязка фигур
**REQ:** REQ-P0-07
**Риск:** Docling может не привязывать фигуры EPUB к spine_index; виртуальная нумерация неочевидна

**Предусловие:** EPUB-файл (любая книга или техн. документ)

**Что делаем:**
1. Написать скрипт `poc/p0_07_epub_geometry.py`
2. Через Docling распарсить EPUB: `converter.convert("test.epub").document`
3. Построить карту спайна: `spine_index -> href, title` для каждой главы
4. Для каждой `PictureItem` проверить:
   - spine_index (или эквивалентное поле)
   - `location_ref` вида `epub:s{N}#{anchor}`
   - `page_number` = виртуальная страница = spine_index
5. Если Docling не даёт spine_index нативно - написать маппер через `ebooklib`

**Acceptance criteria:**
- [ ] Карта спайна строится: `spine_index -> href, title`
- [ ] Каждая фигура привязана к spine_index (не None)
- [ ] `location_ref` вида `epub:s{N}#{anchor}` формируется корректно
- [ ] Несколько чанков из одной главы: одинаковый `page_number`, разный `anchor`
- [ ] Подход задокументирован в `POC_REPORT.md`

---

## Тестовые данные

| Файл | Нужен для | Откуда взять |
|---|---|---|
| Морской PDF с рисунками (>= 5 схем) | T0-01, T0-02 | Bowditch, Дедекам, OpenLibrary |
| Скан страницы с RU-текстом | T0-05 | Отсканированная страница / PNG с шумом |
| EPUB файл (любой техн. документ) | T0-07 | Project Gutenberg, любой EPUB |

---

## Установка окружения

```bash
# Создать виртуальное окружение
python -m venv .venv-poc
.venv-poc\Scripts\activate

# poc/requirements_poc.txt:
# docling>=2.15
# lancedb>=0.17
# fastembed
# rapidocr-onnxruntime
# pytesseract
# ollama
# pydantic>=2.0
# rich>=13.0
# ebooklib

pip install -r poc/requirements_poc.txt
```

---

## Выходные артефакты Phase 0

| Артефакт | Путь | Содержание |
|---|---|---|
| Скрипты spike | `poc/p0_0*.py` | Самодостаточные скрипты для каждой проверки |
| Тестовые ассеты | `poc/assets/` | Изображения, документы |
| Итоговый отчёт | `.planning/phase-0/POC_REPORT.md` | Решение по каждому из 7 рисков |

---

## Acceptance Gate Phase 0

Переход к Phase 1 разрешён **только** если:

1. ✅ T0-01: Docling кроп работает (векторная графика в растр)
2. ✅ T0-02: VLM JSON-стабильность >= 95%, нет зависаний
3. ✅ T0-03: FTS кириллица приемлема (хотя бы один вариант >= 0.70 recall)
4. ✅ T0-04: e5 с префиксами mean cosine >= 0.75, recall@5 >= 0.80
5. ✅ T0-05: OCR движок выбран и задокументирован
6. ✅ T0-06: LadybugDB работает ИЛИ NetworkX-fallback задокументирован как v1-путь
7. ✅ T0-07: EPUB spine mapping и figure binding работают

**POC_REPORT.md создан -> STATE.md обновлён -> git commit -> Phase 1**
