# Phase 7: RUNPOD-H — Hybrid MKP Builder (RunPod + OpenRouter) — Implementation Plan

**Phase:** Phase 7  
**Goal:** Реализация гибридного конвейера **RUNPOD-H** (RunPod для PDF parsing + OCR + VLM annotation; локальный ПК + OpenRouter API для всех текстовых LLM и критики):
- Сокращение времени сборки книги с 4.5–5 часов до **2–2.5 часов**.
- Снижение стоимости до **~$1.30–$1.80 за книгу** (GPU + API).
- 12-этапный отказоустойчивый конвейер (`openrouter/phase.py`).
- Асинхронный OpenRouter Batch API (24h SLA, персистентность `pending_batch.json` при выключении ПК, обработка частичных сбоев Option A: use completed, log failed).
- Балансовый страж (`BalanceGuard`), токен-бакет `RateLimiter`, предохранитель `CircuitBreaker` (5 failures -> OPEN).
- Изолированный Rich TUI монитор с горячими клавишами (`mkp_tui_openrouter/`).

**Sources of Truth:**  
- `.init_doc/RUNPOD-H_Master Specification v1.0_1of2.md`  
- `.init_doc/RUNPOD-H_Master Specification v1.0_2of2.md`  
**Execution Environment:** Windows 11 (оркестрация, OpenRouter API, TUI, сборка, Ed25519 подпись) + Linux RunPod (RTX 5090 32GB, parse + VLM).

---

## 1. Scope & Boundaries (Что НЕ трогать / Что создаётся)

### 1.1. Существующие компоненты Clean RUNPOD (НЕ ТРОГАТЬ):
- `mkp_builder/extract/docling_parser.py`, OCR (EasyOCR), Image extraction (Docling), Rule-based filter.
- RunPod VLM annotate (`qwen2.5-vl:32b` на GPU).
- Утилиты передачи файлов (PDF $\to$ RunPod, Images/Chunks $\to$ ПК), ZST компрессия, dedup.
- Мониторинг RunPod и существующий RunPod TUI.
- Fallback v4.2 компоненты для RunPod (`KillSwitch`, `HealthMonitor`, `PodStopper`, `ShutdownOrchestrator`).
- Локальная Ed25519 подпись и упаковщик bookpack v0.3.0.

### 1.2. Новые модули RUNPOD-H (отдельный инструмент в каталоге `tools/`):
| # | Компонент | Путь к файлу | Назначение |
|---|---|---|---|
| 1 | OpenRouter Client | `tools/openrouter/client.py` | Httpx клиент с экспоненциальным backoff, обработкой 429 (Retry-After), 402/401 (STOP). |
| 2 | Rate Limiter | `tools/openrouter/rate_limiter.py` | Token Bucket (150 req / 10s, 15 RPS sustained). |
| 3 | Circuit Breaker | `tools/openrouter/circuit_breaker.py` | 5 ошибок подряд $\to$ OPEN, 300s cooldown, HALF_OPEN recovery. |
| 4 | Balance Guard | `tools/openrouter/balance_guard.py` | Проверка `/credits` каждые 5 мин. Останов при балансе < $10 или < стоимости книги. |
| 5 | Cost Tracker | `tools/openrouter/cost_tracker.py` | Повызовный лог в `work/openrouter/costs.jsonl` на основе `total_cost` от OpenRouter. |
| 6 | Batch Client | `tools/openrouter/batch_client.py` | Загрузка файлов `/files`, запуск `/batches`, поллинг, скачивание результатов. |
| 7 | Checkpoint Manager | `tools/openrouter/checkpoint.py` | Сохранение состояния этапов и `pending_batch.json` (безопасное выключение ПК). |
| 8 | Phase Pipeline | `tools/openrouter/phase.py` | 12-этапный оркестратор OpenRouter-фазы с resume. |
| 9 | Config & CLI | `tools/openrouter/config.py`, `cli.py` | Конфигурация и точка входа `python -m tools.openrouter.cli run`. |
| 10 | TUI Monitor | `tools/openrouter/tui/monitor.py` | Rich дашборд (прогресс 12 этапов, затраты в реальном времени, здоровье, лог). |
| 11 | Batches View | `tools/openrouter/tui/batches_view.py` | Экран истории батчей (активные, завершенные, упавшие) по hotkey `l`. |
| 12 | TUI App & Sound | `tools/openrouter/tui/app.py` | Главный цикл TUI с поддержкой горячих клавиш (`q`, `b`, `s`, `r`, `l`, `d`, `i`) и звуков. |

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
| **REQ-HYB-07** | **Config, CLI & Pipeline Auto-Start:** CLI команда `python -m mkp_builder.openrouter.cli run`, патч `pipeline.py` для бесшовного перехода RunPod $\to$ OpenRouter, sequential multi-book. | Master Spec §10 | Автоматический старт OpenRouter-фазы после выгрузки с RunPod, останов батча при 2 ошибках подряд. |
| **REQ-HYB-08** | **Full Unit & Mock Integration Test Suite:** Покрытие тестами всех компонентов OpenRouter (client, rate limiter, circuit breaker, balance guard, batch client, checkpoint, partial failure). | Master Spec §12 | 100% PASS на всех юнит-тестах с использованием моков httpx. |

