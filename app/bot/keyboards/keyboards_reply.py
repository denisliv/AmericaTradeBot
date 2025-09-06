from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.lexicon.lexicon_ru import LEXICON_BUTTONS_RU


# Функция, генерирующая клавиатуру для отправки номера телефона
def create_call_request_keyboard() -> ReplyKeyboardMarkup:
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(
        KeyboardButton(
            text=LEXICON_BUTTONS_RU["phone_number_button"], request_contact=True
        )
    )
    return kb_builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_chat_keyboard() -> ReplyKeyboardMarkup:
    """Создает клавиатуру для чата с LLM"""
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(
        KeyboardButton(text="🗑️ Очистить историю"),
        KeyboardButton(text="🚪 Выйти из чата"),
    )
    return kb_builder.as_markup(resize_keyboard=True, one_time_keyboard=False)
