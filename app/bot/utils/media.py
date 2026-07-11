"""Sending media albums in handlers with Telegram error handling."""

import asyncio
import logging

from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# Универсальная отправка media_group с обработкой ошибок.
# Media group не поддерживает reply_markup, поэтому кнопка выбора авто
# отправляется отдельным сообщением сразу под альбомом.
async def safe_send_media_group(
    callback: CallbackQuery, media_group, number, car
) -> bool:
    try:
        await callback.message.answer_media_group(media=media_group)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await callback.message.answer_media_group(media=media_group)
    except TelegramBadRequest as e:
        logger.warning(f"Ошибка TelegramBadRequest: {e}")
        return False

    button_text = f"📋 Получить детальный расчет Авто № {number}"
    callback_data = (
        f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}"
    )
    await callback.message.answer(
        text="👇 Нажмите кнопку, чтобы получить расчёт цены под ключ в РБ:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=callback_data,
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            ]
        ),
    )
    return True
