import asyncio
import logging
import uuid
from typing import Optional

import redis.asyncio as redis
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.services.promo_newsletter import start_promo_listener
from app.infrastructure.services.daily_posts_broadcast import send_weekly_posts_broadcast
from app.infrastructure.services.subscription_newsletter import send_daily_newsletter
from app.infrastructure.services.utils import download_csv

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Менеджер для управления задачами AsyncIOScheduler"""

    def __init__(self, timezone: str = "Europe/Moscow"):
        self.scheduler = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                "misfire_grace_time": 300,
                "coalesce": True,
                "max_instances": 1,
            },
        )
        self._is_started = False
        self._bot: Optional[Bot] = None
        self._db_pool: Optional[AsyncConnectionPool] = None
        self._redis_client: Optional[redis.Redis] = None
        self._promo_listener_task: Optional[asyncio.Task] = None
        self._promo_stop_event = asyncio.Event()

    async def _run_with_lock(
        self,
        lock_key: str,
        coro,
        lock_ttl_seconds: int = 1800,
    ) -> None:
        if self._redis_client is None:
            await coro
            return
        lock_value = str(uuid.uuid4())
        acquired = await self._redis_client.set(
            lock_key,
            lock_value,
            ex=lock_ttl_seconds,
            nx=True,
        )
        if not acquired:
            close_method = getattr(coro, "close", None)
            if callable(close_method):
                close_method()
            logger.info("Skip job, lock already acquired: %s", lock_key)
            return
        try:
            await coro
        finally:
            current_value = await self._redis_client.get(lock_key)
            if isinstance(current_value, bytes):
                current_value = current_value.decode("utf-8")
            if current_value and current_value == lock_value:
                await self._redis_client.delete(lock_key)

    def add_download_csv_job(self, url: str, interval_minutes: int = 60) -> None:
        """Добавляет задачу загрузки CSV файла"""
        self.scheduler.add_job(
            self._download_csv_wrapper,
            trigger="interval",
            minutes=interval_minutes,
            args=[url],
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

    def add_weekly_posts_broadcast_job(
        self,
        hour: int = 19,
        minute: int = 0,
        day_of_week: str = "wed",
    ) -> None:
        """Рассылка одного поста из data/posts раз в неделю (по умолчанию среда), всем is_alive / не banned."""
        self.scheduler.add_job(
            self._weekly_posts_broadcast_wrapper,
            trigger="cron",
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            id="weekly_posts_broadcast",
            name="Weekly posts broadcast to all users",
            replace_existing=True,
        )
        logger.info(
            "Added weekly posts broadcast: %s at %02d:%02d",
            day_of_week,
            hour,
            minute,
        )

    def start_promo_listener(self) -> None:
        """Запускает слушатель Redis для промо-рассылок"""
        if self._bot is None or self._db_pool is None or self._redis_client is None:
            logger.error(
                "Bot, database pool or Redis client not set for promo listener"
            )
            return

        if self._promo_listener_task and not self._promo_listener_task.done():
            logger.info("Promo listener already running")
            return

        async def _listener_supervisor() -> None:
            while not self._promo_stop_event.is_set():
                try:
                    await start_promo_listener(
                        self._bot, self._db_pool, self._redis_client
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("Promo listener crashed: %s", e)
                    try:
                        await asyncio.wait_for(self._promo_stop_event.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
                else:
                    try:
                        await asyncio.wait_for(self._promo_stop_event.wait(), timeout=1)
                    except asyncio.TimeoutError:
                        pass

        self._promo_stop_event.clear()
        self._promo_listener_task = asyncio.create_task(_listener_supervisor())
        logger.info("Started Redis promo listener")

    async def _newsletter_wrapper(self) -> None:
        """Обертка для функции рассылки с передачей бота и пула соединений"""
        if self._bot is None or self._db_pool is None:
            logger.error("Bot or database pool not set for newsletter task")
            return

        await self._run_with_lock(
            "lock:daily_newsletter",
            send_daily_newsletter(self._bot, self._db_pool),
            lock_ttl_seconds=7200,
        )

    async def _download_csv_wrapper(self, url: str) -> None:
        await self._run_with_lock(
            "lock:download_csv",
            download_csv(url),
            lock_ttl_seconds=3600,
        )

    async def _weekly_posts_broadcast_wrapper(self) -> None:
        if self._bot is None or self._db_pool is None:
            logger.error("Bot or database pool not set for weekly posts broadcast")
            return
        await self._run_with_lock(
            "lock:weekly_posts_broadcast",
            send_weekly_posts_broadcast(self._bot, self._db_pool),
            lock_ttl_seconds=7200,
        )

    def start(self) -> None:
        """Запускает планировщик и слушатель промо-рассылок"""
        if not self._is_started:
            self.scheduler.start()
            self._is_started = True
            logger.info("Scheduler started")

            # Запускаем слушатель промо-рассылок
            self.start_promo_listener()

    async def shutdown(self) -> None:
        """Останавливает планировщик и фоновый promo-listener корректно."""
        if self._is_started:
            self.scheduler.shutdown()
            self._is_started = False
            logger.info("Scheduler shutdown")
        self._promo_stop_event.set()
        if self._promo_listener_task and not self._promo_listener_task.done():
            self._promo_listener_task.cancel()
            try:
                await self._promo_listener_task
            except (asyncio.CancelledError, Exception) as exc:
                if not isinstance(exc, asyncio.CancelledError):
                    logger.exception("Promo listener shutdown error: %s", exc)
        self._promo_listener_task = None

    def get_jobs(self) -> list:
        """Возвращает список активных задач"""
        return self.scheduler.get_jobs()


def create_scheduler(
    config,
    bot: Bot,
    db_pool: AsyncConnectionPool,
    redis_client: redis.Redis,
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

    # Еженедельная контент-рассылка (посты из data/posts) — среда 19:00 по Москве
    scheduler_manager.add_weekly_posts_broadcast_job(
        hour=19, minute=0, day_of_week="wed"
    )

    # Промо-рассылка теперь обрабатывается через Redis Keyspace Notifications
    # и запускается автоматически при истечении TTL

    return scheduler_manager
