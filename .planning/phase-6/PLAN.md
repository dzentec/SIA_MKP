# Phase 6: MKP-Builder Pipeline Upgrade, Dual-Stage Critic & Fallback Subsystem (v4.2) — Implementation Plan

**Phase:** Phase 6  
**Goal:** Кардинальное решение проблемы over-generation правил (сокращение с 800+ до 40–50 операционных правил на книгу) и обеспечение абсолютной отказоустойчивости в облачной/локальной среде (RunPod RTX 5090/4090 / Windows 11) согласно Fallback Spec v4.2:
1. Устранение 5 критических дефектов генерации правил и схем.
2. Подсистема последовательной загрузки моделей на single-GPU (`OllamaManager`, VRAM ≤ 30GB).
3. Двухступенчатый fail-open критик (`ClusterCritic` + `RuleCritic` на 32B).
4. Комплексная подсистема аварийного останова и защиты (`src/mkp_builder/fallback/`): HealthMonitor (CPU/GPU/VRAM offload), KillSwitch, VLMFailTracker (5 consecutive fails -> stop, 1-4 skip), PodStopper (RunPod API), RetryHelper (1 retry с коротким таймаутом), BatchCircuitBreaker (2 книги подряд -> stop), EventLogger (`work/fallback_events.jsonl`, `work/tui_signal.json`).
5. TUI-сигнализация и звуковые оповещения (`src/mkp_tui/watcher.py`, `sound.py`, `renderer.py`).
6. Пресеты конфигурации (`full`, `basic`, `fast`), флаги CLI и расширенная воронка метрик (`PipelineMetrics`).

**Sources of Truth:**  
- `.init_doc/MKP_Builder update.md` (v2)  
- `.init_doc/MKP_Builder update(critic_code).md` (v2)  
- `.init_doc/MKP_Builder update_Fallback Specification v4.2.md` (v4.2 Final)  
**Execution Environment:** Windows 11 / Linux RunPod (NVIDIA RTX 5090 32GB / RTX 4090 24GB), 100% offline-ready Ollama backend.

---

## 1. Requirements & Success Criteria Mapping

| Requirement ID | Description | Source | Success Criteria |
|---|---|---|---|
| **REQ-BLD-V2-01** | **5 Core Bug Patches:** `RULE-` prefix normalization, `Trigger.value` float/list type safety, Contradiction tracking in clustering, `mapped` flag filtering in Claims, strict allowed numbers (0.0/1.0 context). | `MKP_Builder update.md` §1 | Устранение двойных префиксов `RULE_RULE-`, сериализации триггеров и корректная фильтрация claims. |
| **REQ-BLD-V2-02** | **OllamaManager (Single-GPU Sequential Loading):** Управление VRAM бюджетом (≤32 GB), последовательная загрузка/выгрузка моделей (VLM 32B ➔ Extractor 32B ➔ Critic 32B). | `MKP_Builder update.md` §2, `critic_code.md` §0 | Никогда не превышать 30 GB VRAM, в памяти всегда ровно одна 32B модель, корректный warmup и fallback. |
| **REQ-BLD-V2-03** | **Critic Subsystem Core:** `CriticVerdict` (keep, reject, uncertain, fix), `BaseCritic` interface, устойчивый JSON-парсер с поддержкой reasoning preamble DeepSeek-R1, fail-open гарантия. | `critic_code.md` §1–3 | Никакая ошибка критика не роняет конвейер (fail-open ➔ `keep` / `uncertain`), извлечение JSON из блоков markdown. |
| **REQ-BLD-V2-04** | **Cluster Critic (Stage 5.2):** Рецензирование кластеров утверждений морским экспертным промптом до синтеза правил. | `critic_code.md` §4 | Сокращение кластеров: 895 ➔ ~50–100, отсев справочных цитат и конструкторских рекомендаций. |
| **REQ-BLD-V2-05** | **Rule Critic (Stage 5.4):** Рецензирование и исправление синтезированных правил (триггеры, действия, severity, домен, дубликаты). | `critic_code.md` §5 | Финальное число правил: 600+ ➔ **40–50 высококачественных операционных правил**. |
| **REQ-BLD-V2-06** | **Config, CLI Presets & Funnel Metrics:** Пресеты `full`, `basic`, `fast`, CLI флаги, воронка метрик `PipelineMetrics` и расширенный отчет `ingest_report.md`. | `MKP_Builder update.md` §2 | Поддержка `mkp-builder build --preset full|basic|fast`, фиксация latency переключения моделей и этапов. |
| **REQ-BLD-V2-07** | **Fallback & Health Monitoring Subsystem:** HealthMonitor (CPU >85%, GPU <50%, Offload >30s, VRAM >98%), KillSwitch (StopReason, StopEvent), EventLogger (`work/fallback_events.jsonl`), RetryHelper (1 retry). | `Fallback Spec v4.2` §1, 2, 6, 7 | Автоматическая фиксация деградации оборудования, повторные попытки с коротким таймаутом, жесткая остановка. |
| **REQ-BLD-V2-08** | **VLM Resilience & Batch Circuit Breaker:** VLMFailTracker (1–4 ошибки -> skip + log, 5 ошибок -> STOP), BatchCircuitBreaker (2 книги подряд упали -> STOP batch + Pod stop). | `Fallback Spec v4.2` §1, 5 | `work/vlm/vlm_failures.jsonl`, `work/vlm/vlm_summary.json`, защита от бесконечной траты ресурсов в RunPod. |
| **REQ-BLD-V2-09** | **PodStopper & Graceful Shutdown Orchestration:** PodStopper (RunPod REST API), ShutdownOrchestrator (сохранение частичного состояния, `work/tui_signal.json`, `pipeline_stopped.jsonl`). | `Fallback Spec v4.2` §3, 6, 7 | Корректная остановка пода с 30s grace period и полным сохранением контекста сбоя для аудита. |
| **REQ-BLD-V2-10** | **TUI Signal Watcher & Sound Alerts:** SignalWatcher (`watchdog` на `tui_signal.json`), AlertSound (`winsound`/terminal bell по severity) с флагом `--no-sound`, отрисовка отчета останова. | `Fallback Spec v4.2` §3, 4, 10 | Мгновенная звуковая и визуальная реакция TUI при останове пайплайна или деградации. |

