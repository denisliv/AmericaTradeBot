import logging
from datetime import datetime, timezone
from typing import Optional

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.bot.enums.roles import UserRole
from app.infrastructure.database.orm_models import (
    AssistedSelectionRow,
    SelfSelectionRow,
    UserRow,
)
from app.infrastructure.database.schema import METRICS_TABLES_SQL

logger = logging.getLogger(__name__)

STATS_TZ = "Europe/Moscow"


async def ensure_metrics_tables(conn: AsyncConnection) -> None:
    async with conn.cursor() as cursor:
        for query in METRICS_TABLES_SQL:
            await cursor.execute(query)


async def record_metric_event(
    conn: AsyncConnection,
    *,
    event_name: str,
    user_id: int | None = None,
    value: float = 1.0,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO bot_metrics_events(event_name, user_id, value)
            VALUES (%(event_name)s, %(user_id)s, %(value)s);
            """,
            {
                "event_name": event_name,
                "user_id": user_id,
                "value": value,
            },
        )


async def record_metric_event_with_pool(
    db_pool: AsyncConnectionPool,
    *,
    event_name: str,
    user_id: int | None = None,
    value: float = 1.0,
) -> None:
    try:
        async with db_pool.connection() as conn:
            await record_metric_event(
                conn,
                event_name=event_name,
                user_id=user_id,
                value=value,
            )
    except Exception as e:
        logger.warning("Failed to record metric event `%s`: %s", event_name, e)


async def record_delivery_metric(
    conn: AsyncConnection,
    *,
    category: str,
    status: str,
    user_id: int | None = None,
    error_text: str | None = None,
    duration_ms: int | None = None,
) -> None:
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO bot_delivery_metrics(category, status, user_id, error_text, duration_ms)
            VALUES (%(category)s, %(status)s, %(user_id)s, %(error_text)s, %(duration_ms)s);
            """,
            {
                "category": category,
                "status": status,
                "user_id": user_id,
                "error_text": error_text,
                "duration_ms": duration_ms,
            },
        )


async def record_delivery_metric_with_pool(
    db_pool: AsyncConnectionPool,
    *,
    category: str,
    status: str,
    user_id: int | None = None,
    error_text: str | None = None,
    duration_ms: int | None = None,
) -> None:
    try:
        async with db_pool.connection() as conn:
            await record_delivery_metric(
                conn,
                category=category,
                status=status,
                user_id=user_id,
                error_text=error_text,
                duration_ms=duration_ms,
            )
    except Exception as e:
        logger.warning(
            "Failed to record delivery metric `%s/%s`: %s", category, status, e
        )


