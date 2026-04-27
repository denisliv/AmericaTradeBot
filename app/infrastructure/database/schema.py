"""Shared PostgreSQL schema fragments used by startup guards and migrations."""

METRICS_TABLES_SQL = (
    """
    CREATE TABLE IF NOT EXISTS bot_metrics_events(
        id BIGSERIAL PRIMARY KEY,
        event_name TEXT NOT NULL,
        user_id BIGINT,
        value DOUBLE PRECISION NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_bot_metrics_events_event_name_created_at
    ON bot_metrics_events(event_name, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_bot_metrics_events_user_id_created_at
    ON bot_metrics_events(user_id, created_at DESC);
    """,
    """
    CREATE TABLE IF NOT EXISTS bot_delivery_metrics(
        id BIGSERIAL PRIMARY KEY,
        category TEXT NOT NULL,
        status TEXT NOT NULL,
        user_id BIGINT,
        error_text TEXT,
        duration_ms INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_bot_delivery_metrics_category_status_created_at
    ON bot_delivery_metrics(category, status, created_at DESC);
    """,
)

ASSISTED_SELECTION_DROP_SUBSCRIPTION_SQL = """
ALTER TABLE assisted_selection_requests DROP COLUMN IF EXISTS subscription;
"""