---

## 2. Wave Architecture & Implementation Plan

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               Phase 6 Wave Architecture                          │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 1: Core Bug Patches & Schema Alignment (Task 1)                             │
│   ├── normalize_rule_id & synthesize.py patch (Bug 1 & 5)                        │
│   ├── rules_schema.py Trigger.value & Contradiction patch (Bug 2 & 3)            │
│   └── claims.py mapped flag filtering (Bug 4)                                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 2: OllamaManager & Configuration (Task 2 & 3)                               │
│   ├── src/mkp_builder/ollama_manager.py (Sequential VRAM Loader ≤ 30GB)           │
│   └── src/mkp_builder/config.py (Presets: full, basic, fast + KillSwitchConfig)   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 3: Critic Subsystem (Dual-Stage Fail-Open) (Task 4)                         │
│   ├── src/mkp_builder/critic/verdict.py & base.py                                │
│   ├── src/mkp_builder/critic/prompts.py (Captain persona 32B)                    │
│   ├── src/mkp_builder/critic/cluster_critic.py & rule_critic.py                  │
│   └── src/mkp_builder/critic/registry.py                                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 4: Fallback & Resilience Subsystem (Spec v4.2) (Task 5)                     │
│   ├── src/mkp_builder/fallback/health.py (HealthMonitor: CPU/GPU/VRAM/Offload)    │
│   ├── src/mkp_builder/fallback/killswitch.py (KillSwitch, StopReason, StopEvent)    │
│   ├── src/mkp_builder/fallback/vlm_tracker.py (VLMFailTracker)                   │
│   ├── src/mkp_builder/fallback/retry.py (call_with_retry: primary/retry timeout)  │
│   ├── src/mkp_builder/fallback/pod_stopper.py (RunPod REST API client)           │
│   ├── src/mkp_builder/fallback/shutdown.py (ShutdownOrchestrator)                │
│   ├── src/mkp_builder/fallback/logger.py (EventLogger)                           │
│   └── src/mkp_builder/fallback/batch.py (BatchCircuitBreaker)                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 5: TUI Signal Watcher & Sound Alerts (Task 6)                               │
│   ├── src/mkp_tui/watcher.py (watchdog on tui_signal.json)                       │
│   ├── src/mkp_tui/sound.py (AlertSound: warning, error, critical, success)       │
│   └── src/mkp_tui/renderer.py (Stopped state screen rendering)                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 6: Pipeline Integration & Metrics (Task 7)                                  │
│   ├── src/mkp_builder/metrics.py (Funnel Metrics)                                │
│   ├── src/mkp_builder/pipeline.py (Sequential 6-Phase Execution + KillSwitch)    │
│   └── src/mkp_builder/cli.py (CLI options: --preset, --critic, --no-sound, etc.) │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 7: Comprehensive Testing & Verification (Task 8)                            │
│   ├── tests/test_builder_v2_patches.py (Schema, prefix, threshold unit tests)    │
│   ├── tests/test_critic_subsystem.py (Critic verdict, JSON parser, fail-open)    │
│   ├── tests/test_ollama_manager.py (Mock VRAM & sequential loader)               │
│   ├── tests/test_fallback_v42.py (Health, KillSwitch, VLM tracker, CircuitBreaker)│
│   ├── tests/test_tui_sound_watcher.py (Signal watcher & sound alerts)            │
│   └── Regression verification (100% PASS on all test suites)                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

