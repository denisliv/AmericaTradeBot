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
├── alembic/                      # Миграции схемы БД (Alembic)
│   ├── env.py
│   └── versions/
├── alembic.ini
├── grafana/                      # Dashboards и provisioning для Grafana
│   ├── dashboards/
│   └── provisioning/
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
- **Alembic** — версионируемые миграции схемы PostgreSQL
- **Grafana** — операционные и продуктовые дашборды поверх Postgres
- **Docker** — контейнер приложения и **Docker Compose** для полного стека (БД + Redis + бот + Grafana)

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
- `POSTGRES_*` (хост, порт, БД, пользователь, пароль). Опционально: `POSTGRES_POOL_MIN_SIZE`, `POSTGRES_POOL_MAX_SIZE` (по умолчанию 5/20)
- `REDIS_*` (хост, порт; для промо используется отдельный номер БД: `REDIS_PROMO_DATABASE`)
- `API_KEY` — **обязательная** переменная. При необходимости — блок `EMBEDDINGS_*` для другой модели/ключа
- для AI Manager — при необходимости `AI_MANAGER_*`, пути по умолчанию смотрите в `config/config.py`
- опционально: `BITRIX_WEBHOOK_URL`, `COPART_URL`, `LOG_LEVEL`, `LOG_FORMAT`
- опционально: `GRAFANA_PUBLIC_URL` (ссылка из /admin), `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`

### 5. База данных

Создайте базу в PostgreSQL (если её ещё нет):

```sql
CREATE DATABASE america_trade;
```

Примените миграции через Alembic:

```bash
uv run alembic upgrade head
```

Если у вас уже есть существующая БД, схема которой была создана старым скриптом `migrations/create_tables.py`, отметьте начальную ревизию как применённую перед накатом новых:

```bash
uv run alembic stamp 0001
uv run alembic upgrade head
```

Все DDL (включая таблицы метрик `bot_metrics_events`, `bot_delivery_metrics`) теперь управляются Alembic-миграциями в `alembic/versions/`. Runtime-инициализация схемы при старте бота больше не выполняется.

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

Точная схема задаётся миграциями Alembic в `alembic/versions/`. Среди прочего:

- **users** — пользователи бота
- **self_selection_requests** / **assisted_selection_requests** — заявки подбора
- **chat_history** — история сообщений для контекста
- **bot_metrics_events**, **bot_delivery_metrics** — метрики

Временная таблица **admin_mailing** создаётся/удаляется в рантайме перед каждой админ-рассылкой (`admin_mailing_prepare_for_broadcast` в `app/infrastructure/database/db.py`).

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

## Метрики и Grafana

Бот пишет два потока в Postgres:

- `bot_metrics_events` — продуктовые события (`self_flow_started`, `self_completed_search`, `llm_lead_sent`, `ai_rag_hit`, `telegram_retry_after` и т.п.). Колонка `value` хранит payload — например, количество найденных авто для `self_completed_search` или длительность retry-after.
- `bot_delivery_metrics` — категория/статус/`duration_ms` для рассылок и LLM-ответов (`category='llm_chat'`, `status='ok'` или `'error'`).

Поверх таблиц поднимаются 5 materialized views (см. миграцию `0003_metrics_views.py`):

- `mv_events_hourly`, `mv_delivery_hourly` — почасовые агрегаты для realtime-графиков
- `mv_users_daily` — регистрации, активность, подписчики по дням
- `mv_self_funnel_daily`, `mv_llm_funnel_daily` — воронки self-selection и LLM-чата

Views обновляются `REFRESH MATERIALIZED VIEW CONCURRENTLY` раз в 5 минут через APScheduler-job `metrics_mv_refresh`. AI Manager метрики флашатся в `bot_metrics_events` раз в минуту job-ом `ai_manager_metrics_flush`.

### Grafana

Контейнер `grafana` поднимается рядом с ботом в `docker-compose.yml`. Datasource и стартовый дашборд провизионятся из `grafana/provisioning/` и `grafana/dashboards/`.

```bash
docker compose up -d grafana
# Откройте http://localhost:3000 (через SSH-туннель в продакшене)
# Логин/пароль — GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD из .env
```

После открытия дашборда `AmericaTrade Bot — Overview` поставьте публичный URL (например, `https://grafana.example.com/d/americatrade-overview`) в `.env` как `GRAFANA_PUBLIC_URL` — он отобразится как ссылка в `/admin → Статистика`.

### Админ-сводка

В `/admin → Статистика` бот возвращает только 4 KPI: всего пользователей, регистрации сегодня, с активной подпиской, среднее число авто на подписку. Подробная аналитика и графики — в Grafana по ссылке.

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

Поднимутся зависимости (Postgres/Redis), выполнится команда миграций:

```bash
docker compose run --rm bot alembic upgrade head
```

Для миграции с уже существующей БД (схема создана старым `migrations/create_tables.py`):

```bash
docker compose run --rm bot alembic stamp 0001
docker compose run --rm bot alembic upgrade head
```

Убедитесь в логах, что миграции применились без ошибок.

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
docker compose run --rm bot alembic upgrade head   # если есть новые миграции
docker compose up -d
```
