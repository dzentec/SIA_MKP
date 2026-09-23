# RunPod Zero-Touch TUI & Orchestration System — Complete Specification & Implementation Plan

> **Цель:** Полностью автоматизированная система "Zero-Touch", позволяющая пользователю или ИИ-агенту заполнить конфигурацию секретов, запустить 1 команду, увидеть интерактивный TUI-дашборд прогресса на RTX 4090 (24GB), автоматически скачать готовые `.bookpack.zip` архивы и автоматически отключить под по завершению для нулевого расхода средств.

---

## 1. Сценарий использования (User Experience)

### Шаг 1: Конфигурация (`tools/runpod/.env`)
Пользователь заполняет простой файл конфигурации:
```env
# RunPod API Key
RUNPOD_API_KEY=rpa_YOUR_RUNPOD_API_KEY_HERE

# SSH Key
SSH_KEY_PATH=C:/Users/User/.ssh/id_ed25519

# Выбор GPU (RTX 4090 24GB или RTX A5000)
GPU_TYPE=NVIDIA GeForce RTX 4090
GPU_COUNT=1
POD_DISK_SIZE_GB=40

# Папки ввода/вывода
SOURCE_BOOKS_DIR=.init_doc/source_doc
OUTPUT_BOOKPACKS_DIR=qa/bookpacks

# Модель и поведение
VLM_MODEL=qwen2.5vl:32b
AUTO_STOP=true
```

### Шаг 2: Запуск одной командой
```bash
python tools/runpod/runpod_orchestrator.py
```

---

## 2. Архитектура автоматического оркестратора (`runpod_orchestrator.py`)

```
   ┌────────────────────────────────────────────────────────────┐
   │             `runpod_orchestrator.py` Workflow              │
   └─────────────────────────────┬──────────────────────────────┘
                                 │
                   1. Чтение .env и проверка API
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────┐
   │            Поиск / Создание Пода через API                 │
   │  • Если под существует -> возобновить (`podResume`)        │
   │  • Если пода нет -> создать на RTX 4090 (`podFindAndDeploy`)│
   └─────────────────────────────┬──────────────────────────────┘
                                 │
                   2. Авто-определение Exposed IP:Port
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────┐
   │           Быстрый Bootstrap (2 минуты)                     │
   │  • Проверка Ollama & Pull qwen2.5vl:32b (датацентр 2Gbps)  │
   │  • Прямой SCP книг из `SOURCE_BOOKS_DIR` (15 секунд)       │
   │  • Установка `mkp==1.5.0`                                  │
   └─────────────────────────────┬──────────────────────────────┘
                                 │
                   3. Старт сборки на 32B VLM
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────┐
   │           Интерактивный TUI Дашборд (Rich)                 │
   │  • Прогресс-бар книг (1/2, 2/2)                            │
   │  • Детальный прогресс этапа (диаграммы 18/24, триплеты)    │
   │  • Живые метрики GPU (RTX 4090: 15+ t/s, 23.5GB VRAM, 52°C)│
   │  • Окно ошибок и логов                                     │
   └─────────────────────────────┬──────────────────────────────┘
                                 │
                   4. Завершение сборки
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────────┐
   │           Авто-скачивание и Защита Бюджета                 │
   │  • Скачивание `.bookpack.zip` в `OUTPUT_BOOKPACKS_DIR`     │
   │  • Проверка SHA256 хешей по манифесту                      │
   │  • Вызов `podStop` через API -> $0/час тарификация         │
   │  • Вывод красивого финального отчета                       │
   └────────────────────────────────────────────────────────────┘
```

---

## 3. Макет интерфейса TUI Дашборда (Rich Live)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ MKP PIPELINE DASHBOARD — RUNPOD CLUSTER               Pod: rtx4090-worker (Running · $0.74/hr)    ┃
┃ [Auto-Stop: ON (Защита бюджета)]                                        Uptime: 00:24:18         ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ 🖥️ СИСТЕМНЫЕ РЕСУРСЫ:                                                                             ┃
┃   • CPU Load:  [████░░░░░░░░░░░░░░░░] 22% (8 vCPUs)     • GPU:   RTX 4090 24GB (Temp: 51°C · 95W) ┃
┃   • RAM Usage: [████████░░░░░░░░░░░░] 14.2 / 32.0 GB    • VRAM:  23.4 / 24.0 GB (97% · 16.4 t/s) ┃
┃   • Pod Disk:  [███████████░░░░░░░░░] 22.1 / 40.0 GB    • Net:   ↓ 120 KB/s · ↑ 45 KB/s          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  [ОЧЕРЕДЬ КНИГ]
  Всего книг: [████████████████████░░░░░░░░░░░░░░░░░░░░] 50.0% (Обработано 1 из 2)
  Текущая:    Illustrated Seamanship (Ivar Dedekam) [EPUB · 5.4 MB]

  [ЭТАПЫ ОБРАБОТКИ]
  ├── 1. Извлечение текста и диаграмм        [✓ ВЫПОЛНЕНО ] (28 изображений найдено)
  ├── 2. VLM Аннотирование схем (32B)        [✓ ВЫПОЛНЕНО ] (28/28 схем, 1 предупреждение)
  ├── 3. GraphRAG Семантические триплеты     [██████████████░░░░░░] 70.8% (68/96 чанков)
  ├── 4. Синтез морских правил               [· В ОЧЕРЕДИ ]
  └── 5. Экспорт .bookpack.zip               [· В ОЧЕРЕДИ ]

  ┌── Живой лог событий и ошибок ──────────────────────────────────────────────────────────────────┐
  │ 18:21:31 [INFO] Начата сборка книги: illustrated_seamanship (Tier 1)                           │
  │ 18:27:08 [INFO] VLM аннотирование запущено на qwen2.5vl:32b                                    │
  │ 18:30:38 [WARN] Схема 1b2be8f77542: ответ превысил 512 токенов -> расширен бюджет до 2048     │
  │ 18:34:12 [INFO] Извлечение триплетов: чанк 65 -> найдено 7 морских отношений                  │
  └────────────────────────────────────────────────────────────────────────────────────────────────┘
  [Горячие клавиши: 'q' - выход из TUI | 'd' - скачать архивы | 's' - остановить под сейчас]
