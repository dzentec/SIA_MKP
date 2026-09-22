# Phase 2.1 Plan: mkp-builder — Rules Pipeline & Bookpack v0.3

**Goal:** Реализовать конвейер извлечения утверждений (Claims), их кластеризации, синтеза формализованных правил (Rules), компиляции статических Guardrails, интеграцию предметной онтологии и экспорт артефакта `.bookpack.zip` стандарта **v0.3.0** с 4-уровневой структурой (`base/`, `yacht/` stub, `voyage/` stub, `personal/` stub), **per-artifact SHA-256**, цифровой подписью **Ed25519** (Инвариант I13), матрицей совместимости (Инвариант I14) и поддержкой интерактивного выбора категории документа в TUI.

---

## 1. Задачи фазы 2.1

### Task 2.1-01: Онтология и Pydantic-схемы данных (v0.3.0)
- Разместить и валидировать YAML-онтологию: `ontology/sia_ontology.yaml`, `ontology/sia_relations.yaml`, `ontology/mapping.yaml`.
- Реализовать в `src/mkp_common/rules_schema.py` финальные замороженные схемы:
  - `RuleSource` (`doc_id`, `page`, `chunk_id`, `quote`)
  - `Claim` (`claim_id`, `text`, `type`, `subject`, `predicate`, `object`, `context`, `source`, `confidence`, `mapped`, `tier`)
  - `Cluster` (`cluster_id`, `topic`, `claims`, `dominant_type`, `archetypes`, `contradictions`, `coverage`, `tier`)
  - `RuleTrigger` (`ontology_field`, `operator`, `value`, `unit`)
  - `RuleAction` (`action_id`, `params`)
  - `Rule` (`rule_id`, `domain`, `archetype`, `triggers`, `triggers_logic`, `actions`, `severity`, `uncertainty`, `tier`, `region`, `origin`, `review_mode`, `requires_confirmation`, `sources`, `conflicts_with`, `status`, `deprecated: bool = False`, `orphaned: bool = False`, `created_at`, `updated_at`)
  - `CompatibilityInfo` (`min_server_version: "1.0.0"`, `max_server_version: "2.x.x"`, `bookpack_schema: "1.0"`, `supported_bookpack_schemas: list[str]`)
  - `ManifestBase` (`t1_version: str`, `t1_hash: str`, `merged_at: str`)
  - `ManifestUser` (`t2_hash: Optional[str]`, `t25_hash: Optional[str]`, `t3_hash: Optional[str]`, `merged_at: Optional[str]`)
  - `ManifestV3` (`bookpack_version: "0.3.0"`, `schema_version: "1.0"`, `ontology_version: "0.1.0"`, `generation: int = 1`, `parent_hash: Optional[str] = None`, `user_id: str = "local"`, `base: ManifestBase`, `user: ManifestUser`, `compatibility: CompatibilityInfo`, `content: dict[str, Any]` с per-artifact hashes).

### Task 2.1-02: Модуль извлечения утверждений (`claims.py`)
- Создать `src/mkp_builder/extract/claims.py`:
  - Запрос к текстовой модели Qwen2.5:7B (Ollama) с промптом из HLD §9.2.
  - Извлечение атомарных фактов, привязка к онтологии, извлечение точной цитаты (`quote` ≤ 200 симв.).
  - Пропуск генерации claims для документов `T3: Personal` (только chunks для поиска).
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

### Task 2.1-06: TUI выбор категории, Экспорт Bookpack v0.3.0 & Ed25519 (`export/bookpack.py` + CLI)
- Интерактивный выбор в TUI (Rich Prompt):
  - Выбор категории (`T1: Base`, `T2: Yacht`, `T2.5: Voyage`, `T3: Personal`) при запуске без флага `--tier`.
  - Запрос региона (`--region`) при выборе `T2.5`.
- Поддержка CLI флагов: `--tier <T1|T2|T2.5|T3>` и `--region <name>`.
- Обновить экспортер в `src/mkp_builder/export/bookpack.py`:
  - Маршрутизация данных книги в соответствующий каталог: `base/`, `yacht/`, `voyage/`, `personal/`.
  - Формирование структуры `base/` (chunks, triplets, claims, rules, guardrails).
  - Генерация per-artifact контрольных сумм (`base/chunks.sha256`, `base/rules.sha256`, `base/guardrails.sha256`).
  - Генерация цифровой подписи Ed25519 (`signature.ed25519`) тестовым/сервисным ключом (I13).
  - Генерация `manifest.yaml` (v0.3.0) и `checksums.sha256`.
  - Упаковка в `.bookpack.zip` (и опционально подготовка под `.zst`).

### Task 2.1-07: CLI для ревью правил и Golden Rules Dataset
- Создать интерактивный/CLI режим ревью `mkp-builder review-rules`:
  - Просмотр правил, валидация цитат, перевод `draft` → `approved`.
  - Подготовка начального набора из 15+ верифицированных правил T1 (Golden Rules T1).

### Task 2.1-08: Тесты и валидация пайплайна
- Создать `tests/test_rules_pipeline.py`:
  - Тест валидации Pydantic схем (Claims, Rules, ManifestV3, CompatibilityInfo).
  - Тест извлечения claims и роутинга категорий T1/T2/T2.5/T3.
  - Тест синтеза правил и детекции выдуманных порогов.
  - Тест компилятора guardrails (проверка лимита символов и структуры).
  - Тест экспорта, per-artifact sha256 и верификации цифровой подписи Ed25519 (I13).

---

## 2. Критерии приёмки Phase 2.1
1. Все схемы строго соответствуют HLD v3.3.1 (Pydantic ManifestV3 с generation, compatibility, base/user).
2. TUI и CLI поддерживают интерактивный выбор и явное указание категории документа (`T1`, `T2`, `T2.5`, `T3`).
3. `mkp-builder` успешно выполняет сквозной прогон со стадиями `claims` → `cluster` → `synthesize` → `guardrails` → `export`.
4. Сформированный `.bookpack.zip` v0.3.0 содержит корректный манифест, per-artifact sha256, валидную цифровую подпись `signature.ed25519` и папки `base/`, `yacht/` (stub), `voyage/` (stub), `personal/` (stub).
5. `guardrails.md` генерируется без ошибок и укладывается в лимит 8000 символов.
6. Набор тестов `pytest tests/test_rules_pipeline.py` проходит со 100% успехом.
