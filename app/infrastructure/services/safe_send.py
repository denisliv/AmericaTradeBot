"""Единая безопасная отправка сообщений пользователю для всех рассылок.

Классифицирует ошибки Telegram в одном месте и помечает недоступных
пользователей (заблокировали бота / деактивированы) как is_alive=false,
чтобы рассылки не тратили лимиты на мертвые чаты.
"""

import logging
from enum import Enum
from typing import Awaitable, Callable

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from psycopg import AsyncConnection

from app.infrastructure.database.users import change_user_alive_status

logger = logging.getLogger(__name__)

_UNREACHABLE_MARKERS = ("chat not found", "user is deactivated")


class SendStatus(Enum):
    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"


async def send_to_user_safely(
    send: Callable[[], Awaitable],
    *,
    conn: AsyncConnection,
    user_id: int,
) -> tuple[SendStatus, str]:
    """Выполняет отправку и классифицирует результат.

    TelegramRetryAfter пробрасывается наверх: политика обработки
    flood-limit у каждой рассылки своя.
    """
    try:
        await send()
    except TelegramRetryAfter:
        raise
    except TelegramForbiddenError as e:
        await change_user_alive_status(conn, is_alive=False, user_id=user_id)
        logger.info("User %d blocked the bot, marked as not alive", user_id)
        return SendStatus.BLOCKED, str(e)
    except TelegramBadRequest as e:
        message = str(e)
        if any(marker in message for marker in _UNREACHABLE_MARKERS):
            await change_user_alive_status(conn, is_alive=False, user_id=user_id)
            logger.info(
                "User %d unreachable (%s), marked as not alive", user_id, message
            )
            return SendStatus.BLOCKED, message
        return SendStatus.ERROR, message
    except Exception as e:
        return SendStatus.ERROR, str(e)
    return SendStatus.OK, ""
