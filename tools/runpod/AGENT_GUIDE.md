# RunPod Cloud Pipeline — Automated User Guide & Zero-Touch Workflow

Этот документ описывает **100% автоматизированный сценарий** развертывания и запуска пайплайна на RunPod без ручной возни и зависаний.

---

## 1. Почему следующий запуск займет 2–3 минуты (а не 1+ час)?

| Что тормозило ранее (Ручной путь) | Как работает сейчас (Автоматический пайплайн) | Время |
|---|---|:---:|
| 1. Ручной выбор и запуск пода в браузере | Под создается / возобновляется через **RunPod API** одной командой | ~15 сек |
| 2. Попытки передачи через SSH Gateway / croc | Прямой **SCP через Exposed TCP порт** на полной скорости сети | ~20 сек |
| 3. Зависания из-за PTY эмуляции терминала | Выполнение команд через чистый `ssh` non-interactive headless | ~5 сек |
| 4. Ручная настройка Ollama и VLM | Автоматический bootstrap скрипт на поде | ~60 сек |
| **ИТОГО ДО СТАРТА ПАЙПЛАЙНА** | **Полная автоматизация без участия человека** | **~2–3 мин** |

---

## 2. Пользовательский сценарий "Всё в один клик" (Zero-Touch)

### Шаг 1: Заполнить файл секретов (`tools/runpod/.env`)
Создается один раз:
```env
# RunPod API Key
RUNPOD_API_KEY=rpa_YOUR_RUNPOD_API_KEY_HERE

# SSH Access
SSH_KEY_PATH=C:/Users/User/.ssh/id_ed25519

# GPU Preference (RTX 4090 24GB)
GPU_TYPE=NVIDIA GeForce RTX 4090
GPU_COUNT=1

# Folders
SOURCE_BOOKS_DIR=.init_doc/source_doc
OUTPUT_BOOKPACKS_DIR=qa/bookpacks

# Behavior
AUTO_STOP_ON_FINISH=true
MODEL_NAME=qwen2.5vl:32b
```

---

### Шаг 2: Запустить одну команду
```bash
python tools/runpod/runpod_orchestrator.py
```

Что делает оркестратор автоматически:
1. **Проверяет поды:** Ищет существующий под. Если нет — создает новый под на **NVIDIA GeForce RTX 4090 (24 GB)** через GraphQL API.
2. **Получает Exposed TCP IP и Port:** Сам извлекает актуальный порт SSH (например, `22049`).
3. **Bootstraps Pod:** Проверяет Ollama, скачивает `qwen2.5vl:32b` (на скорости датацентра 1–2 Гбит/с), ставит `mkp==1.5.0`.
4. **Заливает книги:** Копирует все `.epub` и `.pdf` из `SOURCE_BOOKS_DIR` на под через прямой SCP.
5. **Запускает сборку:** Стартует `run_build_32b.py` с таймаутом `600s` и полным контекстом `num_predict=2048`.
6. **Отображает TUI Дашборд:** Показывает прогресс-бары книг, этапов, температуру, скорость VLM (15+ t/s на 4090) и лог ошибок.
7. **Скачивает результат:** По окончании загружает `.bookpack.zip` в `OUTPUT_BOOKPACKS_DIR` и проверяет SHA256.
8. **Автоматически выключает Pod:** Отправляет команду `podStop`, останавливая списание баланса ($0.74/hr $\rightarrow$ $0/hr).

---

## 3. Архитектура работы для ИИ-Агента

Если задачу выполняет ИИ-агент (Antigravity):
1. **Никаких `ssh -tt` gateway сессий:** Работать **только** через Exposed Direct TCP порт (`runpod_api.get_exposed_ports()`).
2. **Таймауты VLM:** Всегда `timeout=600.0` в `OllamaClient` и `num_predict=2048` в `VLMAnnotator`.
3. **Мониторинг:** Использовать `tools/runpod/runpod_manager.py status` или читать JSON-состояние `/tmp/mkp_progress.json`.
4. **Завершение:** Всегда проверять целостность архивов и вызывать `tools/runpod/runpod_manager.py stop` (или через API `client.stop_pod()`).
