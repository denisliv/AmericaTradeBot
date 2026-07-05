"""drop Grafana metrics and AI manager objects

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05

Grafana и AI-менеджер удалены из проекта: сносим materialized views,
таблицы метрик (bot_metrics_events, bot_delivery_metrics) и chat_history.

"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_MATERIALIZED_VIEWS = (
    "mv_events_hourly",
    "mv_delivery_hourly",
    "mv_users_daily",
    "mv_self_funnel_daily",
    "mv_llm_funnel_daily",
)


def upgrade() -> None:
    for view in _MATERIALIZED_VIEWS:
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE;")
    op.execute("DROP TABLE IF EXISTS bot_delivery_metrics CASCADE;")
    op.execute("DROP TABLE IF EXISTS bot_metrics_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS chat_history CASCADE;")


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade is not supported: Grafana/AI manager objects were removed "
        "together with the application code (see revisions 0001-0003 for DDL)."
    )
