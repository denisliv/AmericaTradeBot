from aiogram.enums import ButtonStyle
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.lexicon.lexicon_ru import LEXICON_BUTTONS_RU


# Функция, генерирующая клавиатуру для отправки номера телефона
def create_call_request_keyboard(
    text_key: str = "send_my_phone_button",
) -> ReplyKeyboardMarkup:
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(
        KeyboardButton(
            text=LEXICON_BUTTONS_RU[text_key],
            request_contact=True,
            style=ButtonStyle.SUCCESS,
        )
    )
    return kb_builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
