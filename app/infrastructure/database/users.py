"""Queries for the users table: accounts, statuses, admin KPI."""

import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg import AsyncConnection

from app.bot.enums.roles import UserRole
from app.infrastructure.database.models import UserRow

logger = logging.getLogger(__name__)


async def add_user(
    conn: AsyncConnection,
    *,
    user_id: int,
    username: str | None = None,
    name: str | None = None,
    role: UserRole = UserRole.USER,
    is_alive: bool = True,
    banned: bool = False,
    active_car_count: int = 0,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO users(user_id, username, name, role, is_alive, banned, active_car_count)
                VALUES(
                    %(user_id)s,
                    %(username)s,
                    %(name)s,
                    %(role)s,
                    %(is_alive)s,
                    %(banned)s,
                    %(active_car_count)s
                ) ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "username": username,
                "name": name,
                "role": role,
                "is_alive": is_alive,
                "banned": banned,
                "active_car_count": active_car_count,
            },
        )
    logger.info(
        "User added. Table=`%s`, user_id=%s, created_at='%s', last_activity='%s', "
        "name='%s', role=%s, is_alive=%s, banned=%s, active_car_count=%s",
        "users",
        user_id,
        datetime.now(timezone.utc),
        datetime.now(timezone.utc),
        name,
        role,
        is_alive,
        banned,
        active_car_count,
    )


async def get_user(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[UserRow]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT
                    id,
                    user_id,
                    username,
                    name,
                    created_at,
                    last_activity,
                    role,
                    is_alive,
                    banned,
                    active_car_count
                    FROM users WHERE user_id = %s;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
        logger.info("Row is %s", row)
        if row:
            return UserRow(*row)
    return None


async def get_user_role(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[str]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT role FROM users WHERE user_id = %s;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
        if row:
            return row[0]
    return None


async def get_user_banned_status_by_id(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[bool]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT banned FROM users WHERE user_id = %s;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
        return row[0] if row else None


async def get_user_banned_status_by_username(
    conn: AsyncConnection,
    *,
    username: str,
) -> Optional[bool]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT banned FROM users WHERE username = %s;
            """,
            params=(username,),
        )
        row = await data.fetchone()
        return row[0] if row else None


async def get_active_subscribers(
    conn: AsyncConnection,
) -> list[UserRow]:
    """Получает всех живых и не забаненных пользователей с активными подписками"""
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT
                    id,
                    user_id,
                    username,
                    name,
                    created_at,
                    last_activity,
                    role,
                    is_alive,
                    banned,
                    active_car_count
                FROM users
                WHERE is_alive = true
                AND banned = false
                AND active_car_count > 0;
            """,
        )
        rows = await data.fetchall()
        return [UserRow(*row) for row in rows]


async def get_broadcast_recipients(
    conn: AsyncConnection,
) -> list[UserRow]:
    """Живые не забаненные пользователи для ежедневной контент-рассылки (все, не только подписчики)."""
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT
                    id,
                    user_id,
                    username,
                    name,
                    created_at,
                    last_activity,
                    role,
                    is_alive,
                    banned,
                    active_car_count
                FROM users
                WHERE is_alive = true
                AND banned = false;
            """,
        )
        rows = await data.fetchall()
        return [UserRow(*row) for row in rows]


async def change_user_banned_status_by_id(
    conn: AsyncConnection,
    *,
    banned: bool,
    user_id: int,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE users
                SET banned = %s
                WHERE user_id = %s
            """,
            params=(banned, user_id),
        )
    logger.info("Updated `banned` status to `%s` for user %d", banned, user_id)


async def change_user_banned_status_by_username(
    conn: AsyncConnection,
    *,
    banned: bool,
    username: str,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE users
                SET banned = %s
                WHERE username = %s
            """,
            params=(banned, username),
        )
    logger.info("Updated `banned` status to `%s` for username %s", banned, username)


async def change_user_alive_status(
    conn: AsyncConnection,
    *,
    is_alive: bool,
    user_id: int,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE users
                SET is_alive = %s
                WHERE user_id = %s;
            """,
            params=(is_alive, user_id),
        )
    logger.info("Updated `is_alive` status to `%s` for user %d", is_alive, user_id)


async def update_user_last_activity(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE users
                SET last_activity = NOW()
                WHERE user_id = %s;
            """,
            params=(user_id,),
        )
    logger.info("Updated last_activity for user %d", user_id)


async def get_admin_kpi_summary(conn: AsyncConnection) -> dict[str, float | int]:
    """4 ключевых KPI для админ-панели."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COUNT(*)::bigint AS total_users,
                COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE)::bigint
                    AS registered_today,
                COUNT(*) FILTER (WHERE active_car_count > 0)::bigint
                    AS users_with_subscription,
                COALESCE(
                    AVG(active_car_count) FILTER (WHERE active_car_count > 0),
                    0
                )::double precision AS avg_cars_per_subscription
            FROM users
            WHERE banned = false;
            """
        )
        row = await cursor.fetchone()

    if not row:
        return {
            "total_users": 0,
            "registered_today": 0,
            "users_with_subscription": 0,
            "avg_cars_per_subscription": 0.0,
        }

    return {
        "total_users": int(row[0] or 0),
        "registered_today": int(row[1] or 0),
        "users_with_subscription": int(row[2] or 0),
        "avg_cars_per_subscription": round(float(row[3] or 0), 2),
    }
