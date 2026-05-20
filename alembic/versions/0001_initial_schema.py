"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-18

"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            username VARCHAR(50),
            name VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            role VARCHAR(30) NOT NULL,
            is_alive BOOLEAN NOT NULL,
            banned BOOLEAN NOT NULL,
            active_car_count INTEGER NOT NULL
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS self_selection_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            brand VARCHAR(50),
            model VARCHAR(50),
            year VARCHAR(50),
            odometer VARCHAR(50),
            auction_status VARCHAR(50),
            subscription BOOLEAN NOT NULL DEFAULT FALSE
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_user_day
        ON self_selection_requests (user_id, created_at);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS assisted_selection_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            body_style VARCHAR(50),
            budget VARCHAR(50)
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_assisted_activity_user_day
        ON assisted_selection_requests (user_id, created_at);
        """
    )
    op.execute(
        "ALTER TABLE assisted_selection_requests DROP COLUMN IF EXISTS subscription;"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at);"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_metrics_events (
            id BIGSERIAL PRIMARY KEY,
            event_name TEXT NOT NULL,
            user_id BIGINT,
            value DOUBLE PRECISION NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bot_metrics_events_event_name_created_at
        ON bot_metrics_events(event_name, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bot_metrics_events_user_id_created_at
        ON bot_metrics_events(user_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_delivery_metrics (
            id BIGSERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            status TEXT NOT NULL,
            user_id BIGINT,
            error_text TEXT,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bot_delivery_metrics_category_status_created_at
        ON bot_delivery_metrics(category, status, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_delivery_metrics CASCADE;")
    op.execute("DROP TABLE IF EXISTS bot_metrics_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS chat_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS assisted_selection_requests CASCADE;")
    op.execute("DROP TABLE IF EXISTS self_selection_requests CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