---

## 3. Wave Architecture & Implementation Sprints

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Phase 7 Wave Architecture                              │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 1: Core API & Protection Layer (Task 1 & 2)                                 │
│   ├── src/mkp_builder/openrouter/client.py (OpenRouterClient, retry, 429/402)    │
│   ├── src/mkp_builder/openrouter/rate_limiter.py (TokenBucket 150/10s)           │
│   ├── src/mkp_builder/openrouter/circuit_breaker.py (5 fails -> OPEN)            │
│   └── src/mkp_builder/openrouter/balance_guard.py (Balance < $10 -> STOP)        │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 2: Persistence, Cost Tracking & Checkpointing (Task 3)                      │
│   ├── src/mkp_builder/openrouter/cost_tracker.py (costs.jsonl from total_cost)   │
│   └── src/mkp_builder/openrouter/checkpoint.py (state.json + pending_batch.json)│
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 3: OpenRouter Batch API Subsystem (Task 4)                                  │
│   ├── src/mkp_builder/openrouter/batch_client.py (File upload, submit, poll)    │
│   └── Partial failure processor (Option A: 95 success + 5 batch_failures.jsonl)  │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 4: 12-Stage Phase Pipeline Orchestrator (Task 5)                            │
│   ├── src/mkp_builder/openrouter/phase.py (Orchestrator + 12 stage handlers)     │
│   ├── Filter2 (Qwen VL 7B), VLM 32B, Claims/Triplets/Synthesize (Qwen 72B)      │
│   └── Cluster Critic & Rule Critic (DeepSeek R1 via Batch API)                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 5: Isolated Rich TUI & CLI (Task 6 & 7)                                     │
│   ├── src/mkp_tui_openrouter/monitor.py (Rich layout & live rendering)           │
│   ├── src/mkp_tui_openrouter/batches_view.py (Batch history modal)               │
│   ├── src/mkp_tui_openrouter/app.py (Hotkeys q/b/s/r/l/d + AlertSound)          │
│   └── src/mkp_builder/openrouter/config.py & cli.py                             │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 6: Pipeline Integration & Auto-Start (Task 8)                               │
│   ├── Pipeline integration in src/mkp_builder/pipeline.py                        │
│   └── Sequential multi-book BatchCircuitBreaker (2 failures -> STOP)             │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Wave 7: Comprehensive Testing & Verification (Task 9)                            │
│   ├── tests/openrouter/test_client.py, test_rate_limiter.py                      │
│   ├── tests/openrouter/test_circuit_breaker.py, test_balance_guard.py           │
│   ├── tests/openrouter/test_cost_tracker.py, test_batch_client.py                │
│   ├── tests/openrouter/test_checkpoint.py, test_partial_failure.py              │
│   └── tests/openrouter/test_phase_e2e.py                                         │
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
  2. Реализовать `RateLimiter`:
     - Token bucket с вместимостью 150 токенов и пополнением 15 токенов/сек (15 RPS sustained, 150 burst).
  3. Реализовать `OpenRouterCircuitBreaker`:
     - 5 ошибок подряд $\to$ состояние `OPEN` (блокировка всех вызовов).
     - Cooldown 300 сек $\to$ переключение в `HALF_OPEN`.
     - 2 успешных вызова подряд в `HALF_OPEN` $\to$ возврат в `CLOSED`.

---

### Task 2: Balance Guard & Budget Protection (`REQ-HYB-02`)
- **Files:**
  - `tools/openrouter/balance_guard.py`
- **Actions:**
  1. Реализовать `BalanceGuard`:
     - Запрос баланса через `GET https://openrouter.ai/api/v1/credits` с кэшированием на 300 сек.
     - `ensure_sufficient()`: проверка `credits_remaining >= min_balance_usd` ($10.0 по умолчанию).
     - `ensure_can_process_book()`: проверка `credits_remaining >= estimated_cost_per_book` ($2.0 по умолчанию).
     - Выброс `BalanceExhausted` с понятным сообщением об остатке на счете.

