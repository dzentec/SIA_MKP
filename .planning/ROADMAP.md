# ROADMAP — Maritime Knowledge Pipeline with Rules (MKP-R)

**6 phases** | **40 requirements mapped** | All MVP requirements covered ✅

| # | Phase | Goal | Requirements | Success Criteria |
|---|-------|------|--------------|-----------------|
| 0 | PoC & Validation | Закрыть все технические риски до начала основной разработки | REQ-P0-01..07 | 7 (✅ PASS) |
| 1 | mkp-builder Core | Парсинг + VLM + верификация + чанкинг + TUI | REQ-B01..05, B08..09, C01..02, C03..04 | 5 (✅ PASS) |
| 2 | mkp-builder Triplets & Base Export | Триплеты + экспорт артефакта v1.5 + Golden Dataset base | REQ-B06..07, B10, QA-01 | 4 (✅ PASS) |
| 2.1 | mkp-builder Rules & Bookpack v0.3 | Онтология + Claims + Кластеризация + Синтез правил + Guardrails + Bookpack v0.3.0 + Ed25519 | REQ-R01..06, REQ-B07 | 6 (✅ PASS) |
| 3 | mkp-server | 4-уровневое хранилище + импорт дельт v0.3.0 + WAL/Rollback (I0–I14) + индексы + 10 MCP-инструментов | REQ-S01..13 | 7 (✅ PASS) |
| 4 | QA & Acceptance | Сквозной прогон Golden Dataset + 15+ эталонных правил + тест Rollback/WAL | REQ-QA-01, QA-02 | 5 (✅ PASS) |
| 5 | Full Evaluation & Quality Benchmark | Полный бенчмарк 2-х книг (95–110 вопросов, 7 блоков), Offline MCP Agent (Qwen), Baseline A/B/C, Gemini LLM-as-a-Judge (M1–M8) | REQ-EVAL-01..06 | 8 (✅ PASS) |
| 6 | MKP-Builder Pipeline Upgrade, Critic, Fallback & Image Filtering (v4.2) | 5 критических багфиксов, OllamaManager (single-GPU VRAM ≤30GB), 3-ступенчатый фильтр картинок (226 ➔ ~50, CPU+7B), двухступенчатый fail-open критик (32B), подсистема аварийного останова Fallback v4.2, TUI сигналы и звук | REQ-BLD-V2-01..11 | 9 (В процессе) |
| 7 | RUNPOD-H: Hybrid MKP Builder (RunPod + OpenRouter) | Гибридный конвейер (RunPod parse/VLM + ПК/OpenRouter LLM), OpenRouter Batch API (DeepSeek R1, 24h SLA), персистентность `pending_batch.json`, BalanceGuard ($10 limit), RateLimiter (150/10s), CircuitBreaker, изолированный Rich TUI | REQ-HYB-01..08 | 8 (Запланировано) |

---

## Phase 0: PoC & Validation (✅ Завершено)
**Goal:** Проверить все технические риски из HLD §14. 7 из 7 тестов пройдены успешно.

---

## Phase 1: mkp-builder — Core Pipeline (✅ Завершено)
**Goal:** Рабочий конвейер парсинг → VLM-аннотация → трёхступенчатая верификация → чанкинг с TUI и логированием.

---

## Phase 2: mkp-builder — Triplets & Base Export (✅ Завершено)
**Goal:** Экстракция триплетов (GraphRAG), упаковка базового артефакта, финализация CLI.

---

