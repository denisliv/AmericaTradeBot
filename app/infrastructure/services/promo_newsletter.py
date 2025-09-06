import asyncio
import logging

import redis.asyncio as redis
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from psycopg_pool import AsyncConnectionPool

from app.lexicon.lexicon_ru import LEXICON_PROMO_RU

logger = logging.getLogger(__name__)


async def start_promo_listener(
    bot: Bot, db_pool: AsyncConnectionPool, redis_client: redis.Redis
) -> None:
    """
    Запускает слушатель Redis Keyspace Notifications для отслеживания истечения TTL
    """
    logger.info("Starting Redis keyspace notifications listener for promo messages")

    try:
        # Включаем уведомления об истечении ключей
        await redis_client.config_set("notify-keyspace-events", "Ex")

        # Подписываемся на события истечения ключей в базе данных промо-рассылок
        pubsub = redis_client.pubsub()
        await pubsub.psubscribe("__keyevent@*__:expired")

        logger.info("Redis keyspace notifications listener started")

        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                key = message["data"].decode("utf-8")

                # Проверяем, что это ключ промо-рассылки
                if key.startswith("promo_48h:"):
                    user_id = key.split(":")[1]
                    logger.info(f"Promo TTL expired for user {user_id}")

                    # Отправляем промо-сообщение
                    await send_promo_to_expired_user(bot, db_pool, int(user_id))

                # Проверяем, что это ключ неактивности
                elif key.startswith("inactivity_10m:"):
                    user_id = key.split(":")[1]
                    logger.info(f"Inactivity TTL expired for user {user_id}")

                    # Отправляем Instagram промо-сообщение
                    await send_instagram_promo_to_expired_user(
                        bot, db_pool, int(user_id), redis_client
                    )

                # Проверяем, что это ключ консультационной рассылки
                elif key.startswith("consultation_24h:"):
                    user_id = key.split(":")[1]
                    logger.info(f"Consultation TTL expired for user {user_id}")

                    # Отправляем консультационное промо-сообщение
                    await send_consultation_promo_to_expired_user(
                        bot, db_pool, int(user_id)
                    )

    except Exception as e:
        logger.error(f"Error in Redis keyspace notifications listener: {e}")
        raise


