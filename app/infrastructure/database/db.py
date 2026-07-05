import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg import AsyncConnection, sql

from app.bot.enums.roles import UserRole
from app.infrastructure.database.orm_models import (
    AssistedSelectionRow,
    SelfSelectionRow,
    UserRow,
)

logger = logging.getLogger(__name__)

STATS_TZ = "Europe/Moscow"


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


async def add_self_selection_request(
    conn: AsyncConnection,
    *,
    user_id: int,
    brand: str | None = None,
    model: str | None = None,
    year: str | None = None,
    odometer: str | None = None,
    auction_status: str | None = None,
    subscription: bool = False,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO self_selection_requests(user_id, brand, model, year, odometer, auction_status, subscription)
                VALUES(
                    %(user_id)s, 
                    %(brand)s, 
                    %(model)s, 
                    %(year)s, 
                    %(odometer)s, 
                    %(auction_status)s,
                    %(subscription)s
                ) ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "brand": brand,
                "model": model,
                "year": year,
                "odometer": odometer,
                "auction_status": auction_status,
                "subscription": subscription,
            },
        )
    logger.info(
        "Order added. Table=`%s`, user_id=%s, created_at='%s', "
        "brand='%s', model=%s, year=%s, odometer=%s, auction_status=%s, "
        "subscription='%s'",
        "self_selection_requests",
        user_id,
        datetime.now(timezone.utc),
        brand,
        model,
        year,
        odometer,
        auction_status,
        subscription,
    )


async def get_self_selection_request(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[SelfSelectionRow]:
    rows = await get_self_selection_requests(conn, user_id=user_id, limit=1)
    return rows[0] if rows else None


async def get_self_selection_requests(
    conn: AsyncConnection,
    *,
    user_id: int,
    limit: int = 5,
) -> list[SelfSelectionRow]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT 
                    id,
                    user_id,
                    created_at,
                    brand,
                    model,
                    year,
                    odometer,
                    auction_status
                    FROM self_selection_requests WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s;
            """,
            params=(user_id, limit),
        )
        rows = await data.fetchall()
        logger.info("Self-selection rows for user %s: %s", user_id, rows)
        return [SelfSelectionRow(*row) for row in rows]


async def set_subscription(
    conn: AsyncConnection,
    *,
    user_id: int,
    limit: int = 6,
    table: str = "self_selection_requests",
) -> int:
    if table != "self_selection_requests":
        logger.error("Unsupported subscription table: %s", table)
        return 0

    async with conn.transaction():
        async with conn.cursor() as cursor:
            # Блокируем строку пользователя, чтобы избежать race-condition по счетчику.
            await cursor.execute(
                query="""
                    SELECT active_car_count FROM users WHERE user_id = %s FOR UPDATE;
                """,
                params=(user_id,),
            )
            result = await cursor.fetchone()
            if not result:
                logger.error("User with user_id %s not found", user_id)
                return 0

            current_count = result[0]

            # Проверяем, не превышен ли лимит
            if current_count >= limit:
                logger.info(
                    "User %s has reached subscription limit (%d)", user_id, limit
                )
                return limit

            table_ident = sql.Identifier(table)
            # Находим последнюю запись пользователя (блокируем строку запроса).
            await cursor.execute(
                query=sql.SQL(
                    """
                    SELECT id, subscription
                    FROM {table}
                    WHERE user_id = %s AND brand IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE;
                    """
                ).format(table=table_ident),
                params=(user_id,),
            )
            result = await cursor.fetchone()
            if not result:
                logger.error("No %s found for user %s", table, user_id)
                return current_count

            request_id, has_subscription = result
            if has_subscription:
                logger.info(
                    "Subscription already active for user %s, request %s",
                    user_id,
                    request_id,
                )
                return current_count

            await cursor.execute(
                query=sql.SQL(
                    """
                    UPDATE {table}
                    SET subscription = true
                    WHERE id = %s;
                    """
                ).format(table=table_ident),
                params=(request_id,),
            )

            # Увеличиваем active_car_count только при реальной активации новой подписки.
            await cursor.execute(
                query="""
                    UPDATE users
                    SET active_car_count = active_car_count + 1
                    WHERE user_id = %s;
                """,
                params=(user_id,),
            )
            new_count = current_count + 1

            logger.info(
                "Subscription set for user %s. Request ID: %s, "
                "Previous count: %d, New count: %d",
                user_id,
                request_id,
                current_count,
                new_count,
            )

            return new_count


async def add_assisted_selection_request(
    conn: AsyncConnection,
    *,
    user_id: int,
    body_style: str | None = None,
    budget: str | None = None,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO assisted_selection_requests(user_id, body_style, budget)
                VALUES(
                    %(user_id)s, 
                    %(body_style)s, 
                    %(budget)s
                ) ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "body_style": body_style,
                "budget": budget,
            },
        )
    logger.info(
        "Assisted selection request added. Table=`%s`, user_id=%s, created_at='%s', "
        "body_style='%s', budget=%s",
        "assisted_selection_requests",
        user_id,
        datetime.now(timezone.utc),
        body_style,
        budget,
    )


async def get_assisted_selection_request(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[AssistedSelectionRow]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT 
                    id,
                    user_id,
                    created_at,
                    body_style,
                    budget
                    FROM assisted_selection_requests WHERE user_id = %s
                    ORDER BY created_at DESC;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
        logger.info("Assisted selection row is %s", row)
        if row:
            return AssistedSelectionRow(*row)
    return None


async def get_user_subscriptions(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> list[SelfSelectionRow]:
    """Получает все активные self-selection подписки пользователя."""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                SELECT id, user_id, created_at, brand, model, year, odometer, auction_status
                FROM self_selection_requests 
                WHERE user_id = %s AND subscription = true
                ORDER BY created_at DESC;
            """,
            params=(user_id,),
        )

        self_selection_rows = []
        async for row in cursor:
            self_selection_rows.append(SelfSelectionRow(*row))

        return self_selection_rows


