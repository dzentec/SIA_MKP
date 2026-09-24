# Phase 7: RUNPOD-H — Hybrid MKP Builder (RunPod + OpenRouter) & 3-Stage Image Filtering — Implementation Plan

**Phase:** Phase 7  
**Goal:** Реализация гибридного конвейера **RUNPOD-H** (RunPod для PDF parsing + OCR; локальный ПК + OpenRouter API для VLM 7B/32B, всех текстовых LLM и критики):
- Сокращение времени сборки книги с 4.5–5 часов до **2–2.5 часов**.
- Снижение стоимости до **~$1.30–$1.80 за книгу** (GPU + API, из них VLM filtering + annotation $\le \$0.07$).
- 3-ступенчатая фильтрация изображений через OpenRouter API: FILTER 1 (Rule-based CPU $\to$ ~85) $\to$ FILTER 2 (Qwen VL 7B via OpenRouter $\to$ ~50) $\to$ FILTER 3 (Qwen VL 32B annotate via OpenRouter).
- 12-этапный отказоустойчивый конвейер (`tools/openrouter/phase.py`).
- Асинхронный OpenRouter Batch API (24h SLA, персистентность `pending_batch.json` при выключении ПК, обработка частичных сбоев Option A: use completed, log failed).
- Балансовый страж (`BalanceGuard`), токен-бакет `RateLimiter` (150 req/10s), предохранитель `CircuitBreaker` (5 failures -> OPEN).
- Изолированный Rich TUI монитор с горячими клавишами (`tools/openrouter/tui/`).

**Sources of Truth:**  
- `.init_doc/RUNPOD-H_Master Specification v1.0_1of2.md`  
- `.init_doc/RUNPOD-H_Master Specification v1.0_2of2.md`  
- `.init_doc/Image Filtering for RUNPOD-H.md` (v1.0 Final)  
**Execution Environment:** Windows 11 (оркестрация, OpenRouter API, TUI, сборка, Ed25519 подпись) + Linux RunPod (RTX 5090 32GB, parse + OCR).

---

## 1. Scope & Boundaries (Что НЕ трогать / Что создаётся)

### 1.1. Существующие компоненты Clean RUNPOD (НЕ ТРОГАТЬ):
- `mkp_builder/extract/docling_parser.py`, OCR (EasyOCR), Image extraction (Docling).
- Утилиты передачи файлов (PDF $\to$ RunPod, Images/Chunks $\to$ ПК), ZST компрессия, dedup.
- Мониторинг RunPod и существующий RunPod TUI (`tools/runpod/`).
- Fallback v4.2 компоненты для RunPod (`KillSwitch`, `HealthMonitor`, `PodStopper`, `ShutdownOrchestrator`).
- Локальная Ed25519 подпись и упаковщик bookpack v0.3.0.

### 1.2. Новые модули RUNPOD-H (отдельный инструмент в каталоге `tools/openrouter/`):
| # | Компонент | Путь к файлу | Назначение |
|---|---|---|---|
| 1 | OpenRouter Client | `tools/openrouter/client.py` | Httpx клиент с экспоненциальным backoff, обработкой 429 (Retry-After), 402/401 (STOP). |
| 2 | Rate Limiter | `tools/openrouter/rate_limiter.py` | Token Bucket (150 req / 10s, 15 RPS sustained). |
| 3 | Circuit Breaker | `tools/openrouter/circuit_breaker.py` | 5 ошибок подряд $\to$ OPEN, 300s cooldown, HALF_OPEN recovery. |
| 4 | Balance Guard | `tools/openrouter/balance_guard.py` | Проверка `/credits` каждые 5 мин. Останов при балансе < $10 или < стоимости книги. |
| 5 | Cost Tracker | `tools/openrouter/cost_tracker.py` | Повызовный лог в `work/openrouter/costs.jsonl` на основе `total_cost` от OpenRouter. |
| 6 | Batch Client | `tools/openrouter/batch_client.py` | Загрузка файлов `/files`, запуск `/batches`, поллинг, скачивание результатов. |
| 7 | Checkpoint Manager | `tools/openrouter/checkpoint.py` | Сохранение состояния этапов и `pending_batch.json` (безопасное выключение ПК). |
| 8 | OpenRouter VLM Backend | `tools/openrouter/filters/openrouter_backend.py` | Адаптер кодирования base64 изображений, rate limiting и cost tracking. |
| 9 | Rule-based Filter | `tools/openrouter/filters/image_filter.py` | FILTER 1 (CPU): edge density/concentration, аспект, размер, OCR digits, dedup. |
| 10 | VLM Filter 7B | `tools/openrouter/filters/vlm_filter.py` | FILTER 2: быстрая классификация через Qwen VL 7B (OpenRouter API), strict fail-open. |
| 11 | VLM Annotator 32B | `tools/openrouter/filters/vlm_annotator.py` | FILTER 3: полная аннотация отобранных ~50 картинок через Qwen VL 32B (OpenRouter). |
| 12 | Phase Pipeline | `tools/openrouter/phase.py` | 12-этапный оркестратор OpenRouter-фазы с resume. |
| 13 | Config & CLI | `tools/openrouter/config.py`, `cli.py` | Конфигурация и точка входа `python -m tools.openrouter.cli run`. |
| 14 | TUI Monitor | `tools/openrouter/tui/monitor.py` | Rich дашборд (прогресс 12 этапов, затраты в реальном времени, здоровье, лог). |
| 15 | Batches View | `tools/openrouter/tui/batches_view.py` | Экран истории батчей (активные, завершенные, упавшие) по hotkey `l`. |
| 16 | TUI App & Sound | `tools/openrouter/tui/app.py` | Главный цикл TUI с поддержкой горячих клавиш (`q`, `b`, `s`, `r`, `l`, `d`, `i`) и звуков. |

