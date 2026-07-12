# AmericaTrade Telegram Bot

Telegram-бот компании AmericaTrade (подбор и доставка автомобилей из США в Беларусь).
Бот ведёт клиента по сценарию: подбор авто по критериям,
информационные разделы, захват контакта с отправкой лида в Bitrix24, подписки на
новые лоты и многошаговая прогревочная рассылка.

## Возможности

**Пользовательская часть** (`/start` → главное меню из 4 кнопок):

- **✅ Подобрать авто из США**
  - *по марке/модели*: марка → модель → год → статус аукциона → до 10 реальных лотов
    из CSV Copart (фото, характеристики, предварительная цена BUY NOW) с кнопкой
    расчёта по каждому авто; «до 2016» и «Другое» (свободный запрос) ведут сразу
    на консультацию;
  - *помощь в выборе*: тип кузова → бюджет → ТОП-3 примера из локальной галереи
    с кнопками расчёта.
- **🤔 Все об авто из США** — инфо-хаб: 5 разделов (выгода, процесс покупки,
  аукционы, цена, почему AmericaTrade), в каждом CTA заявки.
- **⭐ Почему именно AmericaTrade?** — раздел с кнопками отзывов Яндекс/Google.
- **🙎‍♂️ Помощь и контакты** — логотип, реквизиты, сайт, отзывы.
- **Заявка (единый флоу)**: CTA → экран «🎯 Отлично!…» → «📞 Отправить мой номер»
  (reply-кнопка, контакт в одно нажатие) → лид в Bitrix24 → «✅ Контакт получен!».
  В заголовок лида идёт тип запроса (`Консультация` / `Заявка` / `По рассылке`),
  в комментарий — выбранные критерии (марка/модель/год, кузов/бюджет, лот, текст запроса).
- **Подписки** (`/subscription` или «🔔 Следить за вариантами по модели») — до 6
  подписок на критерии поиска, ежедневная авторассылка новых вариантов.

**Рассылки** (все — через общий безопасный отправитель с лимитами и авточисткой
заблокировавших):

- **Прогревочная цепочка** (8 шагов от регистрации, состояние в БД):
  +60 минут и далее ежедневно в 19:00 — контент-посты с картинками, подборки
  случайного кроссовера и седана из CSV, приглашения в
  Telegram/Instagram/TikTok (повторяются каждые 30 дней). Оставленная заявка
  сдвигает оставшиеся шаги на +3 дня.
- **Еженедельные посты** — каждое воскресенье в 19:00 по одному посту
  (картинка + текст-подпись) из `data/posts`, циклично по кругу (12 тем).
- **Подписочная** — ежедневно (по умолчанию 09:20) новые лоты подписчикам.
- **Админ-рассылка** — вручную из админки: текст / фото / альбом + кнопка-ссылка,
  превью, подтверждение, прогресс, per-user статусы доставки.

**Админка** (`/admin`, только для `ADMIN_IDS`): KPI-статистика, создание рассылки,
бан/разбан по id или @username (shadow-ban — молчаливый игнор).

## Технологический стек

