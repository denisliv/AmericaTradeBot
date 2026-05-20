"""metrics materialized views

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-18

Aggregations pre-computed in materialized views so Grafana dashboards
read tiny pre-rolled tables instead of FILTER-COUNT over millions of rows.
Refreshed every 5 minutes by APScheduler через CONCURRENTLY.

"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----- 1. События по часам: основной grain для realtime-графиков -----
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_events_hourly AS
        SELECT
            date_trunc('hour', created_at) AS bucket,
            event_name,
            COUNT(*)::bigint AS event_count,
            COUNT(DISTINCT user_id)::bigint AS unique_users,
            SUM(value)::double precision AS value_sum
        FROM bot_metrics_events
        GROUP BY 1, 2
        WITH NO DATA;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_events_hourly_pk
        ON mv_events_hourly (bucket, event_name);
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mv_events_hourly_event_bucket "
        "ON mv_events_hourly (event_name, bucket DESC);"
    )

    # ----- 2. Доставка по часам (newsletter / promo) -----
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_delivery_hourly AS
        SELECT
            date_trunc('hour', created_at) AS bucket,
            category,
            status,
            COUNT(*)::bigint AS delivery_count,
            COUNT(DISTINCT user_id)::bigint AS unique_users,
            AVG(duration_ms)::double precision AS avg_duration_ms,
            PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY duration_ms)
                AS p95_duration_ms
        FROM bot_delivery_metrics
        GROUP BY 1, 2, 3
        WITH NO DATA;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_delivery_hourly_pk
        ON mv_delivery_hourly (bucket, category, status);
        """
    )

    # ----- 3. Регистрации и активность пользователей по дням -----
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_users_daily AS
        SELECT
            day,
            registered::bigint AS registered,
            active::bigint AS active,
            with_subscription::bigint AS with_subscription
        FROM (
            SELECT
                d::date AS day,
                COUNT(*) FILTER (WHERE u.created_at::date = d::date) AS registered,
                COUNT(*) FILTER (WHERE u.last_activity::date = d::date) AS active,
                COUNT(*) FILTER (
                    WHERE u.created_at::date <= d::date
                      AND u.active_car_count > 0
                ) AS with_subscription
            FROM generate_series(
                COALESCE(
                    (SELECT MIN(created_at)::date FROM users),
                    CURRENT_DATE
                ),
                CURRENT_DATE,
                interval '1 day'
            ) AS d
            LEFT JOIN users u ON TRUE
            GROUP BY d
        ) sub
        WITH NO DATA;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_users_daily_pk
        ON mv_users_daily (day);
        """
    )

    # ----- 4. Воронка self_selection: 4 точки на пользователя в день -----
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_self_funnel_daily AS
        SELECT
            day,
            started::bigint AS started,
            reached_auction::bigint AS reached_auction,
            completed::bigint AS completed,
            with_results::bigint AS with_results,
            clicked_lot::bigint AS clicked_lot,
            lead_sent::bigint AS lead_sent,
            subscription_created::bigint AS subscription_created
        FROM (
            SELECT
                created_at::date AS day,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_flow_started') AS started,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_reached_auction_step') AS reached_auction,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_completed_search') AS completed,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_completed_search' AND value > 0) AS with_results,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_clicked_lot') AS clicked_lot,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_lead_sent') AS lead_sent,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'self_subscription_created') AS subscription_created
            FROM bot_metrics_events
            WHERE event_name LIKE 'self\\_%' ESCAPE '\\'
            GROUP BY 1
        ) sub
        WITH NO DATA;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_self_funnel_daily_pk
        ON mv_self_funnel_daily (day);
        """
    )

    # ----- 5. Воронка LLM-чата -----
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_llm_funnel_daily AS
        SELECT
            day,
            chat_started::bigint AS chat_started,
            lead_sent::bigint AS lead_sent,
            handler_exceptions::bigint AS handler_exceptions
        FROM (
            SELECT
                created_at::date AS day,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'llm_chat_started') AS chat_started,
                COUNT(DISTINCT user_id) FILTER (WHERE event_name = 'llm_lead_sent') AS lead_sent,
                COUNT(*) FILTER (WHERE event_name = 'handler_exception') AS handler_exceptions
            FROM bot_metrics_events
            WHERE event_name IN ('llm_chat_started', 'llm_lead_sent', 'handler_exception')
            GROUP BY 1
        ) sub
        WITH NO DATA;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_llm_funnel_daily_pk
        ON mv_llm_funnel_daily (day);
        """
    )

    # Первичный non-concurrent refresh, чтобы появились данные —
    # потом APScheduler уже будет делать CONCURRENTLY.
    op.execute("REFRESH MATERIALIZED VIEW mv_events_hourly;")
    op.execute("REFRESH MATERIALIZED VIEW mv_delivery_hourly;")
    op.execute("REFRESH MATERIALIZED VIEW mv_users_daily;")
    op.execute("REFRESH MATERIALIZED VIEW mv_self_funnel_daily;")
    op.execute("REFRESH MATERIALIZED VIEW mv_llm_funnel_daily;")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_llm_funnel_daily;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_self_funnel_daily;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_users_daily;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_delivery_hourly;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_events_hourly;")