## Phase 2.1: mkp-builder — Rules Pipeline & Bookpack v0.3 (✅ Завершено)
**Goal:** Онтология, извлечение атомарных утверждений (Claims), кластеризация, синтез формализованных правил (Rules), компиляция Guardrails (≤ 8000 символов), экспорт артефакта `.bookpack.zip` стандарта **v0.3.0** (4 уровня контента: T1 Base + Stubs T2/T2.5/T3), генерация **per-artifact SHA-256** и цифровой подписи **Ed25519** (I13).  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-2.1/PLAN.md`

**Requirements:** REQ-R01, REQ-R02, REQ-R03, REQ-R04, REQ-R05, REQ-R06, REQ-B07

**Success Criteria:**
1. Онтология (`ontology/`) и Pydantic-модели (`mkp_common/rules_schema.py`) финализированы (включая `CompatibilityInfo`, `ManifestV3`, поля `deprecated` и `orphaned`).
2. `claims.py` извлекает атомарные утверждения с точными цитатами и маппингом на онтологию.
3. `synthesize.py` формирует объекты `Rule` со строгой валидацией числовых порогов триггеров.
4. `guardrails.py` компилирует markdown-файл правил (≤ 8000 символов).
5. Экспортер упаковывает `.bookpack.zip` / `.zst` v0.3.0 с каталогами `base/`, `yacht/` (stub), `voyage/` (stub), `personal/` (stub), `manifest.yaml`, `checksums.sha256`, per-artifact чексуммами и подписью `signature.ed25519` (I13).
6. Сформирован набор из 15+ верифицированных правил T1 (Golden Rules).

---

## Phase 3: mkp-server — 4-Tier Knowledge Base, Storage Lifecycle & 10 MCP Tools (✅ Завершено)
**Goal:** Полнофункциональный сервер: управление хранилищем `/storage/` (`active/`, `backup/`, `fallback/`, `staging/`, `failed/`), импорт архивов и раздельных дельт v0.3.0 с верификацией Ed25519 (I13) и совместимости (I14), транзакционный конвейер с WAL и гарантированным отбоем/Rollback (I0–I10), построение индексов (LanceDB + NetworkX Graph + Rules Store), **10 MCP-инструментов** (включая `get_bookpack_info`), изоляция T1 и orphaning-контроль.  
**Mode:** standard  
**Duration:** 2 дня  
**Plan:** `.planning/phase-3/PLAN.md`

**Requirements:** REQ-S01, REQ-S02, REQ-S03, REQ-S04, REQ-S05, REQ-S06, REQ-S07, REQ-S08, REQ-S09, REQ-S10, REQ-S11, REQ-S12, REQ-S13

**Success Criteria:**
1. Управление хранилищем `/storage/` с многоуровневой защитой `active` → `backup` → `fallback` (R/O SquashFS) → `USB factory` (I8, I11).
2. `mkp-server import` поддерживает монолитные bookpack v0.3.0, `T1-delta` и `User-delta` со строгой проверкой Ed25519 (I13) и `compatibility` (I14).
3. Транзакционный конвейер обновления с WAL, `fsync` на файл и каталог, атомарной заменой (`renameat2`) и автоматическим откатом к `backup/` при сбое (I1–I10).
4. Ручной откат одной командой/кнопкой при валидном backup и поддержка 3-х сценариев при поврежденном backup (I5).
5. Работают **10 MCP-инструментов**: 4 в `documents/`, 5 в `rules/` и 1 в `system/` (`get_bookpack_info`).
6. Пользовательские MCP-инструменты изолированы от модификации слоя T1.
7. При изменении T1 зависимые пользовательские правила помечаются `orphaned=true` без удаления.

---

## Phase 4: QA & Acceptance (✅ Завершено)
**Goal:** Сквозной прогон Golden Dataset через `mkp-server`, аудит точности правил и триплетов, верификация инвариантов надежности Rollback/WAL, финальный отчёт приёмки.  
**Mode:** qa  
**Duration:** 1 день  
**Plan:** `.planning/phase-4/PLAN.md`

**Requirements:** REQ-QA-01, REQ-QA-02

**Success Criteria:**
1. Hallucination rate = 0 на Golden Dataset (0.0%).
2. Rule recall ≥ 0.8 (87.5%); Citation rate ≥ 0.9 (100.0%).
3. 15+ правил с полной трассируемостью до первоисточника (15/15).
4. Прохождение тестов сбоя питания / отката обновлений (I0–I14: 100% PASS).
5. Отчёт приёмки (`acceptance_report.md` & `UAT.md`) зафиксирован.

---

## Phase 5: Full Evaluation & Quality Benchmark (✅ Завершено)
**Goal:** Реализация полноценного тестового стенда по спецификации **MKP-R Full Evaluation Spec v1.1**: расширенный датасет из 95–110 вопросов (7 блоков), автономный оффлайн-агент (Qwen2.5) с вызовом 10 MCP-инструментов, замеры Baseline A/B/C, проверка Data Leakage, судейство LLM-as-a-Judge (Gemini API), расчет 8 активных метрик (M1–M8) с доверительными интервалами (95% CI), регрессионный пул и автогенерация детального отчета `qa/reports/full_eval_report.md`.  
**Mode:** standard / ai-eval  
**Duration:** 2–3 дня  
**Plan:** `.planning/phase-5/PLAN.md`  
**Spec:** `.init_doc/MKP-R Full Evaluation Spec v1.1_1of2.md`, `.init_doc/MKP-R Full Evaluation Spec v1.1_2of2.md`

**Requirements:** REQ-EVAL-01, REQ-EVAL-02, REQ-EVAL-03, REQ-EVAL-04, REQ-EVAL-05, REQ-EVAL-06

**Success Criteria:**
1. Датасет `qa/golden_full_dataset.json` на 95–110 вопросов по 7 блокам (Sail Trim, Seamanship, Cross-Book, Negative, Adversarial, Guardrails, Update/Rollback — DEFERRED).
2. Модуль `qa/offline_mcp_agent.py` реализует автономного оффлайн-агента на базе локального Qwen2.5:7b, подключающегося к `mkp-server` через 10 MCP-инструментов с сохранением сырых трасс JSONL.
3. Модуль `baseline_runner.py` проводит замеры контрольных групп: Baseline A (No-MCP), Baseline B (Search-only) с фиксацией $\Delta \ge 20$ п.п. по Faithfulness.
4. Модуль `leakage_check.py` подтверждает отсутствие утечки данных (Leakage < 30%).
5. Модуль `eval_judge.py` на базе Gemini API оценивает утверждения, проверяет толерантность цитат (±1 стр, 0 ошибок книги), M3 Rule Recall, M4 Cross-Domain rubric (3 независимых судьи), M5/M6 Guardrails, M7 Refusals и M8 Adversarial.
6. Расчет доверительных интервалов (95% CI) по Wilson score и Bootstrap.
7. Регрессионный раннер `qa/regression_pool.json` с выборкой 10 вопросов.
8. Генерация итогового отчета `qa/reports/full_eval_report.md` с таксономией ошибок и атрибуцией причин.

---

## Phase 6: MKP-Builder Pipeline Upgrade, Dual-Stage Critic, Fallback Subsystem & 3-Stage Image Filtering (v4.2) (В процессе)
**Goal:** Кардинальное устранение проблемы овергенерации правил (сокращение с 800+ до 40–50 операционных правил на книгу), 3-ступенчатая фильтрация изображений (226 ➔ ~50 картинок перед VLM 32B, экономия 1+ ч GPU) и реализация полной подсистемы аварийного останова и защиты инвестиций в GPU (Fallback Spec v4.2).  
**Mode:** standard / pipeline-upgrade  
**Duration:** 2–3 дня  
**Plan:** `.planning/phase-6/PLAN.md`  
**Spec:** `.init_doc/MKP_Builder update.md`, `.init_doc/MKP_Builder update(critic_code).md`, `.init_doc/MKP_Builder update_Fallback Specification v4.2.md`, `.init_doc/Image Filtering for RUNPOD.md`

**Requirements:** REQ-BLD-V2-01, REQ-BLD-V2-02, REQ-BLD-V2-03, REQ-BLD-V2-04, REQ-BLD-V2-05, REQ-BLD-V2-06, REQ-BLD-V2-07, REQ-BLD-V2-08, REQ-BLD-V2-09, REQ-BLD-V2-10, REQ-BLD-V2-11

**Success Criteria:**
1. Устранены 5 критических багов генерации правил (нормализация префиксов `RULE-`, `Trigger.value` float/list, сериализация противоречий, фильтрация не сопоставленных claims, строгая проверка чисел).
2. `OllamaManager` гарантирует последовательную работу моделей без превышения 30 GB VRAM на одной GPU (7B filter $\to$ 32B VLM $\to$ 32B extractor $\to$ 32B critic).
3. 3-ступенчатый фильтр изображений (`RuleBasedImageFilter` CPU $\to$ `VLMImageFilter` Qwen VL 7B GPU $\to$ VLM 32B) отсекает 78% мусора (226 $\to$ ~50) без потери ценных ЧБ схем такелажа.
4. Двухступенчатый критик (`ClusterCritic` + `RuleCritic`) отсеивает описательные/справочные утверждения и доводит количество правил до 40–50 операционных инструкций.
5. Подсистема критика и VLM-фильтра строго fail-open: при ошибках парсинга или сбоях API пайплайн продолжает работу (`keep` / `uncertain`).
6. Реализована подсистема Fallback v4.2 (`src/mkp_builder/fallback/`): `HealthMonitor`, `KillSwitch`, `VLMFailTracker` (1–4 skip, 5 stop), `PodStopper` (RunPod API), `RetryHelper`, `BatchCircuitBreaker` (2 книги подряд -> STOP batch).
7. TUI-сигнализация (`SignalWatcher` на `work/tui_signal.json`) и звуковые оповещения (`AlertSound` по severity с флагом `--no-sound`).
8. Реализованы пресеты конфигурации (`full`, `basic`, `fast`), `builder_config.yaml`, флаги CLI и расширенная воронка метрик `PipelineMetrics` в отчете `ingest_report.md`.

---

## Phase 7: RUNPOD-H — Hybrid MKP Builder (RunPod + OpenRouter) (Запланировано)
**Goal:** Реализация гибридного конвейера RUNPOD-H (RunPod для parse+VLM, локальный ПК + OpenRouter API для всех текстовых LLM и критики), ускорение обработки книги в 2 раза (до 2–2.5 часов) при стоимости ~$1.30–$1.80 за книгу.  
**Mode:** standard / hybrid-builder  
**Duration:** 3–4 дня  
**Plan:** `.planning/phase-7/PLAN.md`  
**Spec:** `.init_doc/RUNPOD-H_Master Specification v1.0_1of2.md`, `.init_doc/RUNPOD-H_Master Specification v1.0_2of2.md`

**Requirements:** REQ-HYB-01, REQ-HYB-02, REQ-HYB-03, REQ-HYB-04, REQ-HYB-05, REQ-HYB-06, REQ-HYB-07, REQ-HYB-08

**Success Criteria:**
1. Httpx-клиент `OpenRouterClient` с повторными попытками, экспоненциальным backoff, RateLimiter (150/10s), CircuitBreaker (5 ошибок $\to$ OPEN).
2. `BalanceGuard` ($10 лимит) и `CostTracker` (лог `costs.jsonl` на основе `total_cost` от OpenRouter).
3. Асинхронный `BatchClient` (24h SLA) с обработкой частичных сбоев (Option A: 95 успехов, 5 в `batch_failures.jsonl`).
4. Персистентность батчей через `pending_batch.json` с возможностью выключения ПК и восстановления по hotkey `l` (`BatchesView`).
5. 12-этапный оркестратор `OpenRouterPhase` с пошаговыми чекпоинтами `state.json`.
6. Изолированный Rich TUI монитор с горячими клавишами (`q/b/s/r/l/d/i`) и звуковыми сигналами.
7. CLI команда `python -m mkp_builder.openrouter.cli run` и автоматический старт фазы в `pipeline.py`.
8. 100% покрытие unit-тестами с моками httpx (`tests/openrouter/`).
