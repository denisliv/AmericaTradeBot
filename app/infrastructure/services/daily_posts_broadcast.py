from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.db import (
    get_broadcast_recipients,
    record_delivery_metric_with_pool,
)
from app.infrastructure.services.subscription_newsletter import NewsletterQueue

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
POSTS_DIR = _PROJECT_ROOT / "data" / "posts"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def list_post_files() -> list[Path]:
    return sorted(p for p in POSTS_DIR.glob("post_*.txt") if p.is_file())


def pick_post_for_current_week() -> Optional[tuple[Path, str]]:
    files = list_post_files()
    if not files:
        logger.warning("No post_*.txt files in %s", POSTS_DIR)
        return None
    moscow_date = datetime.now(MOSCOW_TZ).date()
    y, w, _ = moscow_date.isocalendar()
    # Уникальный индекс календарной недели, цикл по списку файлов
    idx = (y * 100 + w) % len(files)
    path = files[idx]
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.warning("Empty post file: %s", path.name)
        return None
    return path, text


async def send_post_to_user(bot: Bot, user_id: int, text: str) -> tuple[bool, str]:
    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode=None)
        return True, ""
    except TelegramRetryAfter as e:
        wait_time = e.retry_after
        logger.warning("Rate limited for user %s, waiting %ss", user_id, wait_time)
        await asyncio.sleep(wait_time)
        return False, f"Rate limited, retry after {wait_time}s"
    except TelegramBadRequest as e:
        error_msg = str(e)
        if "chat not found" in error_msg or "bot was blocked" in error_msg:
            return False, "User blocked bot"
        if "user is deactivated" in error_msg:
            return False, "User deactivated"
        return False, f"Bad request: {error_msg}"
    except Exception as e:
        return False, f"Unexpected error: {e!s}"


async def send_weekly_posts_broadcast(bot: Bot, db_pool: AsyncConnectionPool) -> None:
    picked = pick_post_for_current_week()
    if not picked:
        return
    path, text = picked
    logger.info(
        "Starting weekly posts broadcast: file=%s, recipients pending query",
        path.name,
    )

    async with db_pool.connection() as conn:
        recipients = await get_broadcast_recipients(conn)

    if not recipients:
        logger.info("No recipients for weekly posts broadcast")
        return

    logger.info(
        "Weekly posts broadcast %s to %d users (%d chars)",
        path.name,
        len(recipients),
        len(text),
    )

    queue = NewsletterQueue(
        max_retries=3,
        batch_size=30,
        delay_between_batches=1.0,
    )
    for row in recipients:
        await queue.add_subscriber(row)

    while not queue.is_empty():
        batch = await queue.get_batch()
        if not batch:
            break

        logger.info("Posts broadcast batch: %d users", len(batch))
        results = await asyncio.gather(
            *(
                send_post_to_user(bot, subscriber.user_id, text)
                for subscriber, _ in batch
            ),
            return_exceptions=True,
        )
        for (subscriber, retry_count), result in zip(batch, results, strict=True):
            if isinstance(result, Exception):
                await queue.add_retry(subscriber, retry_count)
                logger.warning(
                    "Unexpected exception in posts broadcast for user %s: %s",
                    subscriber.user_id,
                    result,
                )
                continue
            success, error_msg = result
            if success:
                logger.debug("Post sent to user %s", subscriber.user_id)
                await record_delivery_metric_with_pool(
                    db_pool,
                    category="daily_posts",
                    status="sent",
                    user_id=subscriber.user_id,
                )
                continue
            if "blocked" in error_msg or "deactivated" in error_msg:
                logger.warning("User %s blocked bot or deactivated", subscriber.user_id)
                await record_delivery_metric_with_pool(
                    db_pool,
                    category="daily_posts",
                    status="blocked" if "blocked" in error_msg else "deactivated",
                    user_id=subscriber.user_id,
                    error_text=error_msg,
                )
                continue
            await queue.add_retry(subscriber, retry_count)
            await record_delivery_metric_with_pool(
                db_pool,
                category="daily_posts",
                status="failed",
                user_id=subscriber.user_id,
                error_text=error_msg,
            )
            logger.warning(
                "Failed posts broadcast to user %s: %s",
                subscriber.user_id,
                error_msg,
            )

        if not queue.is_empty():
            await asyncio.sleep(queue.delay_between_batches)

    logger.info("Weekly posts broadcast completed (%s)", path.name)
