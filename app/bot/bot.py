import asyncio
import logging
import signal
import sys

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
from app.infrastructure.services.ai_manager.service import AIManagerService
from config.config import Config

logger = logging.getLogger(__name__)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Регистрирует обработчики SIGINT/SIGTERM, чтобы корректно прерывать polling."""
    if sys.platform.startswith("win") or sys.platform == "cygwin":
        return
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            logger.debug("Signal %s not supported on this platform", sig)


# Функция конфигурирования и запуска бота
async def main(config: Config) -> None:
    logger.info("Starting bot...")
    # Создаем Redis клиент для FSM storage
    redis_storage_client = Redis(
        db=config.redis.db,
        host=config.redis.host,
        port=config.redis.port,
        username=config.redis.username,
        password=config.redis.password,
    )

    storage = RedisStorage(redis=redis_storage_client)

    # Отдельный Redis клиент для промо-логики (другая БД)
    redis = Redis(
        db=config.redis.promo_db,
        host=config.redis.host,
        port=config.redis.port,
        username=config.redis.username,
        password=config.redis.password,
    )

    # Инициализируем AI-менеджер (FAISS-индекс прогревается асинхронно)
    ai_manager_service = AIManagerService(config)
    await ai_manager_service.aensure_index()

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
        min_size=config.db.pool_min_size,
        max_size=config.db.pool_max_size,
    )
    # DDL schema управляется Alembic: `alembic upgrade head` перед запуском.

    # Создаем и настраиваем планировщик
    scheduler_manager = create_scheduler(
        config, bot, db_pool, redis, ai_manager_service=ai_manager_service
    )
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

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, db_pool=db_pool, admin_ids=config.bot.admin_ids)
    )
    stop_task = asyncio.create_task(stop_event.wait())

    try:
        done, _ = await asyncio.wait(
            {polling_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            logger.info("Stop signal received, shutting down...")
            await dp.stop_polling()
            await polling_task
        else:
            stop_task.cancel()
            if polling_task.exception() is not None:
                raise polling_task.exception()
    except Exception:
        logger.exception("Polling stopped with unhandled exception")
    finally:
        await scheduler_manager.shutdown()
        await db_pool.close()
        logger.info("Connection to Postgres closed")
        try:
            await redis.aclose()
        except Exception:
            logger.exception("Error closing promo Redis client")
        try:
            await redis_storage_client.aclose()
        except Exception:
            logger.exception("Error closing FSM Redis client")
        logger.info("Redis connections closed")
        await bot.session.close()
