from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import CallbackQuery, TelegramObject

_HOURLY_LIMIT = 100
_WINDOW_SECONDS = 3600


class LimitActionMiddleware(BaseMiddleware):
    def __init__(self, storage: RedisStorage) -> None:
        super().__init__()
        self.storage = storage

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        if not get_flag(data, "blocking"):
            return await handler(event, data)

        key = f"FSM_user{event.from_user.id}"
        # SET ... NX создаёт ключ только при отсутствии — задаёт TTL ровно один раз.
        # Затем INCR увеличивает счётчик. Атомарно в MULTI/EXEC и совместимо
        # с Redis < 7 (EXPIRE NX появился только в 7.0).
        async with self.storage.redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=_WINDOW_SECONDS, nx=True)
            pipe.incr(key)
            _, new_value = await pipe.execute()

        if int(new_value) > _HOURLY_LIMIT:
            return await event.answer(
                text="Ваш лимит исчерпан! Повторите запрос через час.",
                show_alert=True,
            )

        return await handler(event, data)
