from psycopg import AsyncConnection

from app.infrastructure.database.db import (
    change_user_banned_status_by_id,
    change_user_banned_status_by_username,
    get_user_banned_status_by_id,
    get_user_banned_status_by_username,
)
from app.lexicon.lexicon_ru import LEXICON_ADMIN_RU


async def try_ban_user(conn: AsyncConnection, raw: str) -> str:
    arg_user = raw.split()[0].strip() if raw else ""
    if not arg_user:
        return LEXICON_ADMIN_RU["empty_ban_answer"]

    if arg_user.isdigit():
        banned_status = await get_user_banned_status_by_id(conn, user_id=int(arg_user))
    elif arg_user.startswith("@"):
        banned_status = await get_user_banned_status_by_username(
            conn, username=arg_user[1:]
        )
    else:
        return LEXICON_ADMIN_RU["incorrect_ban_arg"]

    if banned_status is None:
        return LEXICON_ADMIN_RU["no_user"]
    if banned_status:
        return LEXICON_ADMIN_RU["already_banned"]

    if arg_user.isdigit():
        await change_user_banned_status_by_id(conn, user_id=int(arg_user), banned=True)
    else:
        await change_user_banned_status_by_username(
            conn, username=arg_user[1:], banned=True
        )
    return LEXICON_ADMIN_RU["successfully_banned"]


async def try_unban_user(conn: AsyncConnection, raw: str) -> str:
    arg_user = raw.split()[0].strip() if raw else ""
    if not arg_user:
        return LEXICON_ADMIN_RU["empty_unban_answer"]

    if arg_user.isdigit():
        banned_status = await get_user_banned_status_by_id(conn, user_id=int(arg_user))
    elif arg_user.startswith("@"):
        banned_status = await get_user_banned_status_by_username(
            conn, username=arg_user[1:]
        )
    else:
        return LEXICON_ADMIN_RU["incorrect_unban_arg"]

    if banned_status is None:
        return LEXICON_ADMIN_RU["no_user"]
    if not banned_status:
        return LEXICON_ADMIN_RU["not_banned"]

    if arg_user.isdigit():
        await change_user_banned_status_by_id(conn, user_id=int(arg_user), banned=False)
    else:
        await change_user_banned_status_by_username(
            conn, username=arg_user[1:], banned=False
        )
    return LEXICON_ADMIN_RU["successfully_unbanned"]
