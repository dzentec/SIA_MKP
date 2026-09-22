# Phase 4: QA & Acceptance

**Phase Goal:** Финальная сквозная верификация качества и надёжности всей системы: сквозной прогон 30 вопросов Golden Dataset и 15+ эталонных правил T1 через `mkp-server`, автоматизированный бенчмаркинг точности поиска (Recall, Citation Rate, Hallucination Rate = 0), стресс-тестирование инвариантов надежности I0–I14 (инъекция сбоев питания, откат, целостность WAL) и выпуск официального отчёта приёмки (`qa/acceptance_report.md`).

**Source of Truth:** HLD v3.1, DIFF v3.3, DIFF v3.3.1 (Инварианты I0–I14), `REQUIREMENTS.md` (REQ-QA-01, REQ-QA-02, REQ-S01..S13).  
**Dependencies:** Phase 0 (PoC), Phase 1 (`mkp-builder` Core), Phase 2 (`mkp-builder` Triplets & Base Export), Phase 2.1 (`mkp-builder` Rules Pipeline & Bookpack v0.3), **Phase 3 (`mkp-server` 4-Tier Knowledge Base, Storage & 10 MCP Tools)**.

---

## Tasks Breakdown

| # | Task | Requirements | Deliverables | Checkpoint |
|---|------|--------------|--------------|------------|
| **T4-01** | **Golden Rules Dataset & Ground Truth Corpus** | REQ-QA-01 | `qa/golden_rules.json`, `qa/corpus_fixture.py` | 15+ эталонных правил T1 с точными цитатами первоисточника, триггерами и конфликтами; генератор эталонного артефакта `.bookpack.zip` |
| **T4-02** | **End-to-End QA Evaluator & Benchmark Engine** | REQ-QA-02, REQ-S05, REQ-S06, REQ-R01..R04 | `qa/evaluator.py`, `qa/metrics.py` | Автоматизированный бенчмаркинг 30 вопросов `golden_dataset.json` и правил: расчёт Rule Recall (≥ 0.8), Citation Rate (≥ 0.9), Search Precision/Recall, Hallucination Rate (= 0) |
| **T4-03** | **Invariants Failure Injection & Stress Testing** | REQ-QA-02, REQ-S07, I0–I14 | `tests/test_qa_invariants_stress.py` | Симуляция аварийных отказов питания на каждом из 11 шагов WAL, повреждение архивов, проверка многоуровневого восстановления (Backup -> Fallback -> Factory) |
| **T4-04** | **Acceptance Suite Runner & Final Report** | REQ-QA-01, REQ-QA-02 | `qa/run_acceptance.py`, `qa/acceptance_report.md`, `.planning/phase-4/ACCEPTANCE.md` | Консольный раннер приёмки, генерация сводного markdown-отчёта со всеми метриками приёмки и фиксация готовности к релизу |

---

## Task Details

### T4-01: Golden Rules Dataset & Ground Truth Corpus (REQ-QA-01)
- Экспорт и структурирование `qa/golden_rules.json`:
  - 15+ эталонных правил T1, покрывающих домены `safety`, `trim`, `reefing`, `maneuver`.
  - Точные цитаты первоисточника (`RuleSource` с `doc_id`, `page`, `chunk_id`, `quote`).
  - Формализованные триггеры (`RuleTrigger` с `ontology_field`, `operator`, `value`, `unit`).
  - Двусторонние конфликты (`conflicts_with`).
- `qa/corpus_fixture.py`:
  - Генерация самодостаточного подписанного Bookpack v0.3.0 для книг корпуса Dedekam (`dedekam_sail_trim`, `dedekam_seamanship`) со всеми чанками, диаграммами, триплетами и правилами.

### T4-02: End-to-End QA Evaluator & Benchmark Engine (REQ-QA-02, REQ-S05, REQ-S06, REQ-R01..R04)
- Разработка модуля оценки `qa/evaluator.py`:
  1. **Семантический поиск (`search_chunks`):**
     - Прогон 30 вопросов `qa/golden_dataset.json`.
     - Проверка попадания целевого `expected_book` и `expected_page` в top-k (Recall@1, Recall@3, Recall@5).
     - Проверка наличия обязательных терминов `must_contain_terms` (Precision).
     - Расчёт **Hallucination Rate** (отсутствие несоответствующих/вымышленных чанков).
  2. **Операционные правила (`query_rules`):**
     - Прогон тестовых телеметрических векторов (TWS=15..35kt, Heel=15..40°, различные архетипы: `monohull`, `performance_multihull`).
     - Расчёт **Rule Recall** (доля сработавших релевантных правил, порог ≥ 0.8).
     - Расчёт **Citation Rate** (доля правил с верифицированными цитатами первоисточника, порог ≥ 0.9).
  3. **Граф знаний (`get_related_entities`):**
     - Проверка точности связей по триплетам из `golden_dataset.json` (порог ≥ 0.90).
  4. **Статические ограничения (`get_guardrails`):**
     - Проверка длины guardrails (≤ 8000 символов) и наличия ключевых инвариантов безопасности.

### T4-03: Invariants Failure Injection & Stress Testing (REQ-QA-02, REQ-S07, I0–I14)
- Комплекс стресс-тестов в `tests/test_qa_invariants_stress.py`:
  - **Power-loss Injection:** прерывание процесса обновления на каждом шаге конвейера (до backup, во время backup, во время staging, во время swap) и верификация автоматического восстановления при старте через WAL (I0, I7, I9).
  - **Corrupted Backup Recovery:** эмуляция повреждения backup и проверка работы 3-х сценариев аварийного восстановления (I5, I8, I11).
  - **Sequential Update Storm:** последовательное применение цепочки обновлений (v1 -> v2 -> v3) с дельтами и проверкой сохранения целостности `generation` и `base.json`.
  - **Path Traversal & Security Fuzzing:** стресс-тест инструмента `get_diagram_image` на различные формы атак обхода путей (`..`, `%2e%2e`, unicode escape).

### T4-04: Acceptance Suite Runner & Final Report (REQ-QA-01, REQ-QA-02)
- Создание исполняемого раннера `qa/run_acceptance.py`:
  - Запуск полного цикла приёмки: развёртывание тестового `mkp-server`, прогон бенчмарка, сбор метрик, выполнение тестов инвариантов.
  - Формирование отчёта `qa/acceptance_report.md` со сводными таблицами результатов.
- Создание `.planning/phase-4/ACCEPTANCE.md`.

---

## Success Criteria (Критерии завершения Phase 4)
1. **Hallucination Rate = 0.0%** на 30 вопросах Golden Dataset.
2. **Rule Recall ≥ 0.80** и **Citation Rate ≥ 0.90** на эталонном наборе правил T1.
3. **Triplets Accuracy ≥ 0.90** на графовых запросах.
4. Все 15 инвариантов надежности (I0–I14) успешно проходят стресс-тесты с инъекцией сбоев.
5. `Static guardrails` скомпилированы и не превышают 8000 символов.
6. 100% прохождение всех тестов проекта (`pytest`).
7. Отчёт приёмки `qa/acceptance_report.md` сформирован и зафиксирован.
