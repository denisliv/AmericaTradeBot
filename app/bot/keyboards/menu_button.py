from aiogram.types import BotCommand

from app.bot.enums.roles import UserRole
from app.lexicon.lexicon_ru import LEXICON_COMMANDS_RU


def get_main_menu_commands(role: UserRole):
    if role == UserRole.USER:
        return [
            BotCommand(
                command="/start",
                description=LEXICON_COMMANDS_RU.get("/start_description"),
            ),
            BotCommand(
                command="/help",
                description=LEXICON_COMMANDS_RU.get("/help_description"),
            ),
            BotCommand(
                command="/subscription",
                description=LEXICON_COMMANDS_RU.get("/subscription_description"),
            ),
            BotCommand(
                command="/chat",
                description=LEXICON_COMMANDS_RU.get("/chat_description"),
            ),
        ]
    elif role == UserRole.ADMIN:
        return [
            BotCommand(
                command="/start",
                description=LEXICON_COMMANDS_RU.get("/start_description"),
            ),
            BotCommand(
                command="/help",
                description=LEXICON_COMMANDS_RU.get("/help_description"),
            ),
            BotCommand(
                command="/subscription",
                description=LEXICON_COMMANDS_RU.get("/subscription_description"),
            ),
            BotCommand(
                command="/chat",
                description=LEXICON_COMMANDS_RU.get("/chat_description"),
            ),
            BotCommand(
                command="/admin",
                description=LEXICON_COMMANDS_RU.get("/admin_description"),
            ),
        ]