---

### Task 3: Cost Tracker & Checkpoint Management (`REQ-HYB-02`, `REQ-HYB-04`)
- **Files:**
  - `tools/openrouter/cost_tracker.py`
  - `tools/openrouter/checkpoint.py`
- **Actions:**
  1. Реализовать `CostTracker`:
     - Thread-safe лог в `work/openrouter/{book_id}/costs.jsonl`.
     - Накопление суммарных затрат, токенов ввода/вывода, времени выполнения.
     - Метод `write_summary(out_path)` для сохранения итогового `summary_{book_id}.json`.
  2. Реализовать `CheckpointManager`:
     - Сохранение статуса каждого из 12 этапов в `checkpoints/{book_id}_state.json`.
     - `first_incomplete_stage()` для возобновления работы с прерванного места.
     - Персистентность батча в `checkpoints/{book_id}_pending_batch.json` (`batch_id`, `stage`, `items_count`, `model`).

---

### Task 4: OpenRouter Batch Client & Partial Failure Handling (`REQ-HYB-03`, `REQ-HYB-04`)
- **Files:**
  - `tools/openrouter/batch_client.py`
- **Actions:**
  1. Реализовать `BatchClient`:
     - `submit(requests: list[BatchRequest]) -> str`: формирование JSONL, загрузка через `POST /files`, создание батча через `POST /batches` с `completion_window: 24h`.
     - `poll(batch_id: str) -> BatchStatus`: запрос `GET /batches/{batch_id}` (счетчики `total`, `completed`, `failed`).
     - `wait_for_completion(batch_id: str, poll_interval_sec: int = 60)`: ожидание завершения до 24 часов (SLA).
     - `download_results(batch_id: str, out_path: Path) -> Path`: скачивание содержимого файла результатов через `GET /files/{output_file_id}/content`.
  2. Реализовать `_process_batch_results` (Option A):
     - Извлечение успешных ответов и передача дальше по конвейеру.
     - Логирование ошибочных элементов в `work/openrouter/{book_id}/batch_failures.jsonl` без падения пайплайна.

---

### Task 5: 12-Stage Phase Pipeline Orchestrator (`REQ-HYB-05`)
- **Files:**
  - `tools/openrouter/phase.py`
- **Actions:**
  1. Реализовать класс `OpenRouterPhase` со словарем моделей:
     - `filter2`: `qwen/qwen-2.5-vl-7b-instruct`
     - `vlm_annotate`: `qwen/qwen-2.5-vl-32b-instruct`
     - `claims`: `qwen/qwen-2.5-72b-instruct`
     - `triplets`: `qwen/qwen-2.5-72b-instruct`
     - `synthesize`: `qwen/qwen-2.5-72b-instruct`
     - `cluster_critic`: `deepseek/deepseek-r1-0528` (fallback: `deepseek/deepseek-r1`)
     - `rule_critic`: `deepseek/deepseek-r1-0528` (fallback: `deepseek/deepseek-r1`)
  2. Реализовать 12 обработчиков этапов:
     - Stage 1 (`_stage_filter2`): фильтрация картинок (90 $\to$ ~50).
     - Stage 2 (`_stage_vlm_annotate`): аннотация 50 картинок.
     - Stage 3 (`_stage_claims`): извлечение утверждений из 308 чанков через Qwen 72B.
     - Stage 4 (`_stage_triplets`): извлечение триплетов через Qwen 72B.
     - Stage 5 (`_stage_clustering`): локальная кластеризация claims.
     - Stage 6 (`_stage_cluster_critic`): отправка батча на DeepSeek R1, ожидание или сохранение pending batch.
     - Stage 7 (`_stage_synthesize`): синтез правил через Qwen 72B.
     - Stage 8 (`_stage_rule_critic`): отправка батча правил на DeepSeek R1.
     - Stage 9 (`_stage_validation`): локальная валидация (дедупликация, капы, соответствие action $\leftrightarrow$ domain).
     - Stage 10 (`_stage_guardrails`): локальная компиляция `guardrails.md` (≤ 8000 симв.).
     - Stage 11 (`_stage_assemble`): сборка архива `.bookpack.zip` стандарта v0.3.0.
     - Stage 12 (`_stage_sign`): генерация подписи Ed25519 приватным ключом на ПК.
  3. Интеграция событий `on_event` для живого обновления UI и записи в `events.jsonl`.

---