### Task 1: 5 Core Bug Patches (`REQ-BLD-V2-01`)
- **Files:**
  - `src/mkp_builder/synthesize/synthesize.py`
  - `src/mkp_common/rules_schema.py`
  - `src/mkp_builder/synthesize/cluster.py`
  - `src/mkp_builder/extract/claims.py`
- **Actions:**
  1. Реализовать `normalize_rule_id(raw_id: str) -> str` в `synthesize.py` (удаление повторов `RULE-RULE-`, перевод в `RULE-TOPIC-ID`).
  2. Разрешить в `RuleTrigger.value` безопасную валидацию типов `float | int | str | list[float] | list[str]`.
  3. Исправить сохранение и сериализацию `contradictions` в `cluster.py`.
  4. В `claims.py` реализовать строгую фильтрацию не сопоставленных утверждений (`mapped=True` для operational, сохранение цитат).
  5. В `validate_triggers_against_quotes` разрешить тривиальные базовые константы (0.0, 1.0) только в допустимых контекстах булевых флагов.

---

### Task 2: Single-GPU Sequential Model Manager (`REQ-BLD-V2-02`)
- **Files:**
  - `src/mkp_builder/ollama_manager.py` (новый)
- **Actions:**
  1. Реализовать `OllamaManager`:
     - `load_model(model_name: str, role: str, estimated_vram_gb: float)`
     - `unload_current()` (через `/api/generate` с `keep_alive: 0` или direct unload)
     - `vram_budget_check(target_gb: float)`
     - Трекинг латентности переключения моделей и сохранение в таймлайн.
  2. Обеспечить устойчивость к сетевым сбоям и таймаутам Ollama API.

---

### Task 3: Configuration, YAML Config & Presets (`REQ-BLD-V2-06`, `REQ-BLD-V2-07`)
- **Files:**
  - `src/mkp_builder/config.py` (новый)
  - `builder_config.yaml` (шаблон конфигурации по умолчанию)
- **Actions:**
  1. Создать типизированные Pydantic/dataclass модели:
     - `CriticConfig`: `enabled` (bool, default True), `model` ("deepseek-r1:32b" / "qwen2.5:32b"), `temperature` (0.1), `batch_size` (5), `estimated_vram_gb` (20.0), `strict_mode` (False), `confidence_threshold` (0.7).
     - `ModelConfig`: `vlm_model` ("qwen2.5vl:7b" / "qwen2.5-vl:32b"), `extractor_model` ("qwen2.5:7b" / "qwen2.5:32b"), `vram_budget_gb` (30.0), `num_predict` (3072), `num_ctx` (8192), `num_gpu` (999).
     - `TimeoutConfig`: `primary_sec`, `retry_sec`, `hard_limit_sec` для каждого этапа (vlm, claims, triplets, cluster_critic, synthesize, rule_critic).
     - `HealthThresholdsConfig`: `cpu_saturation_pct` (85%), `gpu_underutil_pct` (50%), `offload_persistent_sec` (30s), `vram_max_pct` (98%), `slow_call_sec` (60s), `slow_consecutive_limit` (3).
     - `KillSwitchConfig`: `vlm_max_consecutive_errors` (5), `model_max_consecutive_errors` (5), `vlm_failure_ratio_stop` (0.50), `batch_max_consecutive_errors` (2), `enabled` (True).
     - `RunPodConfig`: `enabled` (auto/bool), `pod_id` (str), `api_key` (str), `grace_period_sec` (30).
     - `SoundConfig`: `enabled` (bool), `frequencies` (dict).
     - `PipelineConfig`: полная конфигурация сборщика, объединяющая `ModelConfig`, `CriticConfig`, `KillSwitchConfig`, `RunPodConfig`, `SoundConfig`, `TimeoutConfig`.
  2. Реализовать загрузчик `load_builder_config(path: Path | None = None) -> PipelineConfig`:
     - Иерархия: Встроенные дефолты (v4.2) ➔ Файл `builder_config.yaml` (или указанный через `--config`) ➔ Переменные окружения (`ENV`) ➔ CLI аргументы (наивысший приоритет).
  3. Реализовать фабрики пресетов:
     - `preset_5090_full()`: VLM 32B + Extractor 32B + Critic 32B (critic enabled).
     - `preset_5090_basic()`: VLM 32B + Extractor 32B (critic disabled, baseline mode).
     - `preset_5090_fast()`: VLM 7B + Extractor 14B + Critic 14B.
  4. Поддержка параметров LLM: `num_predict=3072`, `num_ctx=8192`, `num_gpu=999`.