---

## 2. Requirements & Success Criteria Mapping

| Requirement ID | Description | Source | Success Criteria |
|---|---|---|---|
| **REQ-HYB-01** | **OpenRouter API Client & Infrastructure:** httpx-клиент с retry, экспоненциальным backoff, обработкой 429/402/401, RateLimiter (150/10s), CircuitBreaker (5 failures -> OPEN). | Master Spec §6.1–6.3 | Устойчивость к перегрузкам API, 0 необработанных исключений при сетевых сбоях. |
| **REQ-HYB-02** | **Balance Guard & Cost Tracking:** Проверка остатка кредитов перед книгой (<$10 -> STOP), трекинг каждого вызова в `costs.jsonl` с использованием `total_cost`. | Master Spec §6.4–6.5 | Стоимость книги ≤ $1.80, моментальный останов при нехватке средств без потери данных. |
| **REQ-HYB-03** | **OpenRouter Batch API Subsystem:** Асинхронная отправка кластеров и правил на DeepSeek R1 (`deepseek/deepseek-r1-0528`), поллинг (24h SLA), скачивание и парсинг результатов. | Master Spec §6.7, §8 | Успешная отправка батча, обработка частичных сбоев (Option A: use 95, log 5 в `batch_failures.jsonl`). |
| **REQ-HYB-04** | **PC Shutdown Persistence & Batch Recovery:** Сохранение `pending_batch.json`, возможность выключения ПК во время батча, возобновление поллинга при рестарте, ручное скачивание через UI. | Master Spec §8.1, §8.3 | ПК можно выключить сразу после отправки батча, при следующем запуске статус подхватывается. |
| **REQ-HYB-05** | **12-Stage Hybrid Phase Pipeline:** Filter2 (Qwen VL 7B) ➔ VLM 32B ➔ Claims (Qwen 72B) ➔ Triplets (Qwen 72B) ➔ Clustering ➔ Cluster Critic (R1 Batch) ➔ Synthesize (Qwen 72B) ➔ Rule Critic (R1 Batch) ➔ Validation ➔ Guardrails ➔ Assemble ➔ Sign. | Master Spec §7 | Сквозное выполнение 12 этапов с поддержкой постродийного чекпоинта `checkpoints/{book_id}_state.json`. |
| **REQ-HYB-06** | **Rich TUI OpenRouter Monitor:** Изолированный терминальный интерфейс с таблицей этапов, живыми затратами, счетчиком rate limiter, circuit breaker, экраном `BatchesView` (hotkey `l`). | Master Spec §9 | Информативный UI, горячие клавиши `q/b/s/r/l/d/i`, звуковые сигналы тревоги и успеха. |
| **REQ-HYB-07** | **Config, CLI & Pipeline Auto-Start:** CLI команда `python -m tools.openrouter.cli run`, патч `pipeline.py` для бесшовного перехода RunPod $\to$ OpenRouter, sequential multi-book. | Master Spec §10 | Автоматический старт OpenRouter-фазы после выгрузки с RunPod, останов батча при 2 ошибках подряд. |
| **REQ-HYB-08** | **Full Unit & Mock Integration Test Suite:** Покрытие тестами всех компонентов OpenRouter (client, rate limiter, circuit breaker, balance guard, batch client, checkpoint, partial failure). | Master Spec §12 | 100% PASS на всех юнит-тестах с использованием моков httpx. |
| **REQ-HYB-09** | **3-Stage Image Filtering Subsystem (OpenRouter):** FILTER 1 (Rule-based CPU $\to$ ~85) $\to$ FILTER 2 (`qwen/qwen-2.5-vl-7b-instruct` via OpenRouter $\to$ ~50) $\to$ FILTER 3 (`qwen/qwen-2.5-vl-32b-instruct` annotate via OpenRouter). Fail-open, базовая стоимость VLM $\le \$0.07$. | Image Filtering Spec v1.0 §1–5 | Отсев 78% мусорных картинок, сохранение ЧБ схем такелажа, логирование `image_filter_rejects.jsonl`. |

