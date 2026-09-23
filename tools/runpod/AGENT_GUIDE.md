# RunPod Cloud Pipeline — Automated User Guide & Zero-Touch Workflow

Этот документ описывает **100% автоматизированный сценарий** развертывания и запуска пайплайна на RunPod без ручной возни, зависаний и с защитой бюджета (`Auto-Stop`).

---

## 1. Архитектура и скорость работы

| Что тормозило ранее (Ручной путь) | Как работает сейчас (Автоматический оркестратор) | Время |
|---|---|:---:|
| 1. Ручной выбор и запуск пода в браузере | Под создается / возобновляется через **RunPod GraphQL API** с авто-выбором **RTX 5090 / 4090** | ~15 сек |
| 2. Попытки передачи через SSH Gateway / croc | Прямой **SCP через Exposed TCP порт** на полной скорости сети | ~20 сек |
| 3. Зависания из-за PTY эмуляции терминала | Выполнение команд через чистый non-interactive `ssh` | ~5 сек |
| 4. Ручная настройка Ollama и VLM | Автоматический bootstrap скрипт на поде (установка Ollama, запуск демона, pull 32B VLM) | ~90 сек |
| 5. Мониторинг "вслепую" | Интерактивный **Rich Live TUI Дашборд** с живыми t/s, VRAM, temp, прогресс-барами | Реал-тайм |
| 6. Риск забыть включенный под на ночь | **Auto-Stop & Inactivity Guard**: авто-выключение при завершении ($0/ч) и при простое > 15 мин | $0 лишних трат |
| **ИТОГО ДО СТАРТА ПАЙПЛАЙНА** | **Полная автоматизация без участия человека** | **~2–3 мин** |

---

## 2. Пользовательский сценарий "Всё в один клик" (Zero-Touch)

### Шаг 1: Заполнить файл секретов (`tools/runpod/.env`)
Создается один раз (шаблон в `.env.example`):
```env
# RunPod API Key
RUNPOD_API_KEY=rpa_YOUR_API_KEY

# SSH Access
SSH_KEY_PATH=tools/runpod/id_ed25519

# GPU Preference (RTX 5090 или RTX 4090)
GPU_TYPE=NVIDIA GeForce RTX 5090
GPU_COUNT=1
POD_DISK_SIZE_GB=40

# Folders & Behavior
SOURCE_BOOKS_DIR=.init_doc/source_doc
OUTPUT_BOOKPACKS_DIR=qa/bookpacks
AUTO_STOP=true
VLM_MODEL=qwen2.5vl:32b
```

---

### Шаг 2: Запустить одну команду

* **Сборка книги Sail and Rig Tuning (по умолчанию):**
  ```bash
  python tools/runpod/runpod_orchestrator.py
  ```

* **Сборка конкретной книги или всех книг:**
  ```bash
  python tools/runpod/runpod_orchestrator.py --book sail_and_rig_tuning
  python tools/runpod/runpod_orchestrator.py --book illustrated_seamanship
  python tools/runpod/runpod_orchestrator.py --book all
  ```

* **Оффлайн Dry-Run / Mock-режим:**
  ```bash
  python tools/runpod/tui.py --mock
  python tools/runpod/runpod_orchestrator.py --dry-run
  ```

---

## 3. База знаний по проблемам запуска и их решениям (Troubleshooting & RCA)

В ходе разработки и боевой отладки пайплайна были выявлены и устранены следующие ключевые проблемы:

### 1. Windows NTFS ACLs на приватном ключе (`tools/runpod/id_ed25519`)
* **Проблема:** Windows OpenSSH аварийно прерывает соединение с ошибкой `WARNING: UNPROTECTED PRIVATE KEY FILE! Permissions for 'id_ed25519' are too open`, если файл имеет наследуемые или групповые права доступа.
* **Решение:** Настроены строгие права ACL через `icacls tools/runpod/id_ed25519 /inheritance:r /grant:r "$($env:USERNAME):(R)"`.

### 2. Запуск SSH-демона в официальных контейнерах RunPod (`PUBLIC_KEY`)
* **Проблема:** В образах `runpod/pytorch:*` демон SSH (`sshd`) на порту 22 стартует **только** в том случае, если в окружении контейнера передана переменная `PUBLIC_KEY`. Без нее порт 22 отдавал `Connection refused`.
* **Решение:** Метод `RunPodClient.deploy_pod` автоматически извлекает публичный ключ из `id_ed25519` через `ssh-keygen -y` и передает его в `env: [{"key": "PUBLIC_KEY", "value": pub_key}]`.