- **Python 3.13+**, зависимости — **[uv](https://docs.astral.sh/uv/)**
- **aiogram 3.x** — Telegram Bot API (long polling)
- **PostgreSQL 16** — состояние пользователей, заявки, подписки, прогрев (psycopg 3 + пул)
- **Redis 7** — FSM-хранилище (db 0) и распределённые локи планировщика (db 1)
- **APScheduler** — фоновые задачи
- **Alembic** — миграции схемы (единая init-миграция, применяется автоматически при старте)
- **Docker / Docker Compose** — деплой полного стека

## Архитектура проекта

```
AmericaTrade/
├── app/
│   ├── bot/                      # Telegram-слой
│   │   ├── handlers/             # Хендлеры: users, self_selection, assisted_selection,
│   │   │                         #   consultation_request, subscriptions, admin_mailing, others
│   │   ├── keyboards/            # Инлайн/reply-клавиатуры
│   │   ├── middlewares/          # БД, shadow-ban, активность, троттлинг, лимиты действий
│   │   ├── states/               # FSM-состояния
│   │   └── scheduler.py          # Задачи APScheduler
│   ├── infrastructure/
│   │   ├── database/             # SQL-запросы (users, selections, nurture, admin_mailing)
│   │   ├── services/             # nurture, weekly posts, подписочная и админ-рассылки,
│   │   │                         #   safe_send, salesdata (CSV Copart), bitrix, галерея
│   │   └── paths.py              # Пути к данным
│   ├── lexicon/lexicon_ru.py     # ВСЕ тексты и подписи кнопок бота
│   └── config.py                 # Загрузка настроек из .env
├── data/                         # Контент и runtime-данные — НЕ в git (см. ниже)
├── alembic/versions/0001_...py   # Единственная init-миграция (актуальная схема)
├── scripts/                      # Скрипты проверки рассылок без ожидания расписания
├── tests/                        # Pytest (~95 тестов: тексты, клавиатуры, расписания, лимиты)
├── main.py                       # Точка входа
├── Dockerfile / docker-compose.yml
└── env.example                   # Шаблон .env со всеми переменными
```

## Что переносится на сервер ОТДЕЛЬНО (не через GitHub)

В git хранится только код. Секреты и контент нужно доставить на сервер вручную
(scp/rsync) при первом развёртывании:

| Что | Куда на сервере | Зачем |
|---|---|---|
| `.env` | корень проекта | токены и пароли (шаблон — `env.example`) |
| `data/logo/logo.jpg` | `data/logo/` | фото в разделе «Помощь и контакты» |
| `data/warm_up_posts_img/*.png` (8 шт.) | `data/warm_up_posts_img/` | картинки постов прогрева (`why_americatrade`, `top_myths`, `top_suv`, `top_sedan`, `thinking`, `join_telegram`, `join_instagram`, `join_tiktok`) |
| `data/weekly_posts_img/*.png` (12 шт.) | `data/weekly_posts_img/` | картинки еженедельных постов (имена = имена постов) |
| `data/posts/post_*.txt` (12 шт.) | `data/posts/` | тексты еженедельных постов (≤1024 символов — уходят подписью к фото) |
| `data/about_america_trade/*.png` (6 шт.) | `data/about_america_trade/` | картинки хаба «Все об авто из США» (`hub`, `why_profitable`, `purchasing_process`, `auctions`, `price_breakdown`, `why_americatrade`) |
| `data/assisted_gallery/**` | `data/assisted_gallery/` | галерея примеров: `<кузов>/<бюджет>/<марка_модель>/*.jpg` (sedan/suv/electric × 6 бюджетов) |

`data/salesdata.csv` переносить не обязательно — бот скачивает его сам по расписанию,
но **первый час после чистого запуска** поиск по CSV будет пустым. Чтобы этого
избежать, скопируйте свежий `salesdata.csv` в `data/` вместе с остальным контентом.

Пример переноса одним архивом:

```bash
# локально
tar czf content.tar.gz .env data/
scp content.tar.gz user@server:~/AmericaTrade/
# на сервере
cd ~/AmericaTrade && tar xzf content.tar.gz && rm content.tar.gz
```

Если какого-то файла контента нет, бот не падает: пишет предупреждение в лог и
отправляет пост/экран без картинки (или текст «нет примеров» для галереи).

## Переменные окружения

Полный шаблон с комментариями — `env.example`. Ключевые:

| Переменная | Значение |
|---|---|
| `BOT_TOKEN` | токен бота от @BotFather |
| `ADMIN_IDS` | Telegram id админов через запятую (им доступен `/admin`) |
| `POSTGRES_DB/HOST/PORT/USER/PASSWORD` | доступ к PostgreSQL (для Docker host = `postgres`) |
| `POSTGRES_POOL_MIN_SIZE/MAX_SIZE` | размер пула соединений (5/20 по умолчанию) |
| `REDIS_HOST/PORT/USERNAME/PASSWORD` | доступ к Redis (для Docker host = `redis`, пароль пустой) |
| `REDIS_DATABASE` | БД Redis для FSM (0) |
| `REDIS_PROMO_DATABASE` | БД Redis для локов планировщика (1) |
| `COPART_URL` | URL CSV-выгрузки лотов Copart |
| `BITRIX_WEBHOOK_URL` | вебхук Bitrix24 для лидов (`crm.lead.add`) |
| `SCHEDULER_TIMEZONE` | таймзона расписаний (по умолчанию `Europe/Moscow`) |
| `SCHEDULER_CSV_INTERVAL_MINUTES` | период обновления CSV (60) |
| `SCHEDULER_NEWSLETTER_HOUR/MINUTE` | время подписочной рассылки (09:20) |
| `SCHEDULER_POSTS_DAY_OF_WEEK/HOUR/MINUTE` | еженедельные посты (`sun` 19:00) |
| `LOG_LEVEL`, `LOG_FORMAT` | логирование |

Время прогревочной цепочки задано константой в
`app/infrastructure/services/nurture.py` (`SEND_HOUR = 19`).

## Развёртывание на сервере (Docker)

Предполагается Linux-сервер, пользователь в группе `docker`. Для long polling
входящие подключения не нужны — только исходящий HTTPS.

```bash
# 1. Docker Engine + Compose v2 (см. https://docs.docker.com/engine/install/)
docker --version && docker compose version

# 2. Код
git clone <URL-репозитория> AmericaTrade && cd AmericaTrade

# 3. Секреты и контент (см. раздел «Что переносится отдельно»)
#    .env + data/ должны оказаться в корне проекта до сборки:
#    контент data/ попадает внутрь образа при docker compose build

# 4. Запуск
docker compose build
docker compose up -d

# 5. Проверка
docker compose logs -f bot
```

Миграции Alembic применяются автоматически при старте сервиса `bot`
(`alembic upgrade head && python main.py` в `docker-compose.yml`); на актуальной
схеме это мгновенный no-op. В логах не должно быть ошибок миграций и подключения
к Postgres/Redis.

Сервисы: **postgres** (том `postgres_data`), **redis** (том `redis_data`, AOF),
**bot**. Порты БД наружу не пробрасываются.

**Обновление версии кода:**

```bash
git pull
docker compose build     # контент data/ и .env не трогаются, но попадают в новый образ
docker compose up -d     # новые миграции применятся автоматически
```

**Обновление контента** (посты, картинки): скопируйте новые файлы в `data/` и
пересоберите образ (`docker compose build && docker compose up -d`) — контент
запекается в образ при сборке.

## Локальная разработка (без Docker)

Нужны: Python 3.13+, PostgreSQL, Redis, uv.

```bash
uv sync --dev                      # зависимости
cp env.example .env                # заполнить токены/пароли (host = localhost)
# создать БД: CREATE DATABASE america_trade;
uv run alembic upgrade head        # миграции
uv run python main.py              # запуск
uv run pytest                      # тесты
uv run ruff check app tests scripts   # линтер
```

## Проверка рассылок без ожидания расписания

Скрипты шлют сообщения напрямую и не конфликтуют с работающим ботом
(получатель должен хотя бы раз нажать `/start`):

```bash
# Прогревочная цепочка: все 8 шагов или выборочно
docker compose exec bot python scripts/preview_nurture.py <telegram_user_id>
docker compose exec bot python scripts/preview_nurture.py <telegram_user_id> --steps 3,4

# Шаги: 1 — почему AT, 2 — мифы, 3 — ТОП кроссоверов, 4 — ТОП седанов,
# 5 — «пока вы думаете», 6-8 — Telegram/Instagram/TikTok

# Еженедельные посты: все 12 / выборочно / пост текущей недели
docker compose exec bot python scripts/preview_weekly_posts.py <telegram_user_id>
docker compose exec bot python scripts/preview_weekly_posts.py <telegram_user_id> --posts 3,5
docker compose exec bot python scripts/preview_weekly_posts.py <telegram_user_id> --current
```

Проверка расписания прогрева end-to-end — «машина времени» (после этого
планировщик шлёт по одному назревшему шагу каждые 10 минут):

```bash
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c \
  "UPDATE nurture_state SET started_at = NOW() - interval '50 days', last_step = 0 WHERE user_id = <id>;"
```

Сдвиг после заявки: оставить заявку в боте и убедиться, что
`SELECT shift_days FROM nurture_state WHERE user_id = <id>;` вернул 3.

Локально (без Docker) те же скрипты запускаются как
`uv run python scripts/preview_nurture.py …`.

## Фоновые задачи (APScheduler)

| Задача | Расписание | Что делает |
|---|---|---|
| `download_csv` | каждые 60 мин | скачивает и валидирует CSV Copart, обновляет кэш |
| `nurture_chain` | каждые 10 мин | шлёт назревшие шаги прогрева (≤1 шаг на пользователя за прогон) |
| `daily_newsletter` | ежедневно 09:20 | новые лоты подписчикам |
| `weekly_posts_broadcast` | вс 19:00 | еженедельный пост с картинкой всем живым пользователям |

Все задачи выполняются под Redis-локами — безопасно при нескольких инстансах.

## База данных

Схема — в единственной миграции `alembic/versions/0001_initial_schema.py`:

- **users** — пользователи (роль, is_alive, banned, счётчик подписок)
- **self_selection_requests** — поиски по марке/модели (+ флаг подписки)
- **assisted_selection_requests** — запросы «помощь в выборе»
- **nurture_state** — состояние прогревочной цепочки (старт, сдвиг, последний шаг)

Временная таблица **admin_mailing** создаётся и удаляется в рантайме на время
каждой админ-рассылки (per-user статусы доставки).

## Лимиты и защита

- Кулдаун сообщений 2 сек (предупреждение один раз за окно), админы исключены.
- 100 «тяжёлых» действий в час на пользователя (входы в подбор, «Подобрать еще»).
- Подписки: максимум 6 на пользователя, атомарно (`FOR UPDATE`).
- Исходящий темп рассылок 5–20 сообщений/сек с обработкой flood-limit;
  заблокировавшие бота автоматически помечаются `is_alive=false` во всех рассылках.
- Shadow-ban: забаненные пользователи молча игнорируются.