---

## 3. Wave Architecture & Implementation Sprints

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Phase 7 Wave Architecture                              │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 1: Core API & Protection Layer (Task 1 & 2)                                 │
│   ├── tools/openrouter/client.py (OpenRouterClient, retry, 429/402)              │
│   ├── tools/openrouter/rate_limiter.py (TokenBucket 150/10s)                     │
│   ├── tools/openrouter/circuit_breaker.py (5 fails -> OPEN)                      │
│   └── tools/openrouter/balance_guard.py (Balance < $10 -> STOP)                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 2: Persistence, Cost Tracking & Checkpointing (Task 3)                      │
│   ├── tools/openrouter/cost_tracker.py (costs.jsonl from total_cost)             │
│   └── tools/openrouter/checkpoint.py (state.json + pending_batch.json)           │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 3: OpenRouter VLM & Image Filtering Subsystem (Task 4)                      │
│   ├── tools/openrouter/filters/openrouter_backend.py (base64 encoder/adapter)     │
│   ├── tools/openrouter/filters/image_filter.py (RuleBasedImageFilter: CPU)       │
│   ├── tools/openrouter/filters/vlm_filter.py (Qwen VL 7B via OpenRouter)         │
│   └── tools/openrouter/filters/vlm_annotator.py (Qwen VL 32B via OpenRouter)     │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 4: OpenRouter Batch API Subsystem (Task 5)                                  │
│   ├── tools/openrouter/batch_client.py (File upload, submit, poll)               │
│   └── Partial failure processor (Option A: 95 success + 5 batch_failures.jsonl)  │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 5: 12-Stage Phase Pipeline Orchestrator (Task 6)                            │
│   ├── tools/openrouter/phase.py (Orchestrator + 12 stage handlers)                │
│   ├── Stage 1-2: Filter 2 (VL 7B) & VLM Annotate (VL 32B)                        │
│   ├── Stage 3-5: Claims, Triplets, Clustering                                    │
│   ├── Stage 6-8: Cluster Critic (Batch), Synthesize, Rule Critic (Batch)         │
│   └── Stage 9-12: Validation, Guardrails, Assemble, Sign                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 6: Isolated Rich TUI & CLI (Task 7 & 8)                                     │
│   ├── tools/openrouter/tui/monitor.py (Rich layout & live rendering)             │
│   ├── tools/openrouter/tui/batches_view.py (Batch history modal)                 │
│   ├── tools/openrouter/tui/app.py (Hotkeys q/b/s/r/l/d + AlertSound)             │
│   └── tools/openrouter/config.py & cli.py                                        │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 7: Pipeline Integration & Auto-Start (Task 9)                               │
│   ├── Integration hook in tools/runpod/runpod_orchestrator.py                    │
│   └── Sequential multi-book BatchCircuitBreaker (2 failures -> STOP)             │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 8: Comprehensive Testing & Verification (Task 10)                           │
│   ├── tests/openrouter/test_client.py, test_rate_limiter.py                      │
│   ├── tests/openrouter/test_circuit_breaker.py, test_balance_guard.py           │
│   ├── tests/openrouter/test_vlm_filters.py, test_cost_tracker.py                 │
│   ├── tests/openrouter/test_batch_client.py, test_checkpoint.py                  │
│   └── tests/openrouter/test_phase_e2e.py (100% PASS with mock API)               │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tasks & Implementation Steps

### Task 1: OpenRouter Client & Protection Layer (`REQ-HYB-01`)
- **Files:**
  - `tools/openrouter/__init__.py`
  - `tools/openrouter/client.py`
  - `tools/openrouter/rate_limiter.py`
  - `tools/openrouter/circuit_breaker.py`