```

---

## 4. Локальное логирование работы (Local Run Logging)

### Назначение
Даже если терминал с TUI закрыт или связь прервалась, на локальной машине пользователя сохраняется **полная хронология сессии**:
* **Путь к логам:** `tools/runpod/logs/session_YYYYMMDD_HHMMSS.log`
* **Ссылка на последний лог:** `tools/runpod/logs/latest.log`

### Что фиксируется в локальном логе:
1. **События инфраструктуры:** ID созданного/найденного пода, модель GPU, IP, Exposed SSH порт, стоимость часа.
2. **Передача данных:** Список и размеры переданных на сервер книг, время загрузки по SCP.
3. **Хронология сборки:** Время старта каждого этапа (парсинг, VLM, триплеты, правила, экспорт) для каждой книги.
4. **Метрики инференса:** Скорость генерации токенов (t/s), задержка VLM, температура GPU, занятая память VRAM.
5. **Ошибки и предупреждения:** Все исключения и ошибки парсинга с полным stacktrace и контекстом.
6. **Финализация:** Хеши SHA256 и размеры скачанных `.bookpack.zip`, статус выполнения API команды `podStop` (подтверждение остановки списания баланса).

---

## 5. Cost Protection & Auto-Shutdown Feature

### Objective
Automatically stop the pod when all books are built and downloaded, guaranteeing **zero wasted cost** (preventing accidental overnight charges at $0.27/hr).

### Mechanism
1. **Completion Trigger:**
   * When `mkp-builder` finishes exporting all `.bookpack.zip` files for the queue.
   * Local manager downloads all archives and verifies SHA256 against manifests.
2. **Auto-Stop Execution via RunPod API:**
   * Mutation: `podStop(input: {podId: $pod_id})`
   * API Endpoint: `https://api.runpod.io/graphql`
   * Headers: `Authorization: Bearer <API_KEY>`
3. **Safety Fallback on Pod:**
   * On the pod, the runner script `run_build_32b.py` can optionally execute `runpodctl stop pod $RUNPOD_POD_ID` or `/sbin/poweroff` if `--auto-shutdown` is passed.
4. **TUI Indicator:**
   * TUI displays a toggle indicator: `[Auto-Stop: ON (Saves $$$)]`.

---

## 6. Implementation Steps for the Next Phase

1. **Step 1 — Structured Telemetry Hook (`src/mkp_builder/tui.py`):**
   * Add `BuilderProgressTracker.publish_state(state_file)` that updates `/tmp/mkp_progress.json` on each loop iteration with zero I/O overhead.
2. **Step 2 — RunPod API Client & Auto-Stop (`tools/runpod/runpod_api.py`):**
   * Implement GraphQL queries for pod lifecycle, IP discovery, billing stats, and `podStop` / `podTerminate`.
3. **Step 3 — Local Logging Engine (`tools/runpod/logger.py`):**
   * Dedicated rotating file logger with timestamps, levels, and realtime flush to `tools/runpod/logs/`.
4. **Step 4 — Interactive Dashboard & Orchestrator (`tools/runpod/runpod_orchestrator.py`):**
   * Build the `rich.live.Live` auto-refreshing dashboard (refresh rate: 1.5s).
   * Stream events into both UI panels and local log files.
   * Include hotkeys (`q` quit, `d` download, `s` stop pod, `t` toggle auto-shutdown).
5. **Step 5 — Automated Downloader & Verifier Pipeline:**
   * When `progress.json` reports `total_stages == DONE`:
     1. Download `.bookpack.zip` to `OUTPUT_BOOKPACKS_DIR`.
     2. Verify checksums.
     3. Trigger `podStop`.
     4. Save summary to `tools/runpod/logs/latest.log` and notify user.


---

## 5. Гарантии надежности для следующих запусков

1. **Время старта:** $\le$ **3 минут** от запуска команды до начала генерации VLM.
2. **Скорость работы на RTX 4090:** $\approx$ **15–18 токенов/сек** ($\approx$ **45 минут на 2 книги** вместо 5 часов на A5000).
3. **Защита бюджета:** При успешном завершении или при фатальной ошибке под **автоматически выключается**, исключая случайные списания.
4. **Автономность агента:** Любой ИИ-агент может запустить пайплайн одной командой `python tools/runpod/runpod_orchestrator.py` без интерактивных зависаний.
