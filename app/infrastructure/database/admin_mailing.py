"""Queries for the temporary admin_mailing table (admin broadcasts)."""

from psycopg import AsyncConnection


async def admin_mailing_create_table(conn: AsyncConnection) -> None:
    """
    Создаёт таблицу admin_mailing и заполняет user_id
    (is_alive, не banned) — аналог временной рассылочной таблицы Auto4Export.
    """
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            CREATE TABLE admin_mailing (
                user_id BIGINT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'waiting',
                description TEXT
            );
            """
        )
        await cursor.execute(
            """
            INSERT INTO admin_mailing (user_id)
            SELECT user_id FROM users
            WHERE is_alive = true AND banned = false;
            """
        )


async def admin_mailing_delete_table(conn: AsyncConnection) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute("DROP TABLE IF EXISTS admin_mailing;")


async def get_admin_mailing_waiting_user_ids(conn: AsyncConnection) -> list[int]:
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            SELECT user_id FROM admin_mailing
            WHERE status = 'waiting'
            ORDER BY user_id;
            """
        )
        rows = await cursor.fetchall()
    return [int(r[0]) for r in rows]


async def update_admin_mailing_status(
    conn: AsyncConnection,
    *,
    user_id: int,
    status: str,
    description: str,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE admin_mailing
            SET status = %(status)s, description = %(description)s
            WHERE user_id = %(user_id)s;
            """,
            {
                "status": status,
                "description": description,
                "user_id": user_id,
            },
        )


async def admin_mailing_prepare_for_broadcast(conn: AsyncConnection) -> None:
    """
    Как в Auto4Export: перед рассылкой — отдельная таблица и список получателей.
    Удаляем старую admin_mailing (если осталась) и создаём заново.
    """
    await admin_mailing_delete_table(conn)
    await admin_mailing_create_table(conn)
