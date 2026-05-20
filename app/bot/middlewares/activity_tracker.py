import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update
from psycopg import AsyncConnection

from app.infrastructure.database.db import update_user_last_activity
from app.infrastructure.services.promo_newsletter import reset_user_promo_queues

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

                # Управляем очередями промо-рассылок одним pipeline-вызовом
                if "redis" in data:
                    await reset_user_promo_queues(user_id, data["redis"])
                else:
                    logger.warning(f"Redis client not found in data for user {user_id}")

            except Exception as e:
                logger.warning(
                    "Failed to update last_activity for user %d: %s", user_id, e
                )

        # Вызываем следующий обработчик
        return await handler(event, data)
