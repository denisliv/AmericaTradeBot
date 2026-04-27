# AmericaTrade Telegram Bot

Telegram-бот для компании AmericaTrade, специализирующейся на подборе и покупке автомобилей из США. Бот предоставляет пользователям возможность подбирать автомобили по различным критериям, подписываться на уведомления о новых лотах и получать консультации от AI-менеджера.

## Основные возможности

- **Подбор автомобилей**: самостоятельный и ассистированный подбор по различным критериям
- **Подписки**: уведомления о новых автомобилях по выбранным параметрам
- **AI-чат**: AI-менеджер (LangGraph), RAG на FAISS, инструменты и лиды, интеграция с Bitrix
- **Административные функции**: пользователи, статистика, модерация, рассылки
- **Промо-рассылки и контент**: запланированные посты и напоминания (APScheduler)
- **Данные аукционов**: работа с внешними источниками (в т.ч. Copart)

## Архитектура проекта

```
AmericaTrade/
├── app/
│   ├── bot/                      # Telegram: handlers, middlewares, keyboards, states
│   ├── infrastructure/
│   │   ├── database/             # Подключение, схема, db helpers
│   │   └── services/           # AI Manager, рассылки, Bitrix, утилиты
│   └── lexicon/                # Тексты бота
├── config/                       # Загрузка настроек из переменных окружения
├── data/                         # Контент (posts, ai_manager, CSV), векторное хранилище
├── migrations/                   # Создание таблиц PostgreSQL
├── tests/                        # Pytest
├── main.py                       # Точка входа
├── pyproject.toml / uv.lock      # Зависимости (uv)
├── Dockerfile                    # Образ приложения (Python 3.13, uv)
└── docker-compose.yml            # PostgreSQL 16, Redis 7, бот
```

## Технологический стек