### Task 6: Rich TUI Monitor & Batches View (`REQ-HYB-06`)
- **Files:**
  - `tools/openrouter/tui/__init__.py`
  - `tools/openrouter/tui/monitor.py`
  - `tools/openrouter/tui/batches_view.py`
  - `tools/openrouter/tui/app.py`
- **Actions:**
  1. Реализовать `OpenRouterMonitor`:
     - Чтение `work/openrouter/state.json` каждую секунду.
     - Рендеринг панелей: Header (бюджет, баланс, текущий этап), Stages (прогресс 12 этапов с иконками и стоимостью), Costs (сессия, вызовы, токены), Health (Rate, Circuit, ETA), Live log (последние 5 событий), Hotkeys bar.
     - Звуковые оповещения `play_sound(severity)` (`winsound` на Windows).
  2. Реализовать `BatchesView`:
     - Отображение таблицы активных, завершенных и упавших батчей на серверах OpenRouter за 30 дней.
  3. Реализовать `OpenRouterApp`:
     - Обработка нажатий клавиш: `q` (выход), `b` (отправка батча), `s` (останов), `r` (продолжить), `l` (список батчей), `d` (скачать), `i` (инфо).

---

### Task 7: Config, CLI & Pipeline Auto-Start (`REQ-HYB-07`)
- **Files:**
  - `tools/openrouter/config.py`
  - `tools/openrouter/cli.py`
  - `tools/runpod/runpod_orchestrator.py` (или `pipeline.py`)
- **Actions:**
  1. `OpenRouterConfig`: модель конфигурации с поддержкой `OPENROUTER_API_KEY`, лимитов и таймаутов.
  2. CLI Typer `python -m tools.openrouter.cli run`: параметры `--work-dir`, `--book-id`, `--resume`, `--min-balance`.
  3. Патч точки запуска: автоматический старт `OpenRouterPhase` после завершения RunPod-фазы, если передан `OPENROUTER_API_KEY`.
  4. Реализация `BatchCircuitBreaker`: остановка мульти-книжного прогона при 2 ошибках подряд.

---

### Task 8: Comprehensive Testing & Verification (`REQ-HYB-08`)
- **Files:**
  - `tests/openrouter/test_client.py`
  - `tests/openrouter/test_rate_limiter.py`
  - `tests/openrouter/test_circuit_breaker.py`
  - `tests/openrouter/test_balance_guard.py`
  - `tests/openrouter/test_cost_tracker.py`
  - `tests/openrouter/test_batch_client.py`
  - `tests/openrouter/test_checkpoint.py`
  - `tests/openrouter/test_partial_failure.py`
  - `tests/openrouter/test_phase_e2e.py`
- **Actions:**
  1. Юнит-тесты с моками `httpx`:
     - Retry на 429 и таймауты, моментальный отказ на 402/401.
     - Блокировка и восстановление токенов в `RateLimiter`.
     - Переход `CLOSED` $\to$ `OPEN` $\to$ `HALF_OPEN` $\to$ `CLOSED` в `CircuitBreaker`.
     - Выброс `BalanceExhausted` при низком балансе.
     - Запись и расчет сумм в `CostTracker`.
     - Загрузка, поллинг и скачивание файлов в `BatchClient`.
     - Персистентность состояния и `pending_batch.json` при перезапуске.
     - Обработка 95 успешных и 5 сбойных элементов батча.
     - Сквозной E2E тест 12 этапов с замоканным API.
  2. Запуск `pytest tests/openrouter/` (100% PASS).

---

## 5. Success Criteria & Verification Gates

| Метрика / Проверка | Чистый RunPod | Гибридный RUNPOD-H | Критерий успеха |
|---|---|---|---|
| **E2E время обработки книги** | 4.5–5 часов | **2–2.5 часа** | ⚡ Ускорение в 2 раза |
| **Стоимость на 1 книгу** | ~$2.00 (GPU) | **~$1.30–$1.80** (GPU + API) | 💰 Экономия бюджета |
| **Параллелизм LLM** | Последовательно (1 GPU) | **Параллельно** (OpenRouter) | 🚀 Высокая пропускная способность |
| **Batch Persistence** | Нет | **Да** (`pending_batch.json`) | 🔒 ПК можно выключать |
| **Partial Failure Handling** | Падение | **Option A: use 95, log 5** | 🛡️ Устойчивость к сбоям |
| **Защита баланса** | Нет | **Останов при < $10** | 🛑 Защита от перерасхода |
| **Unit Tests Coverage** | — | **100% PASS** (`tests/openrouter/`) | ✅ Зеленый тестовый стенд |
