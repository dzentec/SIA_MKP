# Phase 2.1 Plan: mkp-builder — Rules Pipeline & Bookpack v0.2

**Goal:** Реализовать конвейер извлечения утверждений (Claims), их кластеризации, синтеза формализованных правил (Rules), компиляции статических Guardrails, интеграцию предметной онтологии и экспорт артефакта `.bookpack.zip` стандарта v0.2 с 4-уровневой структурой (`base/`, `yacht/` stub, `voyage/` stub, `personal/` stub).

---

## 1. Задачи фазы 2.1

### Task 2.1-01: Онтология и Pydantic-схемы данных
- Разместить и валидировать YAML-онтологию: `ontology/sia_ontology.yaml`, `ontology/sia_relations.yaml`, `ontology/mapping.yaml`.
- Реализовать в `src/mkp_common/rules_schema.py` финальные замороженные схемы:
  - `RuleSource` (`doc_id`, `page`, `chunk_id`, `quote`)
  - `Claim` (`claim_id`, `text`, `type`, `subject`, `predicate`, `object`, `context`, `source`, `confidence`, `mapped`, `tier`)
  - `Cluster` (`cluster_id`, `topic`, `claims`, `dominant_type`, `archetypes`, `contradictions`, `coverage`, `tier`)
  - `RuleTrigger` (`ontology_field`, `operator`, `value`, `unit`)
  - `RuleAction` (`action_id`, `params`)
  - `Rule` (`rule_id`, `domain`, `archetype`, `triggers`, `triggers_logic`, `actions`, `severity`, `uncertainty`, `tier`, `region`, `origin`, `review_mode`, `requires_confirmation`, `sources`, `conflicts_with`, `status`, `created_at`, `updated_at`)
  - `ManifestV2` (`bookpack_version: "0.2.0"`, `schema_version: "1.0"`, `content` по 4 уровням).

### Task 2.1-02: Модуль извлечения утверждений (`claims.py`)
- Создать `src/mkp_builder/extract/claims.py`:
  - Запрос к текстовой модели Qwen2.5:7B (Ollama) с промптом из HLD §9.2.
  - Извлечение атомарных фактов, привязка к онтологии, извлечение точной цитаты (`quote` ≤ 200 симв.).
  - Кэширование запросов claims (SHA-256 чанка + model + prompt_ver).

### Task 2.1-03: Модуль кластеризации утверждений (`cluster.py`)
- Создать `src/mkp_builder/synthesize/cluster.py`:
  - Группировка claims по архетипам судов, доменам (`safety`, `trim`, `reefing`, `maneuver`) и сигналам телеметрии.
  - Детекция противоречий между источниками.

### Task 2.1-04: Модуль синтеза правил (`synthesize.py`)
- Создать `src/mkp_builder/synthesize/synthesize.py`:
  - Промпт синтеза правила из кластера (HLD §9.3) с сохранением reasoning для аудита.
  - Строгая валидация: проверка, что все значения в `triggers` присутствуют в цитатах claims (запрет выдумывания чисел).
  - Назначение severity (`critical`, `warning`, `info`) и uncertainty (`verified`, `hypothesis`).

### Task 2.1-05: Модуль компиляции Guardrails (`guardrails.py`)
- Создать `src/mkp_builder/compile/guardrails.py`:
  - Фильтрация T1 approved правил severity in (`critical`, `warning`).
  - Форматирование в компактный markdown `compiled_system_prompt.md` / `guardrails.md` объёмом ≤ 8000 символов.

### Task 2.1-06: Экспорт Bookpack v0.2 (`export/bookpack.py`)
- Обновить экспортер в `src/mkp_builder/export/bookpack.py`:
  - Формирование структуры `base/` (chunks, triplets, claims, rules, guardrails).
  - Формирование пустых заглушек `yacht/`, `voyage/`, `personal/`.
  - Генерация `manifest.yaml` (v0.2.0) и `checksums.sha256`.

### Task 2.1-07: CLI для ревью правил и Golden Rules Dataset
- Создать интерактивный/CLI режим ревью `mkp-builder review-rules`:
  - Просмотр правил, переход `draft` → `approved`.
  - Подготовка начального набора из 15+ верифицированных правил T1.

### Task 2.1-08: Тесты и валидация пайплайна
- Создать `tests/test_rules_pipeline.py`:
  - Тест валидации Pydantic схем (Claims, Rules, ManifestV2).
  - Тест извлечения claims на фикстурах.
  - Тест синтеза правил и детекции выдуманных порогов.
  - Тест компилятора guardrails (проверка лимита символов и структуры).
  - Тест экспорта и целостности `.bookpack.zip` v0.2.

---

## 2. Критерии приёмки Phase 2.1
1. Все схемы строго соответствуют HLD v3.1 §7.1.
2. `mkp-builder` успешно выполняет сквозной прогон со стадиями `claims` → `cluster` → `synthesize` → `guardrails` → `export`.
3. Сформированный `.bookpack.zip` v0.2 содержит корректные манифесты и папки `base/`, `yacht/` (stub), `voyage/` (stub), `personal/` (stub).
4. `guardrails.md` генерируется без ошибок и укладывается в лимит 8000 символов.
5. Набор тестов `pytest tests/test_rules_pipeline.py` проходит со 100% успехом.
