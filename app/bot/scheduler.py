import logging
import uuid

import redis.asyncio as redis
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from psycopg_pool import AsyncConnectionPool

from app.config import Config
from app.infrastructure.services.daily_posts_broadcast import (
    send_weekly_posts_broadcast,
)
from app.infrastructure.services.nurture import send_due_nurture_messages
from app.infrastructure.services.salesdata import download_csv
from app.infrastructure.services.subscription_newsletter import send_daily_newsletter

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Менеджер для управления задачами AsyncIOScheduler"""

    def __init__(
        self,
        bot: Bot,
        db_pool: AsyncConnectionPool,
        redis_client: redis.Redis,
        timezone: str = "Europe/Moscow",
    ):
        self.scheduler = AsyncIOScheduler(
            timezone=timezone,
            job_defaults={
                "misfire_grace_time": 300,
                "coalesce": True,
                "max_instances": 1,
            },
        )
        self._is_started = False
        self._bot = bot
        self._db_pool = db_pool
        self._redis_client = redis_client
        self._timezone = timezone

    async def _run_with_lock(
        self,
        lock_key: str,
        coro,
        lock_ttl_seconds: int = 1800,
    ) -> None:
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

    def add_nurture_job(self, interval_minutes: int = 10) -> None:
        """Добавляет задачу отправки шагов прогревочной цепочки."""
        self.scheduler.add_job(
            self._nurture_wrapper,
            trigger="interval",
            minutes=interval_minutes,
            id="nurture_chain",
            name="Nurture chain messages",
            replace_existing=True,
        )
        logger.info("Added nurture chain job with interval %d minutes", interval_minutes)

    async def _nurture_wrapper(self) -> None:
        await self._run_with_lock(
            "lock:nurture_chain",
            send_due_nurture_messages(self._bot, self._db_pool, self._timezone),
            lock_ttl_seconds=600,
        )

    async def _newsletter_wrapper(self) -> None:
        """Обертка для функции рассылки с передачей бота и пула соединений"""
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
        await self._run_with_lock(
            "lock:weekly_posts_broadcast",
            send_weekly_posts_broadcast(self._bot, self._db_pool),
            lock_ttl_seconds=7200,
        )

    def start(self) -> None:
        """Запускает планировщик"""
        if not self._is_started:
            self.scheduler.start()
            self._is_started = True
            logger.info("Scheduler started")

    async def shutdown(self) -> None:
        """Останавливает планировщик корректно."""
        if self._is_started:
            self.scheduler.shutdown()
            self._is_started = False
            logger.info("Scheduler shutdown")

    def get_jobs(self) -> list:
        """Возвращает список активных задач"""
        return self.scheduler.get_jobs()


def create_scheduler(
    config: Config,
    bot: Bot,
    db_pool: AsyncConnectionPool,
    redis_client: redis.Redis,
) -> SchedulerManager:
    """Создает и настраивает планировщик с задачами по расписанию из конфига"""
    schedule = config.scheduler
    scheduler_manager = SchedulerManager(
        bot=bot,
        db_pool=db_pool,
        redis_client=redis_client,
        timezone=schedule.timezone,
    )

    # Добавляем задачу загрузки CSV
    scheduler_manager.add_download_csv_job(
        url=config.copart.url,
        interval_minutes=schedule.csv_interval_minutes,
    )

    # Добавляем задачу ежедневной рассылки
    scheduler_manager.add_daily_newsletter_job(
        hour=schedule.newsletter_hour,
        minute=schedule.newsletter_minute,
    )

    # Еженедельная контент-рассылка (посты из data/posts)
    scheduler_manager.add_weekly_posts_broadcast_job(
        hour=schedule.posts_hour,
        minute=schedule.posts_minute,
        day_of_week=schedule.posts_day_of_week,
    )

    # Прогревочная цепочка сообщений (график в services/nurture.py)
    scheduler_manager.add_nurture_job()

    return scheduler_manager
