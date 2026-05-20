from pathlib import Path

_INITIAL_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0001_initial_schema.py"
)


def _read_migration() -> str:
    return _INITIAL_MIGRATION.read_text(encoding="utf-8")


def test_metrics_schema_has_shared_events_and_delivery_tables():
    ddl = _read_migration()

    assert "CREATE TABLE IF NOT EXISTS bot_metrics_events" in ddl
    assert "CREATE TABLE IF NOT EXISTS bot_delivery_metrics" in ddl


def test_assisted_selection_subscription_column_is_removed_by_migration_guard():
    ddl = _read_migration()
    assert (
        "ALTER TABLE assisted_selection_requests DROP COLUMN IF EXISTS subscription"
        in ddl
    )
