import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from psycopg import AsyncConnection

from app.bot.enums.roles import UserRole
from app.bot.filters.filters import UserRoleFilter
from app.infrastructure.database.db import (
    change_user_banned_status_by_id,
    change_user_banned_status_by_username,
    get_user_banned_status_by_id,
    get_user_banned_status_by_username,
)
from app.lexicon.lexicon_ru import LEXICON_ADMIN_RU

logger = logging.getLogger(__name__)

admin_router = Router()

admin_router.message.filter(UserRoleFilter(UserRole.ADMIN))


# Этот хэндлер будет срабатывать на команду /ban для пользователя с ролью `UserRole.ADMIN`
@admin_router.message(Command("ban"))
async def process_ban_command(
    message: Message,
    command: CommandObject,
    conn: AsyncConnection,
) -> None:
    args = command.args

    if not args:
        await message.reply(LEXICON_ADMIN_RU["empty_ban_answer"])
        return

    arg_user = args.split()[0].strip()

    if arg_user.isdigit():
        banned_status = await get_user_banned_status_by_id(conn, user_id=int(arg_user))
    elif arg_user.startswith("@"):
        banned_status = await get_user_banned_status_by_username(
            conn, username=arg_user[1:]
        )
    else:
        await message.reply(LEXICON_ADMIN_RU["incorrect_ban_arg"])
        return

    if banned_status is None:
        await message.reply(LEXICON_ADMIN_RU["no_user"])
    elif banned_status:
        await message.reply(LEXICON_ADMIN_RU["already_banned"])
    else:
        if arg_user.isdigit():
            await change_user_banned_status_by_id(
                conn, user_id=int(arg_user), banned=True
            )
        else:
            await change_user_banned_status_by_username(
                conn, username=arg_user[1:], banned=True
            )
        await message.reply(LEXICON_ADMIN_RU["successfully_banned"])


# Этот хэндлер будет срабатывать на команду /unban для пользователя с ролью `UserRole.ADMIN`
@admin_router.message(Command("unban"))
async def process_unban_command(
    message: Message,
    command: CommandObject,
    conn: AsyncConnection,
) -> None:
    args = command.args

    if not args:
        await message.reply(LEXICON_ADMIN_RU["empty_unban_answer"])
        return

    arg_user = args.split()[0].strip()

    if arg_user.isdigit():
        banned_status = await get_user_banned_status_by_id(conn, user_id=int(arg_user))
    elif arg_user.startswith("@"):
        banned_status = await get_user_banned_status_by_username(
            conn, username=arg_user[1:]
        )
    else:
        await message.reply(LEXICON_ADMIN_RU["incorrect_unban_arg"])
        return

    if banned_status is None:
        await message.reply(LEXICON_ADMIN_RU["no_user"])
    elif banned_status:
        if arg_user.isdigit():
            await change_user_banned_status_by_id(
                conn, user_id=int(arg_user), banned=False
            )
        else:
            await change_user_banned_status_by_username(
                conn, username=arg_user[1:], banned=False
            )
        await message.reply(LEXICON_ADMIN_RU["successfully_unbanned"])
    else:
        await message.reply(LEXICON_ADMIN_RU["not_banned"])
