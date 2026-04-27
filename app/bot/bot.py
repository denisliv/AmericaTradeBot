import logging

import psycopg_pool
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.bot.handlers.admin import admin_router
from app.bot.handlers.assisted_selection import assisted_selection_router
from app.bot.handlers.consultation_request import consultation_request_router
from app.bot.handlers.llm_chat import llm_chat_router
from app.bot.handlers.others import others_router
from app.bot.handlers.self_selection import self_selection_router
from app.bot.handlers.subscriptions import subscriptions_router
from app.bot.handlers.users import user_router
from app.bot.middlewares.activity_tracker import ActivityTrackerMiddleware
from app.bot.middlewares.chat_action import ChatActionMiddleware
from app.bot.middlewares.database import DataBaseMiddleware
from app.bot.middlewares.limit_action import LimitActionMiddleware
from app.bot.middlewares.redis import RedisMiddleware
from app.bot.middlewares.shadow_ban import ShadowBanMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.scheduler import create_scheduler
from app.infrastructure.database.connection import get_pg_pool
from app.infrastructure.database.db import ensure_metrics_tables
from app.infrastructure.services.ai_manager.service import AIManagerService
from config.config import Config

logger = logging.getLogger(__name__)


# Функция конфигурирования и запуска бота
async def main(config: Config) -> None:
    logger.info("Starting bot...")
    # Инициализируем хранилище
    # Создаем Redis клиент для FSM storage
    redis_storage = Redis(
        db=config.redis.db,
        host=config.redis.host,
        port=config.redis.port,
        username=config.redis.username,
        password=config.redis.password,
    )

    storage = RedisStorage(redis=redis_storage)

    # Создаем отдельный Redis клиент для промо-рассылок
    redis = Redis(
        db=config.redis.promo_db,
        host=config.redis.host,
        port=config.redis.port,
        username=config.redis.username,
        password=config.redis.password,
    )

    # Инициализируем AI-менеджер
    ai_manager_service = AIManagerService(config)

    # Инициализируем бот и диспетчер
    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Создаём пул соединений с Postgres
    db_pool: psycopg_pool.AsyncConnectionPool = await get_pg_pool(
        db_name=config.db.db,
        host=config.db.host,
        port=config.db.port,
        user=config.db.user,
        password=config.db.password,
    )
    async with db_pool.connection() as conn:
        await ensure_metrics_tables(conn)

    # Создаем и настраиваем планировщик
    scheduler_manager = create_scheduler(config, bot, db_pool, redis)
    scheduler_manager.start()

    # Подключаем роутеры в нужном порядке
    logger.info("Including routers...")
    dp.include_routers(
        user_router,
        self_selection_router,
        assisted_selection_router,
        consultation_request_router,
        subscriptions_router,
        admin_router,
        llm_chat_router,
        others_router,
    )

    # Подключаем миддлвари в нужном порядке
    logger.info("Including middlewares...")
    dp.update.middleware(DataBaseMiddleware())
    dp.update.middleware(ShadowBanMiddleware())
    dp.update.middleware(RedisMiddleware(redis))
    dp.update.middleware(ActivityTrackerMiddleware())
    dp.callback_query.middleware(ChatActionMiddleware())
    dp.callback_query.middleware(LimitActionMiddleware(storage=storage))
    dp.message.middleware(
        ThrottlingMiddleware(storage=storage, admin_ids=config.bot.admin_ids)
    )

    # Регистрируем зависимости
    dp["ai_manager_service"] = ai_manager_service
    dp["config"] = config

    # Запускаем поллинг
    try:
        await dp.start_polling(bot, db_pool=db_pool, admin_ids=config.bot.admin_ids)
    except Exception as e:
        logger.exception(e)
    finally:
        # Останавливаем планировщик
        scheduler_manager.shutdown()
        # Закрываем пул соединений
        await db_pool.close()
        logger.info("Connection to Postgres closed")
