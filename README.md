# AmericaTrade Telegram Bot

Telegram-бот для компании AmericaTrade, специализирующейся на подборе и покупке автомобилей из США. Бот предоставляет пользователям возможность подбирать автомобили по различным критериям, подписываться на уведомления о новых лотах и получать консультации от AI-ассистента.

## 🚀 Основные возможности

- **Подбор автомобилей**: Самостоятельный и ассистированный подбор по различным критериям
- **Подписки**: Уведомления о новых автомобилях по выбранным параметрам
- **AI-чат**: Интеграция с OpenAI для консультаций по автомобилям
- **Административные функции**: Управление пользователями и статистика
- **Промо-рассылки**: Автоматические уведомления и рекламные сообщения
- **Интеграция с аукционами**: Работа с данными Copart

## 🏗️ Архитектура проекта

```
AmericaTrade/
├── app/                          # Основное приложение
│   ├── bot/                      # Telegram бот
│   │   ├── handlers/             # Обработчики команд и сообщений
│   │   ├── middlewares/          # Промежуточное ПО
│   │   ├── keyboards/            # Клавиатуры
│   │   ├── states/               # FSM состояния
│   │   └── enums/                # Перечисления
│   ├── infrastructure/           # Инфраструктура
│   │   ├── database/             # Работа с БД
│   │   └── services/             # Бизнес-логика
│   └── lexicon/                  # Тексты и локализация
├── config/                       # Конфигурация
├── data/                         # Данные (CSV файлы)
├── migrations/                   # Миграции БД
└── main.py                       # Точка входа
```

## 🛠️ Технологический стек

- **Python 3.11+**
- **aiogram 3.x** - Telegram Bot API
- **PostgreSQL** - Основная база данных
- **Redis** - Кэширование и FSM storage
- **OpenAI API** - AI-ассистент
- **APScheduler** - Планировщик задач
- **psycopg** - PostgreSQL драйвер
- **langchain** - Работа с LLM

## 📋 Требования

- Python 3.11 или выше
- PostgreSQL 12+
- Redis 6+
- Telegram Bot Token
- OpenAI API Key

## ⚙️ Установка и настройка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd AmericaTrade
```

### 2. Создание виртуального окружения

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Скопируйте файл `env.example` в `.env` и заполните необходимые переменные:

```bash
cp env.example .env
```

Отредактируйте `.env` файл:

```env
# Bot Configuration
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_IDS=123456789,987654321

# Database Configuration (PostgreSQL)
POSTGRES_DB=america_trade
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password_here

# Redis Configuration
REDIS_DATABASE=0
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_USERNAME=
REDIS_PASSWORD=

# Copart Configuration
COPART_URL=https://www.copart.com

# OpenAI Configuration
API_KEY=your_openai_api_key_here
BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-3.5-turbo

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s
```

### 5. Настройка базы данных

Создайте базу данных PostgreSQL:

```sql
CREATE DATABASE america_trade;
```

Запустите миграции:

```bash
python migrations/create_tables.py
```

### 6. Запуск бота

```bash
python main.py
```

## 📊 Структура базы данных

### Основные таблицы:

- **users** - Пользователи бота
- **self_selection** - Самостоятельный подбор автомобилей
- **assisted_selection** - Ассистированный подбор
- **consultation_requests** - Заявки на консультацию
- **subscriptions** - Подписки пользователей
- **llm_chat_history** - История чатов с AI

## 🔧 Основные компоненты

### Handlers (Обработчики)

- **users.py** - Основные команды пользователей
- **self_selection.py** - Самостоятельный подбор автомобилей
- **assisted_selection.py** - Ассистированный подбор
- **subscriptions.py** - Управление подписками
- **llm_chat.py** - Чат с AI-ассистентом
- **admin.py** - Административные функции
- **consultation_request.py** - Заявки на консультацию

### Middlewares (Промежуточное ПО)

- **database.py** - Подключение к БД
- **redis.py** - Работа с Redis
- **throttling.py** - Ограничение частоты запросов
- **shadow_ban.py** - Теневая блокировка
- **activity_tracker.py** - Отслеживание активности
- **limit_action.py** - Ограничения действий

### Services (Сервисы)

- **llm_service.py** - Интеграция с OpenAI
- **promo_newsletter.py** - Промо-рассылки
- **subscription_newsletter.py** - Рассылки по подпискам
- **utils.py** - Утилиты (загрузка CSV, работа с данными)

## 🤖 Команды бота

- `/start` - Запуск бота и приветствие
- `/help` - Справка по работе с ботом
- `/subscription` - Управление подписками
- `/chat` - Чат с AI-ассистентом
- `/statistics` - Статистика (только для админов)
- `/ban` - Заблокировать пользователя (только для админов)
- `/unban` - Разблокировать пользователя (только для админов)

## 📱 Функциональность

### Подбор автомобилей

1. **Самостоятельный подбор**:
   - Выбор марки и модели
   - Год выпуска
   - Пробег
   - Статус аукциона

2. **Ассистированный подбор**:
   - Тип кузова
   - Бюджет
   - Автоматический подбор подходящих вариантов

### Подписки

- Подписка на конкретные марки/модели
- Уведомления о новых лотах
- Управление подписками через интерфейс

### AI-ассистент

- Консультации по автомобилям из США
- Информация о процессе покупки и доставки
- Ответы на вопросы о компании

## 🔄 Планировщик задач

Бот использует APScheduler для автоматических задач:

- **Загрузка CSV данных** - Обновление данных об автомобилях
- **Ежедневная рассылка** - Уведомления подписчикам
- **Промо-рассылки** - Рекламные сообщения

## 🛡️ Безопасность

- Теневая блокировка пользователей
- Ограничение частоты запросов
- Валидация входных данных
- Логирование всех действий

## 📈 Мониторинг и логирование

- Подробное логирование всех операций
- Отслеживание активности пользователей
- Статистика использования бота
- Мониторинг ошибок

## 🚀 Развертывание

### Docker (рекомендуется)

```bash
# Создание образа
docker build -t americatrade-bot .

# Запуск контейнера
docker run -d --name americatrade-bot --env-file .env americatrade-bot
```

### Системный сервис

Создайте systemd сервис для автоматического запуска:

```ini
[Unit]
Description=AmericaTrade Telegram Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/AmericaTrade
ExecStart=/path/to/AmericaTrade/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 🤝 Разработка

### Структура кода

- **Чистая архитектура** - Разделение на слои
- **Dependency Injection** - Внедрение зависимостей
- **Type Hints** - Типизация для лучшей читаемости
- **Async/Await** - Асинхронное программирование

### Добавление новых функций

1. Создайте новый handler в `app/bot/handlers/`
2. Добавьте роутер в `app/bot/bot.py`
3. Обновите клавиатуры в `app/bot/keyboards/`
4. Добавьте тексты в `app/lexicon/lexicon_ru.py`

## 📝 Лицензия

Этот проект является собственностью компании AmericaTrade.

## 📞 Поддержка

Для получения поддержки обращайтесь:
- Email: info@americatrade.by
- Telegram: @americatradeby
- Телефон: +375 44 723-24-25

## 🔄 Обновления

Следите за обновлениями в репозитории. Перед обновлением:
1. Сделайте резервную копию базы данных
2. Остановите бота
3. Обновите код
4. Запустите миграции (если есть)
5. Перезапустите бота

---

**AmericaTrade** - Ваш надежный партнер в покупке автомобилей из США! 🇺🇸🚗
