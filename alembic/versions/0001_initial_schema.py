"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-10

"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
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
        CREATE INDEX idx_users_role
        ON users(role)
        WHERE role <> 'user';
        """
    )
    op.execute(
        """
        CREATE TABLE self_selection_requests (
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
        CREATE UNIQUE INDEX idx_activity_user_day
        ON self_selection_requests (user_id, created_at);
        """
    )
    op.execute(
        """
        CREATE INDEX idx_self_selection_subscription
        ON self_selection_requests(user_id)
        WHERE subscription = true;
        """
    )
    op.execute(
        """
        CREATE TABLE assisted_selection_requests (
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
        CREATE UNIQUE INDEX idx_assisted_activity_user_day
        ON assisted_selection_requests (user_id, created_at);
        """
    )
    op.execute(
        """
        CREATE TABLE nurture_state (
            user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            shift_days INTEGER NOT NULL DEFAULT 0,
            last_step INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nurture_state CASCADE;")
    op.execute("DROP TABLE IF EXISTS assisted_selection_requests CASCADE;")
    op.execute("DROP TABLE IF EXISTS self_selection_requests CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
