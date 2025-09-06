import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg import AsyncConnection

from app.bot.enums.roles import UserRole
from app.infrastructure.database.orm_models import (
    AssistedSelectionRow,
    SelfSelectionRow,
    UserRow,
)

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
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT 
                    id,
                    user_id,
                    brand,
                    model,
                    year,
                    odometer,
                    auction_status,
                    subscription
                    FROM self_selection_requests WHERE user_id = %s;
            """,
            params=(user_id,),
        )
        row = await data.fetchone()
        logger.info("Row is %s", row)
        if row:
            return SelfSelectionRow(*row)
    return None


async def set_subscription(
    conn: AsyncConnection,
    *,
    user_id: int,
    limit: int = 6,
    table: str = "self_selection_requests",
) -> int:
    async with conn.cursor() as cursor:
        # Получаем текущее количество активных подписок
        await cursor.execute(
            query="""
                SELECT active_car_count FROM users WHERE user_id = %s;
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
            logger.info("User %s has reached subscription limit (%d)", user_id, limit)
            return limit

        if table == "self_selection_requests":
            # Находим последнюю запись пользователя в self_selection_requests
            await cursor.execute(
                query="""
                    SELECT id FROM self_selection_requests 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1;
                """,
                params=(user_id,),
            )
            result = await cursor.fetchone()
            if not result:
                logger.error("No self_selection_requests found for user %s", user_id)
                return current_count

            request_id = result[0]

            # Обновляем subscription в self_selection_requests
            await cursor.execute(
                query="""
                    UPDATE self_selection_requests 
                    SET subscription = true 
                    WHERE id = %s;
                """,
                params=(request_id,),
            )

        elif table == "assisted_selection_requests":
            await cursor.execute(
                query="""
                    SELECT id FROM assisted_selection_requests 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1;
                """,
                params=(user_id,),
            )
            result = await cursor.fetchone()
            if not result:
                logger.error(
                    "No assisted_selection_requests found for user %s", user_id
                )
                return current_count

            request_id = result[0]

            await cursor.execute(
                query="""
                    UPDATE assisted_selection_requests 
                    SET subscription = true 
                    WHERE id = %s;
                """,
                params=(request_id,),
            )

        # Увеличиваем active_car_count в users
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
    subscription: bool = False,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO assisted_selection_requests(user_id, body_style, budget, subscription)
                VALUES(
                    %(user_id)s, 
                    %(body_style)s, 
                    %(budget)s, 
                    %(subscription)s
                ) ON CONFLICT DO NOTHING;
            """,
            params={
                "user_id": user_id,
                "body_style": body_style,
                "budget": budget,
                "subscription": subscription,
            },
        )
    logger.info(
        "Assisted selection request added. Table=`%s`, user_id=%s, created_at='%s', "
        "body_style='%s', budget=%s, subscription='%s'",
        "assisted_selection_requests",
        user_id,
        datetime.now(timezone.utc),
        body_style,
        budget,
        subscription,
    )


async def get_assisted_selection_request(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> Optional[dict]:
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT 
                    id,
                    user_id,
                    body_style,
                    budget,
                    subscription
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
) -> tuple[list[SelfSelectionRow], list[AssistedSelectionRow]]:
    """Получает все активные подписки пользователя"""
    async with conn.cursor() as cursor:
        # Получаем подписки из self_selection_requests
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

        # Получаем подписки из assisted_selection_requests
        await cursor.execute(
            query="""
                SELECT id, user_id, created_at, body_style, budget
                FROM assisted_selection_requests 
                WHERE user_id = %s AND subscription = true
                ORDER BY created_at DESC;
            """,
            params=(user_id,),
        )
        assisted_selection_rows = []
        async for row in cursor:
            assisted_selection_rows.append(AssistedSelectionRow(*row))

        return self_selection_rows, assisted_selection_rows


async def delete_subscription(
    conn: AsyncConnection,
    *,
    user_id: int,
    subscription_id: int,
    table: str,
) -> bool:
    """Удаляет подписку пользователя"""
    async with conn.cursor() as cursor:
        if table == "self_selection_requests":
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

        elif table == "assisted_selection_requests":
            # Проверяем, что подписка существует и принадлежит пользователю
            await cursor.execute(
                query="""
                    SELECT id FROM assisted_selection_requests 
                    WHERE id = %s AND user_id = %s AND subscription = true;
                """,
                params=(subscription_id, user_id),
            )
            if not await cursor.fetchone():
                return False

            # Удаляем подписку
            await cursor.execute(
                query="""
                    UPDATE assisted_selection_requests 
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


async def get_assisted_selection_subscription_by_id(
    conn: AsyncConnection,
    *,
    user_id: int,
    subscription_id: int,
) -> Optional[tuple[str, str, datetime]]:
    """Получает данные assisted selection подписки по ID"""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                SELECT body_style, budget, created_at
                FROM assisted_selection_requests 
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


async def add_chat_message(
    conn: AsyncConnection,
    *,
    user_id: int,
    role: str,
    content: str,
) -> None:
    """Добавляет сообщение в историю чата пользователя"""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                INSERT INTO chat_history(user_id, role, content, created_at)
                VALUES(%(user_id)s, %(role)s, %(content)s, %(created_at)s);
            """,
            params={
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": datetime.now(timezone.utc),
            },
        )
    logger.info(f"Chat message added for user {user_id}, role: {role}")


async def get_chat_history(
    conn: AsyncConnection,
    *,
    user_id: int,
    limit: int = 10,
) -> list:
    """Получает историю чата пользователя"""
    async with conn.cursor() as cursor:
        data = await cursor.execute(
            query="""
                SELECT role, content, created_at 
                FROM chat_history 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s;
            """,
            params=(user_id, limit),
        )
        rows = await data.fetchall()
        # Возвращаем в правильном порядке (от старых к новым)
        return [
            {"role": row[0], "content": row[1], "created_at": row[2]}
            for row in reversed(rows)
        ]


async def clear_chat_history(
    conn: AsyncConnection,
    *,
    user_id: int,
) -> None:
    """Очищает историю чата пользователя"""
    async with conn.cursor() as cursor:
        await cursor.execute(
            query="""
                DELETE FROM chat_history WHERE user_id = %s;
            """,
            params=(user_id,),
        )
    logger.info(f"Chat history cleared for user {user_id}")
