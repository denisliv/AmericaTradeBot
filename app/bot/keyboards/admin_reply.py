from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.lexicon.lexicon_ru import LEXICON_ADMIN_BUTTONS_RU


def create_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    kb_builder: ReplyKeyboardBuilder = ReplyKeyboardBuilder()
    kb_builder.row(
        KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU["statistics_button"]),
        KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU["newsletter_button"]),
        width=2,
    )
    kb_builder.row(
        KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU["ban_user_button"]),
        KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU["unban_user_button"]),
        width=2,
    )
    kb_builder.row(KeyboardButton(text=LEXICON_ADMIN_BUTTONS_RU["exit_button"]))
    return kb_builder.as_markup(resize_keyboard=True)
