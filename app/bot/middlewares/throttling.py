from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    """Ограничение частоты текстовых сообщений: cooldown между сообщениями (Redis NX + TTL)."""

    COOLDOWN_SEC = 2

    def __init__(self, storage: RedisStorage, admin_ids: list) -> None:
        super().__init__()
        self.storage = storage
        self.admin_ids = admin_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user = event.from_user
        if user is None or user.id in self.admin_ids:
            return await handler(event, data)

        key = f"throttle:user:{user.id}"
        # NX: только если ключа ещё нет — разрешаем запрос и ставим окно cooldown
        was_set = await self.storage.redis.set(
            name=key,
            value="1",
            ex=self.COOLDOWN_SEC,
            nx=True,
        )
        if not was_set:
            return await event.answer(
                "Слишком много сообщений подряд. Подождите пару секунд."
            )

        return await handler(event, data)
