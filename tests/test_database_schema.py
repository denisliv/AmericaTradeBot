from app.infrastructure.database.schema import (
    ASSISTED_SELECTION_DROP_SUBSCRIPTION_SQL,
    METRICS_TABLES_SQL,
)


def test_metrics_schema_has_shared_events_and_delivery_tables():
    ddl = "\n".join(METRICS_TABLES_SQL)

    assert "CREATE TABLE IF NOT EXISTS bot_metrics_events" in ddl
    assert "CREATE TABLE IF NOT EXISTS bot_delivery_metrics" in ddl


def test_assisted_selection_subscription_column_is_removed_by_migration_guard():
    assert (
        "ALTER TABLE assisted_selection_requests DROP COLUMN IF EXISTS subscription"
        in ASSISTED_SELECTION_DROP_SUBSCRIPTION_SQL
    )
