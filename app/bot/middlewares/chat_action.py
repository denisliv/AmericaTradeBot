from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Bot
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.chat_action import ChatActionSender


class ChatActionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        long_operation_type = get_flag(data, "long_operation")

        if not long_operation_type:
            return await handler(event, data)

        # Получаем bot из data
        bot: Bot = data.get("bot")

        # Получаем chat_id в зависимости от типа события
        if isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id
        elif isinstance(event, Message):
            chat_id = event.chat.id
        else:
            return await handler(event, data)

        async with ChatActionSender(
            bot=bot,
            action=long_operation_type,
            chat_id=chat_id,
            interval=1,
            initial_sleep=0.1,
        ):
            result = await handler(event, data)
            return result
