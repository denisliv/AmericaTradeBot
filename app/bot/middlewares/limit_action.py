from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import CallbackQuery, TelegramObject


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
        # Only process CallbackQuery events
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)

        blocking = get_flag(data, "blocking")
        user = f"FSM_user{event.from_user.id}"
        check_user = await self.storage.redis.get(name=user)

        if not blocking:
            return await handler(event, data)

        if check_user:
            value = int(check_user.decode())
            if value == 100:
                return await event.answer(
                    text="Ваш лимит исчерпан! Повторите запрос через час.",
                    show_alert=True,
                )
            else:
                value += 1
                await self.storage.redis.set(name=user, value=value, ex=3600)
                return await handler(event, data)

        await self.storage.redis.set(name=user, value=1, ex=3600)
        return await handler(event, data)