### 3. Ubuntu 24.04 PEP 668 (`externally-managed-environment`)
* **Проблема:** При попытке `pip install` на свежем образе Ubuntu 24.04 pip блокирует установку системных пакетов (`error: externally-managed-environment`), из-за чего зависимости (`pydantic`, `docling`) не ставились.
* **Решение:** Команда установки пакета в bootstrap вызывается с флагом `--break-system-packages`:
  `python3 -m pip install --break-system-packages -e '/root/SIA_MKP[builder]'`.

### 4. Автономный Bootstrap на чистых подах
* **Проблема:** Развертывание на чистом поде не содержало Ollama и модели 32B.
* **Решение:** Оркестратор производит полный bootstrap:
  1. `which ollama` $\rightarrow$ при отсутствии ставит через `curl -fsSL https://ollama.com/install.sh | sh`.
  2. Запускает демон `nohup ollama serve > /root/ollama.log 2>&1 &`.
  3. Проверяет наличие `qwen2.5vl:32b` $\rightarrow$ скачивает по датацентр-сети.
  4. Копирует `src/` и `pyproject.toml` $\rightarrow$ выполняет `pip install`.

### 5. Видимость логов до старта TUI
* **Проблема:** Во время подготовки (поиск пода, SSH, скачивание модели) терминал молчал, что создавало ощущение зависания.
* **Решение:** В `OrchestratorLogger` реализован прямой цветной вывод всех этапов в терминал в реальном времени с таймстемпами. Вывод глушится только в момент отрисовки `Live TUI`.

### 6. Исключение видеокарт с VRAM < 24 GB
* **Проблема:** Модель Qwen2.5-VL 32B (Q4_K_M) требует ~21.5 ГБ VRAM. Запуск на RTX 5080/4080 (16 ГБ) приводит к сбросу в RAM и замедлению до < 0.5 t/s.
* **Решение:** Введен жесткий фильтр `DISALLOWED_GPUS` и каскад:
  1. `RTX 5090` (32 GB, ~30 t/s) — **ТОП-1**
  2. `RTX 4090` (24 GB, ~16 t/s) — **ТОП-2**
  3. `RTX 5000 Ada / A6000` (32–48 GB) — **ТОП-3**
  4. `RTX A5000 / 3090` (24 GB) — **ТОП-4**

### 8. Сбор метрик ресурсов (RAM, Pod Disk, CPU, GPU Load)
* **Проблема:** Ранее в TUI отображались нулевые значения RAM/Disk, а GPU Util ошибочно попадал в поле CPU.
* **Решение:** В `RunPodOrchestrator.fetch_remote_telemetry()` внедрен составной SSH-запрос за один раундтрип:
  - Читает `/tmp/mkp_progress.json`
  - Вычисляет RAM хоста из `/proc/meminfo` (`MemTotal - MemAvailable`)
  - Вычисляет занятый/общий диск пода через `shutil.disk_usage('/')`
  - Считывает среднюю загрузку CPU и ядра через `os.getloadavg()`, `os.cpu_count()`
  - Запрашивает `nvidia-smi` (Util %, VRAM, Temp, Power)
  - `RunPodDashboard.update_telemetry()` корректно обновляет обе колонки панели ресурсов.

---

## 4. Архитектура работы для ИИ-Агента

Если задачу выполняет ИИ-агент (Antigravity):
1. **Единая команда:** Всегда запускать `python tools/runpod/runpod_orchestrator.py --book sail_and_rig_tuning`.
2. **Никаких `ssh -tt` gateway сессий:** Работать **только** через Exposed Direct TCP порт (`client.get_pod_status_and_ip()`).
3. **Таймауты VLM:** Всегда `timeout=600.0` в `OllamaClient` и `num_predict=2048` в `VLMAnnotator`.
4. **Мониторинг:** Читать JSON-состояние `/tmp/mkp_progress.json` и `nvidia-smi`.
5. **Завершение:** Всегда проверять целостность архивов и вызывать `podStop` (автоматически включено в оркестратор).