def _rate(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _avg(total: float, count: float) -> float:
    if count <= 0:
        return 0.0
    return round(total / count, 2)


def _period_dict(row: tuple) -> dict[str, float]:
    return {
        "today": float(row[0] or 0),
        "d7": float(row[1] or 0),
        "d30": float(row[2] or 0),
        "all_time": float(row[3] or 0),
    }


async def _fetch_period_metric(
    conn: AsyncConnection,
    query: str,
    params: dict,
) -> dict[str, float]:
    async with conn.cursor() as cursor:
        await cursor.execute(query, params=params)
        row = await cursor.fetchone()
    if not row:
        return {"today": 0.0, "d7": 0.0, "d30": 0.0, "all_time": 0.0}
    return _period_dict(row)


async def get_admin_dashboard_stats(
    conn: AsyncConnection,
    *,
    tz: str = STATS_TZ,
) -> dict[str, dict[str, float]]:
    """
    Расширенные агрегаты админ-дашборда в разрезе периодов:
    today / d7 / d30 / all_time.
    """
    period_sql = """
        COUNT(*) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date = (timezone(%(tz)s, now()))::date
        )::bigint,
        COUNT(*) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 6)
        )::bigint,
        COUNT(*) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 29)
        )::bigint,
        COUNT(*)::bigint
    """
    period_sql_sum = """
        COALESCE(SUM(value) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date = (timezone(%(tz)s, now()))::date
        ), 0),
        COALESCE(SUM(value) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 6)
        ), 0),
        COALESCE(SUM(value) FILTER (
            WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 29)
        ), 0),
        COALESCE(SUM(value), 0)
    """
    params = {"tz": tz}

    users_total = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM users;",
        params,
    )
    users_banned = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM users WHERE banned = true;",
        params,
    )
    users_inactive = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM users WHERE is_alive = false;",
        params,
    )
    users_active = await _fetch_period_metric(
        conn,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, last_activity))::date = (timezone(%(tz)s, now()))::date
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, last_activity))::date >= ((timezone(%(tz)s, now()))::date - 6)
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, last_activity))::date >= ((timezone(%(tz)s, now()))::date - 29)
            )::bigint,
            COUNT(*)::bigint
        FROM users;
        """,
        params,
    )
    subscriptions_total = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM self_selection_requests WHERE subscription = true;",
        params,
    )

    llm_messages = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM chat_history WHERE role = 'user';",
        params,
    )

    self_requests = await _fetch_period_metric(
        conn,
        f"SELECT {period_sql} FROM self_selection_requests;",
        params,
    )

    def event_count(name: str) -> str:
        return (
            f"SELECT {period_sql} FROM bot_metrics_events WHERE event_name = %(event_name)s;"
        )

    def event_sum(name: str) -> str:
        return f"SELECT {period_sql_sum} FROM bot_metrics_events WHERE event_name = %(event_name)s;"

    funnel_started = await _fetch_period_metric(
        conn, event_count("self_flow_started"), {**params, "event_name": "self_flow_started"}
    )
    funnel_year = await _fetch_period_metric(
        conn, event_count("self_reached_year_step"), {**params, "event_name": "self_reached_year_step"}
    )
    funnel_auction = await _fetch_period_metric(
        conn, event_count("self_reached_auction_step"), {**params, "event_name": "self_reached_auction_step"}
    )
    funnel_completed = await _fetch_period_metric(
        conn, event_count("self_completed_search"), {**params, "event_name": "self_completed_search"}
    )
    clicked_lot = await _fetch_period_metric(
        conn, event_count("self_clicked_lot"), {**params, "event_name": "self_clicked_lot"}
    )
    leads_self = await _fetch_period_metric(
        conn, event_count("self_lead_sent"), {**params, "event_name": "self_lead_sent"}
    )

    subscriptions_created = await _fetch_period_metric(
        conn,
        event_count("self_subscription_created"),
        {**params, "event_name": "self_subscription_created"},
    )
    llm_chat_started = await _fetch_period_metric(
        conn, event_count("llm_chat_started"), {**params, "event_name": "llm_chat_started"}
    )
    llm_lead_sent = await _fetch_period_metric(
        conn, event_count("llm_lead_sent"), {**params, "event_name": "llm_lead_sent"}
    )

    searches_with_results = await _fetch_period_metric(
        conn,
        event_count("self_search_with_results"),
        {**params, "event_name": "self_search_with_results"},
    )
    searches_without_results = await _fetch_period_metric(
        conn,
        event_count("self_search_without_results"),
        {**params, "event_name": "self_search_without_results"},
    )
    cars_shown_sum = await _fetch_period_metric(
        conn,
        event_sum("self_cars_shown"),
        {**params, "event_name": "self_cars_shown"},
    )
    all_models_usage = await _fetch_period_metric(
        conn,
        event_count("self_all_models_selected"),
        {**params, "event_name": "self_all_models_selected"},
    )

    def delivery_count(category: str, status: str) -> str:
        return f"""
            SELECT {period_sql}
            FROM bot_delivery_metrics
            WHERE category = %(category)s AND status = %(status)s;
        """

    newsletter_sent = await _fetch_period_metric(
        conn,
        delivery_count("subscription_newsletter", "sent"),
        {**params, "category": "subscription_newsletter", "status": "sent"},
    )
    newsletter_failed = await _fetch_period_metric(
        conn,
        delivery_count("subscription_newsletter", "failed"),
        {**params, "category": "subscription_newsletter", "status": "failed"},
    )
    newsletter_retried = await _fetch_period_metric(
        conn,
        delivery_count("subscription_newsletter", "retried"),
        {**params, "category": "subscription_newsletter", "status": "retried"},
    )
    promo_sent = await _fetch_period_metric(
        conn,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date = (timezone(%(tz)s, now()))::date
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 6)
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 29)
            )::bigint,
            COUNT(*)::bigint
        FROM bot_delivery_metrics
        WHERE category IN ('promo_48h', 'promo_instagram', 'promo_consultation') AND status = 'sent';
        """,
        params,
    )
    promo_failed = await _fetch_period_metric(
        conn,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date = (timezone(%(tz)s, now()))::date
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 6)
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 29)
            )::bigint,
            COUNT(*)::bigint
        FROM bot_delivery_metrics
        WHERE category IN ('promo_48h', 'promo_instagram', 'promo_consultation') AND status = 'failed';
        """,
        params,
    )

    blocked_or_deactivated = await _fetch_period_metric(
        conn,
        """
        SELECT
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date = (timezone(%(tz)s, now()))::date
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 6)
            )::bigint,
            COUNT(*) FILTER (
                WHERE (timezone(%(tz)s, created_at))::date >= ((timezone(%(tz)s, now()))::date - 29)
            )::bigint,
            COUNT(*)::bigint
        FROM bot_delivery_metrics
        WHERE status IN ('blocked', 'deactivated');
        """,
        params,
    )

    invalid_callbacks = await _fetch_period_metric(
        conn, event_count("invalid_callback"), {**params, "event_name": "invalid_callback"}
    )
    handler_exceptions = await _fetch_period_metric(
        conn,
        event_count("handler_exception"),
        {**params, "event_name": "handler_exception"},
    )
    db_errors = await _fetch_period_metric(
        conn, event_count("db_error"), {**params, "event_name": "db_error"}
    )
    redis_listener_restarts = await _fetch_period_metric(
        conn,
        event_count("redis_listener_restart"),
        {**params, "event_name": "redis_listener_restart"},
    )

    periods = ("today", "d7", "d30", "all_time")
    conversion = {
        "search_to_subscription_rate": {},
        "search_to_lead_rate": {},
        "llm_to_lead_rate": {},
        "avg_cars_shown_per_search": {},
    }
    for p in periods:
        conversion["search_to_subscription_rate"][p] = _rate(
            subscriptions_created[p], funnel_completed[p]
        )
        conversion["search_to_lead_rate"][p] = _rate(leads_self[p], funnel_completed[p])
        conversion["llm_to_lead_rate"][p] = _rate(llm_lead_sent[p], llm_chat_started[p])
        conversion["avg_cars_shown_per_search"][p] = _avg(
            cars_shown_sum[p], searches_with_results[p]
        )

    return {
        "users_total": users_total,
        "users_banned": users_banned,
        "users_inactive": users_inactive,
        "users_active": users_active,
        "subscriptions_total": subscriptions_total,
        "llm_messages": llm_messages,
        "self_requests": self_requests,
        "funnel_started": funnel_started,
        "funnel_reached_year": funnel_year,
        "funnel_reached_auction": funnel_auction,
        "funnel_completed": funnel_completed,
        "clicked_lot": clicked_lot,
        "leads_self": leads_self,
        "subscriptions_created": subscriptions_created,
        "llm_chat_started": llm_chat_started,
        "llm_lead_sent": llm_lead_sent,
        "searches_with_results": searches_with_results,
        "searches_without_results": searches_without_results,
        "all_models_usage": all_models_usage,
        "newsletter_sent": newsletter_sent,
        "newsletter_failed": newsletter_failed,
        "newsletter_retried": newsletter_retried,
        "promo_sent": promo_sent,
        "promo_failed": promo_failed,
        "blocked_or_deactivated": blocked_or_deactivated,
        "invalid_callbacks": invalid_callbacks,
        "handler_exceptions": handler_exceptions,
        "db_errors": db_errors,
        "redis_listener_restarts": redis_listener_restarts,
        "conversion": conversion,
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

            # Находим последнюю запись пользователя (блокируем строку запроса).
            await cursor.execute(
                query="""
                    SELECT id, subscription
                    FROM {table}
                    WHERE user_id = %s AND brand IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE;
                """.format(table=table),
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
                query=f"""
                    UPDATE {table}
                    SET subscription = true
                    WHERE id = %s;
                """,
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


async def prune_chat_history(conn: AsyncConnection) -> int:
    """Удаляет все сообщения LLM-чата старше одного месяца (по created_at). Возвращает число удалённых строк."""
    async with conn.transaction():
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM chat_history
                WHERE created_at < NOW() - INTERVAL '1 month';
                """
            )
            deleted = cursor.rowcount
    logger.info("Pruned %s chat_history rows older than 1 month", deleted)
    return deleted if isinstance(deleted, int) and deleted >= 0 else 0


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
