import logging
from typing import Optional

import redis.asyncio as redis
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.services.promo_newsletter import start_promo_listener
from app.infrastructure.services.subscription_newsletter import send_daily_newsletter
from app.infrastructure.services.utils import download_csv

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Менеджер для управления задачами AsyncIOScheduler"""

    def __init__(self, timezone: str = "Europe/Moscow"):
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self._is_started = False
        self._bot: Optional[Bot] = None
        self._db_pool: Optional[AsyncConnectionPool] = None
        self._redis_client: Optional[redis.Redis] = None

    def add_download_csv_job(self, url: str, interval_minutes: int = 60) -> None:
        """Добавляет задачу загрузки CSV файла"""
        self.scheduler.add_job(
            download_csv,
            trigger="interval",
            minutes=interval_minutes,
            kwargs={"url": url},
            id="download_csv",
            name="Download CSV data",
            replace_existing=True,
        )
        logger.info(f"Added download_csv job with interval {interval_minutes} minutes")

    def add_daily_newsletter_job(self, hour: int = 9, minute: int = 0) -> None:
        """Добавляет задачу ежедневной рассылки сообщений по подписке"""
        self.scheduler.add_job(
            self._newsletter_wrapper,
            trigger="cron",
            hour=hour,
            minute=minute,
            id="daily_newsletter",
            name="Daily newsletter to subscribers",
            replace_existing=True,
        )
        logger.info(f"Added daily newsletter job at {hour:02d}:{minute:02d}")

    def start_promo_listener(self) -> None:
        """Запускает слушатель Redis для промо-рассылок"""
        if self._bot is None or self._db_pool is None or self._redis_client is None:
            logger.error(
                "Bot, database pool or Redis client not set for promo listener"
            )
            return

        # Запускаем слушатель в фоновой задаче
        import asyncio

        asyncio.create_task(
            start_promo_listener(self._bot, self._db_pool, self._redis_client)
        )
        logger.info("Started Redis promo listener")

    async def _newsletter_wrapper(self) -> None:
        """Обертка для функции рассылки с передачей бота и пула соединений"""
        if self._bot is None or self._db_pool is None:
            logger.error("Bot or database pool not set for newsletter task")
            return

        await send_daily_newsletter(self._bot, self._db_pool)

    def start(self) -> None:
        """Запускает планировщик и слушатель промо-рассылок"""
        if not self._is_started:
            self.scheduler.start()
            self._is_started = True
            logger.info("Scheduler started")

            # Запускаем слушатель промо-рассылок
            self.start_promo_listener()

    def shutdown(self) -> None:
        """Останавливает планировщик"""
        if self._is_started:
            self.scheduler.shutdown()
            self._is_started = False
            logger.info("Scheduler shutdown")

    def get_jobs(self) -> list:
        """Возвращает список активных задач"""
        return self.scheduler.get_jobs()


def create_scheduler(
    config, bot: Bot, db_pool: AsyncConnectionPool, redis_client: redis.Redis
) -> SchedulerManager:
    """Создает и настраивает планировщик с задачами"""
    scheduler_manager = SchedulerManager()

    # Устанавливаем бота, пул соединений и Redis клиент
    scheduler_manager._bot = bot
    scheduler_manager._db_pool = db_pool
    scheduler_manager._redis_client = redis_client
    logger.info("Bot, database pool and Redis client set for scheduler tasks")

    # Добавляем задачу загрузки CSV
    scheduler_manager.add_download_csv_job(url=config.copart.url, interval_minutes=60)

    # Добавляем задачу ежедневной рассылки
    scheduler_manager.add_daily_newsletter_job(hour=9, minute=20)

    # Промо-рассылка теперь обрабатывается через Redis Keyspace Notifications
    # и запускается автоматически при истечении TTL

    return scheduler_manager