- **Actions:**
  1. Реализовать `OpenRouterClient` на `httpx.Client`:
     - Base URL: `https://openrouter.ai/api/v1`
     - Headers: `Authorization: Bearer <key>`, `HTTP-Referer`, `X-Title`.
     - Retry: экспоненциальный backoff для 5xx и таймаутов, чтение `Retry-After` для 429, моментальный останов при 402 (Balance) и 401 (Auth).
     - Парсинг ответа: извлечение `content`, токенов и `total_cost`.
  2. Реализовать `RateLimiter`: Token bucket (150 req / 10s, 15 RPS sustained).
  3. Реализовать `OpenRouterCircuitBreaker`: 5 ошибок $\to$ OPEN, 300s cooldown, HALF_OPEN recovery.

---

### Task 2: Balance Guard & Budget Protection (`REQ-HYB-02`)
- **Files:**
  - `tools/openrouter/balance_guard.py`
- **Actions:**
  1. Реализовать `BalanceGuard`:
     - Запрос баланса через `GET https://openrouter.ai/api/v1/credits` с кэшированием на 300 сек.
     - `ensure_sufficient()`: проверка `credits_remaining >= min_balance_usd` ($10.0 по умолчанию).
     - `ensure_can_process_book()`: проверка `credits_remaining >= estimated_cost_per_book` ($2.0 по умолчанию).

---

### Task 3: Cost Tracker & Checkpoint Management (`REQ-HYB-02`, `REQ-HYB-04`)
- **Files:**
  - `tools/openrouter/cost_tracker.py`
  - `tools/openrouter/checkpoint.py`
- **Actions:**
  1. Реализовать `CostTracker`:
     - Thread-safe лог в `work/openrouter/{book_id}/costs.jsonl`.
     - Накопление суммарных затрат, токенов ввода/вывода, времени выполнения.
     - Сохранение `summary_{book_id}.json`.
  2. Реализовать `CheckpointManager`:
     - Сохранение статуса 12 этапов в `checkpoints/{book_id}_state.json`.
     - Возобновление `first_incomplete_stage()`.
     - Персистентность батча в `checkpoints/{book_id}_pending_batch.json`.

---

### Task 4: OpenRouter VLM & Image Filtering Subsystem (`REQ-HYB-09`)
- **Files:**
  - `tools/openrouter/filters/__init__.py`
  - `tools/openrouter/filters/openrouter_backend.py`
  - `tools/openrouter/filters/image_filter.py`
  - `tools/openrouter/filters/vlm_filter.py`
  - `tools/openrouter/filters/vlm_annotator.py`
- **Actions:**
  1. `OpenRouterBackend`: кодирование base64, интеграция с `RateLimiter` и `CostTracker`.
  2. `RuleBasedImageFilter` (FILTER 1 CPU): размер $\ge 10$ KB, габариты $\ge 150$ px, аспект $\le 4.0$, однородность $\le 0.85$, `edge_density >= 0.02`, `edge_concentration <= 0.5`, perceptual hash dedup, OCR check (226 $\to$ ~85 картинок).
  3. `VLMImageFilter` (FILTER 2 OpenRouter): `qwen/qwen-2.5-vl-7b-instruct`, классификация diagram/rigging/photo/cover/map, `extract_worthy: bool`, strict **fail-open** (~85 $\to$ ~50 картинок).
  4. `VLMAnnotator` (FILTER 3 OpenRouter): аннотация ~50 картинок через `qwen/qwen-2.5-vl-32b-instruct`.
  5. Логирование отсева в `work/openrouter/{book_id}/image_filter_rejects.jsonl`.

---

### Task 5: OpenRouter Batch Client & Partial Failure Handling (`REQ-HYB-03`, `REQ-HYB-04`)
- **Files:**
  - `tools/openrouter/batch_client.py`
- **Actions:**
  1. `BatchClient`: загрузка файлов `POST /files`, создание батча `POST /batches` (24h SLA), поллинг, скачивание результатов.
  2. Обработка частичных сбоев (Option A): извлечение успешных ответов и логирование сбойных в `batch_failures.jsonl`.

---

### Task 6: 12-Stage Phase Pipeline Orchestrator (`REQ-HYB-05`, `REQ-HYB-09`)
- **Files:**
  - `tools/openrouter/phase.py`
