"""add indexes for actual queries

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-18

"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_role
        ON users(role)
        WHERE role <> 'user';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_self_selection_subscription
        ON self_selection_requests(user_id)
        WHERE subscription = true;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_history_user_id_created_at_desc
        ON chat_history(user_id, created_at DESC);
        """
    )
    # Заменяем устаревший индекс одиночного user_id, теперь покрывается составным.
    op.execute("DROP INDEX IF EXISTS idx_chat_history_user_id;")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);"
    )
    op.execute("DROP INDEX IF EXISTS idx_chat_history_user_id_created_at_desc;")
    op.execute("DROP INDEX IF EXISTS idx_self_selection_subscription;")
    op.execute("DROP INDEX IF EXISTS idx_users_role;")