async def send_promo_to_expired_user(
    bot: Bot, db_pool: AsyncConnectionPool, user_id: int
) -> None:
    """Отправляет промо-сообщение конкретному пользователю после истечения TTL"""
    try:
        async with db_pool.connection() as conn:
            async with conn.cursor() as cursor:
                # Проверяем, что пользователь все еще активен
                await cursor.execute(
                    query="""
                        SELECT user_id, name, username
                        FROM users
                        WHERE user_id = %s
                        AND is_alive = true
                        AND banned = false;
                    """,
                    params=(user_id,),
                )
                user_data = await cursor.fetchone()

                if user_data:
                    user = {
                        "user_id": user_data[0],
                        "name": user_data[1],
                        "username": user_data[2],
                    }

                    try:
                        await send_promo_to_user(bot, user)
                        logger.info(f"Promo message sent to user {user_id}")
                    except TelegramRetryAfter as e:
                        wait_time = e.retry_after
                        logger.warning(
                            f"Rate limited for user {user_id}, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        await send_promo_to_user(bot, user)
                    except TelegramBadRequest as e:
                        error_msg = str(e)
                        if (
                            "chat not found" in error_msg
                            or "bot was blocked" in error_msg
                        ):
                            logger.warning(f"User {user_id} blocked bot")
                        elif "user is deactivated" in error_msg:
                            logger.warning(f"User {user_id} deactivated")
                        else:
                            logger.error(f"Bad request for user {user_id}: {error_msg}")
                    except Exception as e:
                        logger.error(f"Error sending promo to user {user_id}: {e}")
                else:
                    logger.info(f"User {user_id} is no longer active, skipping promo")

    except Exception as e:
        logger.error(f"Error processing expired promo for user {user_id}: {e}")


async def send_instagram_promo_to_expired_user(
    bot: Bot, db_pool: AsyncConnectionPool, user_id: int, redis_client: redis.Redis
) -> None:
    """Отправляет Instagram промо-сообщение пользователю после 10 минут неактивности"""
    try:
        # Проверяем, не отправляли ли мы Instagram промо за последние 24 часа
        if await is_instagram_promo_sent_recently(user_id, redis_client):
            logger.info(
                f"Instagram promo already sent to user {user_id} in last 24h, skipping"
            )
            return

        async with db_pool.connection() as conn:
            async with conn.cursor() as cursor:
                # Проверяем, что пользователь все еще активен
                await cursor.execute(
                    query="""
                        SELECT user_id, name, username
                        FROM users
                        WHERE user_id = %s
                        AND is_alive = true
                        AND banned = false;
                    """,
                    params=(user_id,),
                )
                user_data = await cursor.fetchone()

                if user_data:
                    user = {
                        "user_id": user_data[0],
                        "name": user_data[1],
                        "username": user_data[2],
                    }

                    try:
                        await send_instagram_promo_to_user(bot, user)

                        # Отмечаем, что Instagram промо было отправлено
                        await mark_instagram_promo_sent(user_id, redis_client)

                        logger.info(f"Instagram promo message sent to user {user_id}")
                    except TelegramRetryAfter as e:
                        wait_time = e.retry_after
                        logger.warning(
                            f"Rate limited for user {user_id}, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        await send_instagram_promo_to_user(bot, user)

                        # Отмечаем, что Instagram промо было отправлено
                        await mark_instagram_promo_sent(user_id, redis_client)

                    except TelegramBadRequest as e:
                        error_msg = str(e)
                        if (
                            "chat not found" in error_msg
                            or "bot was blocked" in error_msg
                        ):
                            logger.warning(f"User {user_id} blocked bot")
                        elif "user is deactivated" in error_msg:
                            logger.warning(f"User {user_id} deactivated")
                        else:
                            logger.error(f"Bad request for user {user_id}: {error_msg}")
                    except Exception as e:
                        logger.error(
                            f"Error sending Instagram promo to user {user_id}: {e}"
                        )
                else:
                    logger.info(
                        f"User {user_id} is no longer active, skipping Instagram promo"
                    )

    except Exception as e:
        logger.error(
            f"Error processing expired Instagram promo for user {user_id}: {e}"
        )


async def add_user_to_promo_queue(user_id: int, redis_client: redis.Redis) -> None:
    """Добавляет пользователя в очередь на промо-рассылку через 48 часов"""
    try:
        key = f"promo_48h:{user_id}"
        # Устанавливаем TTL 48 часов (48 * 60 * 60 = 172800 секунд)
        await redis_client.setex(key, 172800, "pending")
        logger.debug(f"Added user {user_id} to promo queue with 48h TTL")
    except Exception as e:
        logger.error(f"Error adding user {user_id} to promo queue: {e}")


async def add_user_to_inactivity_queue(user_id: int, redis_client: redis.Redis) -> None:
    """Добавляет пользователя в очередь на рассылку через 10 минут неактивности"""
    try:
        key = f"inactivity_10m:{user_id}"
        # Устанавливаем TTL 10 минут (10 * 60 = 600 секунд)
        await redis_client.setex(key, 600, "pending")
        logger.info(
            f"Added user {user_id} to inactivity queue with 600s TTL (key: {key})"
        )
    except Exception as e:
        logger.error(f"Error adding user {user_id} to inactivity queue: {e}")


async def cancel_user_inactivity_queue(user_id: int, redis_client: redis.Redis) -> None:
    """Отменяет рассылку неактивности для пользователя (при новой активности)"""
    try:
        key = f"inactivity_10m:{user_id}"
        result = await redis_client.delete(key)
        logger.debug(
            f"Cancelled inactivity queue for user {user_id} (deleted: {result})"
        )
    except Exception as e:
        logger.error(f"Error cancelling inactivity queue for user {user_id}: {e}")


async def is_instagram_promo_sent_recently(
    user_id: int, redis_client: redis.Redis
) -> bool:
    """Проверяет, отправлялось ли Instagram промо пользователю за последние 24 часа"""
    try:
        key = f"instagram_promo_sent:{user_id}"
        exists = await redis_client.exists(key)
        return bool(exists)
    except Exception as e:
        logger.error(f"Error checking Instagram promo status for user {user_id}: {e}")
        return False


async def mark_instagram_promo_sent(user_id: int, redis_client: redis.Redis) -> None:
    """Отмечает, что Instagram промо было отправлено пользователю"""
    try:
        key = f"instagram_promo_sent:{user_id}"
        # Устанавливаем TTL 24 часа (24 * 60 * 60 = 86400 секунд)
        await redis_client.setex(key, 86400, "sent")
        logger.debug(f"Marked Instagram promo as sent for user {user_id}")
    except Exception as e:
        logger.error(f"Error marking Instagram promo as sent for user {user_id}: {e}")


async def send_consultation_promo_to_expired_user(
    bot: Bot, db_pool: AsyncConnectionPool, user_id: int
) -> None:
    """Отправляет консультационное промо-сообщение пользователю после 24 часов неактивности"""
    try:
        async with db_pool.connection() as conn:
            async with conn.cursor() as cursor:
                # Проверяем, что пользователь все еще активен
                await cursor.execute(
                    query="""
                        SELECT user_id, name, username
                        FROM users
                        WHERE user_id = %s
                        AND is_alive = true
                        AND banned = false;
                    """,
                    params=(user_id,),
                )
                user_data = await cursor.fetchone()

                if user_data:
                    user = {
                        "user_id": user_data[0],
                        "name": user_data[1],
                        "username": user_data[2],
                    }

                    try:
                        await send_consultation_promo_to_user(bot, user)
                        logger.info(
                            f"Consultation promo message sent to user {user_id}"
                        )
                    except TelegramRetryAfter as e:
                        wait_time = e.retry_after
                        logger.warning(
                            f"Rate limited for user {user_id}, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        await send_consultation_promo_to_user(bot, user)
                    except TelegramBadRequest as e:
                        error_msg = str(e)
                        if (
                            "chat not found" in error_msg
                            or "bot was blocked" in error_msg
                        ):
                            logger.warning(f"User {user_id} blocked bot")
                        elif "user is deactivated" in error_msg:
                            logger.warning(f"User {user_id} deactivated")
                        else:
                            logger.error(f"Bad request for user {user_id}: {error_msg}")
                    except Exception as e:
                        logger.error(
                            f"Error sending consultation promo to user {user_id}: {e}"
                        )
                else:
                    logger.info(
                        f"User {user_id} is no longer active, skipping consultation promo"
                    )

    except Exception as e:
        logger.error(
            f"Error processing expired consultation promo for user {user_id}: {e}"
        )


async def add_user_to_consultation_queue(
    user_id: int, redis_client: redis.Redis
) -> None:
    """Добавляет пользователя в очередь на консультационную рассылку через 24 часа"""
    try:
        key = f"consultation_24h:{user_id}"
        # Устанавливаем TTL 24 часа (24 * 60 * 60 = 86400 секунд)
        await redis_client.setex(key, 86400, "pending")
        logger.info(
            f"Added user {user_id} to consultation queue with 24h TTL (key: {key})"
        )
    except Exception as e:
        logger.error(f"Error adding user {user_id} to consultation queue: {e}")


async def cancel_user_consultation_queue(
    user_id: int, redis_client: redis.Redis
) -> None:
    """Отменяет консультационную рассылку для пользователя (при новой активности)"""
    try:
        key = f"consultation_24h:{user_id}"
        result = await redis_client.delete(key)
        logger.debug(
            f"Cancelled consultation queue for user {user_id} (deleted: {result})"
        )
    except Exception as e:
        logger.error(f"Error cancelling consultation queue for user {user_id}: {e}")


async def send_consultation_promo_to_user(bot: Bot, user) -> None:
    """Отправляет консультационное промо-сообщение конкретному пользователю"""
    # Создаем кнопку для заявки на подбор
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LEXICON_PROMO_RU["consultation_button_text"],
                    callback_data="application_for_selection_button",
                )
            ]
        ]
    )

    # Отправляем сообщение
    await bot.send_message(
        chat_id=user["user_id"],
        text=LEXICON_PROMO_RU["24h_consultation_text"],
        reply_markup=keyboard,
    )


async def send_promo_to_user(bot: Bot, user) -> None:
    """Отправляет промо-сообщение конкретному пользователю"""
    # Создаем кнопку для перехода в Telegram-канал
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LEXICON_PROMO_RU["telegram_button_text"],
                    url="https://t.me/americatradeby",
                )
            ]
        ]
    )

    # Отправляем сообщение
    await bot.send_message(
        chat_id=user["user_id"],
        text=LEXICON_PROMO_RU["48h_promo_text"],
        reply_markup=keyboard,
    )

    logger.debug(f"Promo message sent to user {user['user_id']}")


async def send_instagram_promo_to_user(bot: Bot, user) -> None:
    """Отправляет Instagram промо-сообщение конкретному пользователю"""
    # Создаем кнопку для перехода в Instagram
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=LEXICON_PROMO_RU["instagram_button_text"],
                    url="https://www.instagram.com/americatrade.by",
                )
            ]
        ]
    )

    # Отправляем сообщение
    await bot.send_message(
        chat_id=user["user_id"],
        text=LEXICON_PROMO_RU["10m_inactivity_text"],
        reply_markup=keyboard,
    )

    logger.debug(f"Instagram promo message sent to user {user['user_id']}")
