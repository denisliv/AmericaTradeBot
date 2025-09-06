from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
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
        if event.from_user.id in self.admin_ids:
            return await handler(event, data)
        else:
            user = f"trottling_user{event.from_user.id}"
            check_user = await self.storage.redis.get(name=user)

            if check_user:
                if int(check_user.decode()) == 1:
                    await self.storage.redis.set(name=user, value=0, ex=1)
                    return await event.answer(
                        text="Мы обнаружили подозрительную активность. Подождите 1 секунду"
                    )
                return
            await self.storage.redis.set(name=user, value=1, ex=2)
            return await handler(event, data)
