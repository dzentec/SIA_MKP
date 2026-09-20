# POC Report — Phase 0
**Дата:** TODO
**Автор:** TODO

---

## T0-01 — Docling figure crop
**Статус:** ⬜ Не начато
**Версия Docling:** TODO
**Решение:** TODO
**Особые случаи:** TODO

---

## T0-02 — VLM stability (qwen2.5vl:7b)
**Статус:** ⬜ Не начато
**Точность diagram_type:** TODO / TODO = TODO%
**Среднее время ответа:** TODO с
**Зависания:** TODO
**Решение:** TODO

---

## T0-03 — LanceDB FTS (кириллица)
**Статус:** ⬜ Не начато
**Recall (default):** TODO%
**Recall (ngram min=2,max=4):** TODO%
**Токенизатор выбран:** TODO
**Решение:** TODO

---

## T0-04 — e5-large RU<->EN
**Статус:** ⬜ Не начато
**Mean cosine без префиксов:** TODO
**Mean cosine с префиксами:** TODO
**Разница:** TODO
**Кросс-языковый recall@5:** TODO%
**Скорость индексации (CPU):** TODO чанков/с
**Решение:** Префиксы query:/passage: обязательны ✅

---

## T0-05 — OCR engine
**Статус:** ⬜ Не начато
**RapidOCR CER:** TODO%   | Скорость: TODO с/стр
**Tesseract CER:** TODO%   | Скорость: TODO с/стр
**Движок выбран:** TODO
**Решение:** TODO

---

## T0-06 — LadybugDB Windows/Python 3.11
**Статус:** ⬜ Не начато
**Установка:** TODO
**Версия:** TODO (для пина в pyproject.toml)
**CRUD:** TODO
**Параметризованный MATCH:** TODO
**Persistence:** TODO
**Fallback (NetworkX):** TODO
**Решение:** TODO

---

## T0-07 — EPUB geometry
**Статус:** ⬜ Не начато
**Spine mapping:** TODO
**Figure binding:** TODO
**location_ref формат:** TODO
**Решение:** TODO

---

## Решения для фиксации в конфиге

| Параметр | Значение |
|---|---|
| OCR engine | TODO |
| LanceDB FTS tokenizer | TODO |
| LadybugDB version pin | TODO |
| GPU VRAM на машине сборки | TODO ГБ |

---

## Готов к Phase 1: ⬜ TODO

**Блокеры (если есть):**
- TODO
