"""Запросы к таблице nurture_state (прогревочная цепочка рассылок)."""

import logging

from psycopg import AsyncConnection

from app.infrastructure.database.models import NurtureRow

logger = logging.getLogger(__name__)


async def add_nurture_state(conn: AsyncConnection, *, user_id: int) -> None:
    """Ставит нового пользователя в начало прогревочной цепочки."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO nurture_state(user_id)
                VALUES (%s)
                ON CONFLICT DO NOTHING;
            """,
            params=(user_id,),
        )
    logger.info("Nurture chain started for user %d", user_id)


async def set_nurture_shift(
    conn: AsyncConnection, *, user_id: int, shift_days: int = 3
) -> None:
    """Смещает еще не отправленные шаги цепочки (заявка была оставлена)."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE nurture_state
                SET shift_days = %s
                WHERE user_id = %s;
            """,
            params=(shift_days, user_id),
        )
    logger.info("Nurture chain shifted by %d days for user %d", shift_days, user_id)


async def get_active_nurture_rows(conn: AsyncConnection) -> list[NurtureRow]:
    """Пользователи цепочки, которым можно отправлять сообщения."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                SELECT n.user_id, u.name, n.started_at, n.shift_days, n.last_step
                FROM nurture_state n
                JOIN users u ON u.user_id = n.user_id
                WHERE u.is_alive = true AND u.banned = false
                ORDER BY n.user_id;
            """
        )
        rows = await cursor.fetchall()
        return [NurtureRow(*row) for row in rows]


async def set_nurture_last_step(
    conn: AsyncConnection, *, user_id: int, last_step: int
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                UPDATE nurture_state
                SET last_step = %s
                WHERE user_id = %s;
            """,
            params=(last_step, user_id),
        )
