"""Queries for selection requests (self/assisted) and subscriptions."""

import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg import AsyncConnection, sql

from app.infrastructure.database.models import (
    AssistedSelectionRow,
    SelfSelectionRow,
)

logger = logging.getLogger(__name__)


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