- **Python 3.13+**, управление зависимостями — **[uv](https://docs.astral.sh/uv/)**
- **aiogram 3.x** — Telegram Bot API (long polling)
- **PostgreSQL** — основная БД (**psycopg** / **psycopg-pool**)
- **Redis** — FSM storage, отдельная БД для промо-логики
- **OpenAI API** — чат и эмбеддинги для RAG
- **LangChain / LangGraph** — оркестрация AI-менеджера
- **FAISS** — векторный индекс для RAG
- **APScheduler** — фоновые задачи и рассылки
- **Docker** — контейнер приложения и **Docker Compose** для полного стека (БД + Redis + бот)

## Требования

**Локальная разработка**

- Python 3.13+
- PostgreSQL 12+
- Redis 6+
- Telegram Bot Token, OpenAI API Key (и при необходимости вебхук Bitrix)
- **uv** для установки зависимостей из `pyproject.toml`

**Запуск только в Docker на сервере**

- Установленные **Docker Engine** и плагин **Compose v2** (команда `docker compose`)
- Ключи и токены в файле **`.env`** (см. `env.example`)
- Исходящий HTTPS до api.telegram.org, OpenAI и других используемых API

## Установка и настройка (локально, без Docker)

### 1. Клонирование репозитория

```bash
git clone git@github.com:denisliv/AmericaTradeBot.git
cd AmericaTrade
```

### 2. Установка uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Установка зависимостей

```bash
uv sync
```

### 4. Переменные окружения

Скопируйте шаблон и заполните значения:

```bash
cp env.example .env
```

Полный перечень переменных и комментарии — в **`env.example`**. Обязательно задайте как минимум:

- `BOT_TOKEN`, `ADMIN_IDS`
- `POSTGRES_*` (хост, порт, БД, пользователь, пароль)
- `REDIS_*` (хост, порт; для промо используется отдельный номер БД: `REDIS_PROMO_DATABASE`)
- `API_KEY` (и при необходимости блок `EMBEDDINGS_*` для другой модели/ключа)
- для AI Manager — при необходимости `AI_MANAGER_*`, пути по умолчанию смотрите в `config/config.py`
- опционально: `BITRIX_WEBHOOK_URL`, `COPART_URL`, `LOG_LEVEL`, `LOG_FORMAT`

### 5. База данных

Создайте базу в PostgreSQL (если её ещё нет):

```sql
CREATE DATABASE america_trade;
```

Примените миграции:

```bash
uv run python migrations/create_tables.py
```

Дополнительные таблицы при необходимости создаются при старте бота (например, метрики через `ensure_metrics_tables` в `app/infrastructure/database/db.py`).

### 6. Запуск бота

```bash
uv run python main.py
```

### 7. Тесты

```bash
uv sync --dev
uv run pytest
```

## Структура базы данных (основное)

Точная схема задаётся в **`migrations/create_tables.py`** и **`app/infrastructure/database/schema.py`**. Среди прочего:

- **users** — пользователи бота
- **self_selection_requests** / **assisted_selection_requests** — заявки подбора
- **chat_history** — история сообщений для контекста
- **bot_metrics_events**, **bot_delivery_metrics** — метрики (SQL из `schema.py`)

Остальные объекты (подписки, рассылки и т.д.) описаны и создаются в коде БД-слоя по мере развития проекта.

## Основные компоненты

**Обработчики** (примеры): `users`, `self_selection`, `assisted_selection`, `subscriptions`, `llm_chat`, `admin`, `admin_mailing`, `consultation_request`, `others`.

**Сервисы**: каталог `app/infrastructure/services/ai_manager/` (LangGraph, RAG, tools), рассылки, интеграция с Bitrix, загрузка данных и утилиты.

## Команды бота (фрагмент)

- `/start` — приветствие
- `/help` — справка
- `/subscription` — подписки
- `/chat` — чат с AI-менеджером
- Админ-команды — статистика, бан/разбан и др. (см. `ADMIN_IDS` в `.env`)

## Планировщик и фоновые задачи

Используется **APScheduler**: обновление данных (CSV), рассылки подписчикам, промо и связанные задачи (см. `app/bot/scheduler.py` и сервисы рассылок).

## Безопасность и лимиты

В боте применяются middleware для ограничения частоты запросов, теневого бана, учёта активности и ограничений на действия; чувствительные настройки задаются через переменные окружения.

## Логирование

Уровень и формат задаются в `.env` (`LOG_LEVEL`, `LOG_FORMAT`); при старте `main.py` подхватывает `config.config.load_config`.

## Развертывание на сервере в Docker

Ниже предполагается Linux-сервер (например, Ubuntu 22.04/24.04) с правами пользователя, входящего в группу `docker` (или с `sudo` для Docker).

### Шаг 1. Установить Docker и Compose

Официальная инструкция: [Install Docker Engine](https://docs.docker.com/engine/install/). После установки проверьте:

```bash
docker --version
docker compose version
```

### Шаг 2. Получить код на сервер

```bash
git clone <URL-вашего-репозитория> AmericaTrade
cd AmericaTrade
```

### Шаг 3. Настроить `.env`

```bash
cp env.example .env
nano .env
```

Укажите реальные значения:

- **Telegram**: `BOT_TOKEN`, `ADMIN_IDS`
- **PostgreSQL**: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — они же используются сервисом `postgres` в `docker-compose.yml` и должны совпадать с тем, что читает приложение
- **Порты**: `POSTGRES_PORT=5432`, `REDIS_PORT=6379` (внутри сети Compose менять обычно не нужно)
- **Redis**: для текущего `docker-compose.yml` оставьте **`REDIS_PASSWORD` пустым** (Redis без пароля в приватной сети контейнеров). Номера БД: `REDIS_DATABASE=0`, `REDIS_PROMO_DATABASE=1`
- **OpenAI и прочее**: `API_KEY`, при необходимости `EMBEDDINGS_*`, `BITRIX_WEBHOOK_URL` и остальное из `env.example`

Имя хоста БД и Redis для контейнера бота задаётся в `docker-compose.yml` (`POSTGRES_HOST=postgres`, `REDIS_HOST=redis`) и **перекрывает** возможные `localhost` в вашем `.env` — всё равно задайте в `.env` согласованные `POSTGRES_*` и пароль.

### Шаг 4. Собрать образ приложения

```bash
docker compose build
```

### Шаг 5. Применить миграции (первый запуск и после смены DDL)

Поднимутся зависимости (Postgres/Redis), выполнится скрипт миграций:

```bash
docker compose run --rm bot python migrations/create_tables.py
```

Убедитесь в логах, что таблицы созданы без ошибок.

### Шаг 6. Запустить стек в фоне

```bash
docker compose up -d
```

Сервисы: **postgres** (том `postgres_data`), **redis** (том `redis_data`, AOF), **bot** (том `ai_data` для каталога FAISS под `data/vectorstore/ai_manager`).

Порты PostgreSQL и Redis **наружу не пробрасываются** — доступ только между контейнерами. Для Telegram long polling **входящие** подключения к серверу не нужны (нужен исходящий интернет).

### Шаг 7. Проверить логи бота

```bash
docker compose logs -f bot
```

Остановка и перезапуск:

```bash
docker compose down
docker compose up -d
```

Обновление версии кода:

```bash
git pull
docker compose build
docker compose run --rm bot python migrations/create_tables.py   # если менялись миграции
docker compose up -d
```