async def delete_subscription(
    conn: AsyncConnection,
    *,
    user_id: int,
    subscription_id: int,
    table: str,
) -> bool:
    """Удаляет self-selection подписку пользователя."""
    if table != "self_selection_requests":
        logger.warning("Unsupported subscription table in delete_subscription: %s", table)
        return False

    async with conn.transaction():
        async with conn.cursor() as cursor:
            # Проверяем, что подписка существует и принадлежит пользователю
            await cursor.execute(
                query="""
                    SELECT id FROM self_selection_requests 
                    WHERE id = %s AND user_id = %s AND subscription = true;
                """,
                params=(subscription_id, user_id),
            )
            if not await cursor.fetchone():
                return False

            # Удаляем подписку
            await cursor.execute(
                query="""
                    UPDATE self_selection_requests 
                    SET subscription = false
                    WHERE id = %s;
                """,
                params=(subscription_id,),
            )

            # Уменьшаем active_car_count в users
            await cursor.execute(
                query="""
                    UPDATE users 
                    SET active_car_count = GREATEST(active_car_count - 1, 0)
                    WHERE user_id = %s;
                """,
                params=(user_id,),
            )

            logger.info(
                "Subscription deleted for user %s. Subscription ID: %s, Table: %s",
                user_id,
                subscription_id,
                table,
            )
            return True


async def get_self_selection_subscription_by_id(
    conn: AsyncConnection,
    *,
    user_id: int,
    subscription_id: int,
) -> Optional[tuple[str, str, str, str, str, datetime]]:
    """Получает данные self selection подписки по ID"""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                SELECT brand, model, year, odometer, auction_status, created_at
                FROM self_selection_requests 
                WHERE id = %s AND user_id = %s AND subscription = true;
            """,
            params=(subscription_id, user_id),
        )
        row = await cursor.fetchone()
        return row


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