- **Actions:**
  1. `OpenRouterPhase` со словарем моделей:
     - `filter2`: `qwen/qwen-2.5-vl-7b-instruct`
     - `vlm_annotate`: `qwen/qwen-2.5-vl-32b-instruct`
     - `claims`, `triplets`, `synthesize`: `qwen/qwen-2.5-72b-instruct`
     - `cluster_critic`, `rule_critic`: `deepseek/deepseek-r1-0528` (fallback: `deepseek/deepseek-r1`)
  2. 12 этапов:
     - Stage 1: `_stage_filter2` (VLM 7B)
     - Stage 2: `_stage_vlm_annotate` (VLM 32B)
     - Stage 3: `_stage_claims` (Qwen 72B)
     - Stage 4: `_stage_triplets` (Qwen 72B)
     - Stage 5: `_stage_clustering` (локально)
     - Stage 6: `_stage_cluster_critic` (DeepSeek R1 Batch)
     - Stage 7: `_stage_synthesize` (Qwen 72B)
     - Stage 8: `_stage_rule_critic` (DeepSeek R1 Batch)
     - Stage 9: `_stage_validation` (локально)
     - Stage 10: `_stage_guardrails` (локально)
     - Stage 11: `_stage_assemble` (локально)
     - Stage 12: `_stage_sign` (локально Ed25519)

---

### Task 7: Rich TUI Monitor & Batches View (`REQ-HYB-06`)
- **Files:**
  - `tools/openrouter/tui/__init__.py`
  - `tools/openrouter/tui/monitor.py`
  - `tools/openrouter/tui/batches_view.py`
  - `tools/openrouter/tui/app.py`
- **Actions:**
  1. `OpenRouterMonitor`: дашборд 12 этапов, живые затраты, счетчик rate limiter, circuit breaker, live log.
  2. `BatchesView`: таблица истории батчей за 30 дней.
  3. `OpenRouterApp`: горячие клавиши (`q`, `b`, `s`, `r`, `l`, `d`, `i`) и звуковые сигналы `winsound`.

---

### Task 8: Config, CLI & Pipeline Auto-Start (`REQ-HYB-07`)
- **Files:**
  - `tools/openrouter/config.py`
  - `tools/openrouter/cli.py`
  - `tools/runpod/runpod_orchestrator.py`
- **Actions:**
  1. `OpenRouterConfig`: модель конфигурации с поддержкой `OPENROUTER_API_KEY`.
  2. CLI Typer `python -m tools.openrouter.cli run`: параметры `--work-dir`, `--book-id`, `--resume`, `--min-balance`.
  3. Автоматический старт `OpenRouterPhase` после выгрузки с RunPod при наличии ключа API.

---

### Task 9: Comprehensive Testing & Verification (`REQ-HYB-08`)
- **Files:**
  - `tests/openrouter/test_client.py`
  - `tests/openrouter/test_rate_limiter.py`
  - `tests/openrouter/test_circuit_breaker.py`
  - `tests/openrouter/test_balance_guard.py`
  - `tests/openrouter/test_vlm_filters.py`
  - `tests/openrouter/test_cost_tracker.py`
  - `tests/openrouter/test_batch_client.py`
  - `tests/openrouter/test_checkpoint.py`
  - `tests/openrouter/test_partial_failure.py`
  - `tests/openrouter/test_phase_e2e.py`
- **Actions:**
  1. Юнит-тесты с моками `httpx`:
     - 429 retry, 402 STOP, RateLimiter blocking, CircuitBreaker OPEN/HALF_OPEN.
     - VLM фильтрация (diagram keep, photo reject, fail-open).
     - Batch submit/poll/download, персистентность `pending_batch.json`, partial failure 95/5.
     - Сквозной E2E прогон 12 этапов.
  2. Запуск `pytest tests/openrouter/` (100% PASS).

---

## 5. Success Criteria & Verification Gates

| Метрика / Проверка | Чистый RunPod | Гибридный RUNPOD-H | Критерий успеха |
|---|---|---|---|
| **E2E время обработки книги** | 4.5–5 часов | **2–2.5 часа** | ⚡ Ускорение в 2 раза |
| **Стоимость на 1 книгу** | ~$2.00 (GPU) | **~$1.30–$1.80** (GPU + API) | 💰 Экономия бюджета |
| **Затраты на VLM фильтр+аннотацию** | — | **≤ $0.07** за книгу | 📉 Минимальная стоимость API |
| **Параллелизм LLM/VLM** | Последовательно (1 GPU) | **Параллельно** (OpenRouter) | 🚀 Высокая пропускная способность |
| **Batch Persistence** | Нет | **Да** (`pending_batch.json`) | 🔒 ПК можно выключать |
| **Partial Failure Handling** | Падение | **Option A: use 95, log 5** | 🛡️ Устойчивость к сбоям |
| **Защита баланса** | Нет | **Останов при < $10** | 🛑 Защита от перерасхода |
| **Unit Tests Coverage** | — | **100% PASS** (`tests/openrouter/`) | ✅ Зеленый тестовый стенд |