---

### Task 4: Critic Subsystem Implementation (`REQ-BLD-V2-03`, `REQ-BLD-V2-04`, `REQ-BLD-V2-05`)
- **Files:**
  - `src/mkp_builder/critic/__init__.py`
  - `src/mkp_builder/critic/verdict.py`
  - `src/mkp_builder/critic/base.py`
  - `src/mkp_builder/critic/prompts.py`
  - `src/mkp_builder/critic/cluster_critic.py`
  - `src/mkp_builder/critic/rule_critic.py`
  - `src/mkp_builder/critic/registry.py`
- **Actions:**
  1. `CriticVerdict`: модель вердикта (`keep`, `reject`, `uncertain`, `fix`), фабричные методы `fail_open()` и `uncertain_fallback()`.
  2. `BaseCritic`: абстрактный базовый класс с `review_cluster`, `review_rule`, `estimated_vram_gb`.
  3. `CLUSTER_CRITIC_PROMPT` и `RULE_CRITIC_PROMPT`: ролевые промпты морского капитана-эксперта с явными примерами операционных действий шкипера.
  4. `_extract_json()`: надежное извлечение JSON из блоков reasoning (`<think>...</think>`, markdown code blocks).
  5. `ClusterCritic`: пакетное рецензирование кластеров `review_clusters_batch()`.
  6. `RuleCritic`: пакетное рецензирование правил `review_rules_batch()` с применением `suggested_fix`.
  7. `CriticRegistry`: фабрика создания критиков по `CriticConfig`.

---

### Task 5: Fallback & Resilience Subsystem (`REQ-BLD-V2-07`, `REQ-BLD-V2-08`, `REQ-BLD-V2-09`)
- **Files:**
  - `src/mkp_builder/fallback/__init__.py`
  - `src/mkp_builder/fallback/health.py` (HealthMonitor: CPU, GPU util, VRAM%, persistent offload)
  - `src/mkp_builder/fallback/killswitch.py` (KillSwitch, StopReason enum, StopEvent)
  - `src/mkp_builder/fallback/vlm_tracker.py` (VLMFailTracker: 1–4 skip, 5 stop)
  - `src/mkp_builder/fallback/retry.py` (call_with_retry)
  - `src/mkp_builder/fallback/pod_stopper.py` (PodStopper: RunPod API stop, 30s grace)
  - `src/mkp_builder/fallback/shutdown.py` (ShutdownOrchestrator: dump partial state, tui_signal.json)
  - `src/mkp_builder/fallback/logger.py` (EventLogger: fallback_events.jsonl)
  - `src/mkp_builder/fallback/batch.py` (BatchCircuitBreaker: 2 consecutive failed books -> STOP batch)
- **Actions:**
  1. Реализация мониторинга ресурсов: `psutil` для CPU, `pynvml` / `nvidia-smi` / Ollama ps для GPU и VRAM.
  2. Реализация `StopReason` enum: `CPU_SATURATED`, `GPU_UNDERUTILIZED`, `OFFLOAD_PERSISTENT`, `VRAM_EXCEEDED`, `VLM_CONSECUTIVE_FAILURES`, `SLOW_CONSECUTIVE`, `MODEL_ERRORS`, `HARD_LIMIT_EXCEEDED`, `BATCH_STOPPED`.
  3. Реализация `VLMFailTracker`: логирование `work/vlm/vlm_failures.jsonl`, `work/vlm/vlm_summary.json`.
  4. Реализация `call_with_retry(fn, primary_timeout, retry_timeout, hard_limit)`.
  5. Реализация `PodStopper` с интеграцией REST API RunPod (`POST https://api.runpod.io/graphql` или REST endpoint) с grace period 30 сек.
  6. Реализация `ShutdownOrchestrator`: запись `work/tui_signal.json` и `work/pipeline_stopped.jsonl`.

---

