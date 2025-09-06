import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update
from psycopg import AsyncConnection

from app.infrastructure.database.db import update_user_last_activity
from app.infrastructure.services.promo_newsletter import (
    add_user_to_consultation_queue,
    add_user_to_inactivity_queue,
    cancel_user_consultation_queue,
    cancel_user_inactivity_queue,
)

logger = logging.getLogger(__name__)


class ActivityTrackerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        # Получаем user_id из события
        user_id = None

        if event.message:
            user_id = event.message.from_user.id
        elif event.callback_query:
            user_id = event.callback_query.from_user.id
        elif event.inline_query:
            user_id = event.inline_query.from_user.id
        elif event.chosen_inline_result:
            user_id = event.chosen_inline_result.from_user.id
        elif event.shipping_query:
            user_id = event.shipping_query.from_user.id
        elif event.pre_checkout_query:
            user_id = event.pre_checkout_query.from_user.id
        elif event.poll_answer:
            user_id = event.poll_answer.user.id
        elif event.my_chat_member:
            user_id = event.my_chat_member.from_user.id
        elif event.chat_member:
            user_id = event.chat_member.from_user.id
        elif event.chat_join_request:
            user_id = event.chat_join_request.from_user.id

        # Если удалось получить user_id и есть соединение с БД, обновляем активность
        if user_id and "conn" in data:
            try:
                conn: AsyncConnection = data["conn"]
                await update_user_last_activity(conn, user_id=user_id)
                logger.debug("Updated last_activity for user %d", user_id)

                # Управляем очередями промо-рассылок
                if "redis" in data:
                    redis_client = data["redis"]
                    logger.debug(f"Processing promo queues for user {user_id}")

                    # Отменяем и пересоздаем очереди неактивности (10 минут)
                    await cancel_user_inactivity_queue(user_id, redis_client)
                    await add_user_to_inactivity_queue(user_id, redis_client)

                    # Отменяем и пересоздаем очереди консультации (24 часа)
                    await cancel_user_consultation_queue(user_id, redis_client)
                    await add_user_to_consultation_queue(user_id, redis_client)

                    logger.debug(
                        f"Successfully processed promo queues for user {user_id}"
                    )
                else:
                    logger.warning(f"Redis client not found in data for user {user_id}")

            except Exception as e:
                logger.warning(
                    "Failed to update last_activity for user %d: %s", user_id, e
                )

        # Вызываем следующий обработчик
        return await handler(event, data)
