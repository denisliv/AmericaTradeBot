from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import FSInputFile
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.users import get_broadcast_recipients
from app.infrastructure.paths import POSTS_DIR, WEEKLY_POSTS_IMG_DIR
from app.infrastructure.services.safe_send import SendStatus, send_to_user_safely
from app.infrastructure.services.subscription_newsletter import NewsletterQueue

logger = logging.getLogger(__name__)
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


def weekly_post_image(post_path: Path) -> Optional[Path]:
    """Картинка поста: одноименный png в weekly_posts_img."""
    image = WEEKLY_POSTS_IMG_DIR / f"{post_path.stem}.png"
    if image.exists():
        return image
    logger.warning("Weekly post image not found: %s", image)
    return None


async def send_post_to_user(
    bot: Bot,
    conn: AsyncConnection,
    user_id: int,
    text: str,
    photo: FSInputFile | str | None,
) -> tuple[SendStatus, str, str | None]:
    """Отправляет пост (фото с подписью или текст).

    Returns:
        tuple: (статус, описание ошибки, file_id фото после успешной загрузки).
    """
    file_id: str | None = None

    async def _send() -> None:
        nonlocal file_id
        if photo is not None:
            message = await bot.send_photo(
                chat_id=user_id, photo=photo, caption=text, parse_mode=None
            )
            file_id = message.photo[-1].file_id
        else:
            await bot.send_message(chat_id=user_id, text=text, parse_mode=None)

    try:
        status, detail = await send_to_user_safely(_send, conn=conn, user_id=user_id)
        return status, detail, file_id
    except TelegramRetryAfter as e:
        logger.warning("Rate limited for user %s, waiting %ss", user_id, e.retry_after)
        await asyncio.sleep(e.retry_after)
        return SendStatus.ERROR, f"Rate limited, retry after {e.retry_after}s", None


async def send_weekly_posts_broadcast(bot: Bot, db_pool: AsyncConnectionPool) -> None:
    picked = pick_post_for_current_week()
    if not picked:
        return
    path, text = picked
    image = weekly_post_image(path)
    logger.info(
        "Starting weekly posts broadcast: file=%s, recipients pending query",
        path.name,
    )

    async with db_pool.connection() as conn:
        # Обновления is_alive при блокировках должны фиксироваться сразу
        await conn.set_autocommit(True)
        recipients = list(await get_broadcast_recipients(conn))

        if not recipients:
            logger.info("No recipients for weekly posts broadcast")
            return

        logger.info(
            "Weekly posts broadcast %s to %d users (%d chars)",
            path.name,
            len(recipients),
            len(text),
        )

        # Фото загружается на серверы Telegram один раз: первому получателю
        # уходит сам файл, остальным - полученный file_id
        photo: FSInputFile | str | None = FSInputFile(image) if image else None
        upload_attempts = 0
        requeue = []
        while (
            photo is not None
            and not isinstance(photo, str)
            and recipients
            and upload_attempts < 3
        ):
            first = recipients.pop(0)
            upload_attempts += 1
            status, error_msg, file_id = await send_post_to_user(
                bot, conn, first.user_id, text, photo
            )
            if status is SendStatus.OK and file_id:
                photo = file_id
            elif status is SendStatus.ERROR:
                # Получатель не получил пост - вернем его в общую очередь
                requeue.append(first)
                logger.warning(
                    "Weekly post photo upload failed for user %s: %s",
                    first.user_id,
                    error_msg,
                )
        if photo is not None and not isinstance(photo, str):
            logger.warning("Weekly post photo upload failed, sending text only")
            photo = None
        recipients = requeue + recipients

        queue = NewsletterQueue(
            max_retries=3,
            batch_size=20,
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
                    send_post_to_user(bot, conn, subscriber.user_id, text, photo)
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
                status, error_msg, _ = result
                if status is SendStatus.OK:
                    logger.debug("Post sent to user %s", subscriber.user_id)
                    continue
                if status is SendStatus.BLOCKED:
                    logger.warning(
                        "User %s blocked bot or deactivated", subscriber.user_id
                    )
                    continue
                await queue.add_retry(subscriber, retry_count)
                logger.warning(
                    "Failed posts broadcast to user %s: %s",
                    subscriber.user_id,
                    error_msg,
                )

            if not queue.is_empty():
                await asyncio.sleep(queue.delay_between_batches)

    logger.info("Weekly posts broadcast completed (%s)", path.name)