### Task 6: TUI Signal Watcher & Sound Alerts (`REQ-BLD-V2-10`)
- **Files:**
  - `src/mkp_tui/watcher.py` (SignalWatcher на базе `watchdog`)
  - `src/mkp_tui/sound.py` (AlertSound: warning 700Hz, error 1000Hz, critical 1500Hz, success 800->1000Hz)
  - `src/mkp_tui/renderer.py` (TUI stopped screen)
- **Actions:**
  1. `SignalWatcher`: мониторинг изменений `work/tui_signal.json`.
  2. `AlertSound`: воспроизведение звуков через `winsound.Beep` на Windows и ANSI terminal bell / aplay на Linux. Поддержка флага `--no-sound`.
  3. `renderer.py`: красивый терминальный рендеринг аварийного останова с таблицей провалов VLM и частичного состояния.

---

### Task 7: Pipeline Integration & Funnel Metrics (`REQ-BLD-V2-06`)
- **Files:**
  - `src/mkp_builder/metrics.py` (новый)
  - `src/mkp_builder/pipeline.py`
  - `src/mkp_builder/cli.py`
- **Actions:**
  1. `PipelineMetrics`: сбор статистики воронки (Chunks ➔ Claims ➔ Actionable Claims ➔ Clusters ➔ After Cluster Critic ➔ Rules Synthesized ➔ After Rule Critic ➔ Rules Final), тайминги фаз и переключения моделей.
  2. Интеграция 6-фазного конвейера с KillSwitch в `BookpackPipeline`:
     - Фаза 1: VLM 32B (парсинг/схемы) с `VLMFailTracker` ➔ Unload VLM
     - Фаза 2: Extractor 32B (Claims & Triplets) ➔ Unload Extractor
     - Фаза 3: Critic 32B (Cluster review) ➔ Unload Critic (если включен)
     - Фаза 4: Extractor 32B (Rule synthesis) ➔ Unload Extractor
     - Фаза 5: Critic 32B (Rule review) ➔ Unload Critic (если включен)
     - Фаза 6: CPU (Export, Guardrails, Checksums, Ed25519 signature)
  3. Генерация расширенного `ingest_report.md` с таблицей воронки, таймингами и разделом «Failed figures».
  4. Обновление CLI `mkp-builder build` и `mkp-builder batch`: `--preset`, `--critic/--no-critic`, `--no-sound`, `--runpod-pod-id`, `--runpod-api-key`.

---

### Task 8: Testing, Quality Gates & Regression Verification
- **Files:**
  - `tests/test_builder_v2_patches.py`
  - `tests/test_critic_subsystem.py`
  - `tests/test_ollama_manager.py`
  - `tests/test_fallback_v42.py`
  - `tests/test_tui_sound_watcher.py`
- **Actions:**
  1. Тесты нормализации `RULE-` идентификаторов, порогов и типов триггеров.
  2. Тесты извлечения JSON из ответов DeepSeek-R1 с рассуждениями.
  3. Тесты fail-open поведения критика при сетевой ошибке или падении сервиса.
  4. Тесты триггеров KillSwitch: симуляция CPU 90%, GPU 30%, VRAM 99%, VLM 5 провалов подряд, Batch 2 провала.
  5. Тесты `VLMFailTracker`: 1–4 пропускаются, 5-й вызывает останов.
  6. Тесты звуковых сигналов и `tui_signal.json` watcher.
  7. Прогон всего набора `pytest tests/` (75+ тестов) с гарантией 100% PASS.

---

## 3. Success Criteria & Quality Gates

| Метрика / Проверка | Базовый режим (Basic) | Режим критика (Critic) + Fallback v4.2 | Критерий |
|---|---|---|---|
| **Количество правил (Rules)** | ~500–600 | **40–50 правил** | ✅ Очистка от овергенерации |
| **Количество кластеров** | ~100 | **~40–50 кластеров** | ✅ Агрегация тем |
| **Пиковое потребление VRAM** | < 24 GB | **< 28 GB** (RTX 5090 32GB) | ✅ 1 модель в памяти |
| **Fail-Open надежность** | 100% | **100%** (0 падений при сбое LLM) | ✅ Непрерывность |
| **VLM устойчивость** | Падение при сбое | **1–4 пропускаются, 5 → STOP** | ✅ Нет зависания |
| **Защита ресурсов RunPod** | Бесконечный цикл | **Автоматический POD stop при сбое** | ✅ Экономия бюджета |
| **TUI оповещения** | Без звука/сигналов | **Звуковые оповещения + tui_signal.json** | ✅ Мгновенный фидбек |
| **Automated Tests** | 100% PASS | **100% PASS** (все unit-тесты) | ✅ Зеленый CI |
