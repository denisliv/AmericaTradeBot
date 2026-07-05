from pathlib import Path

_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _read_migration(name: str) -> str:
    return (_VERSIONS_DIR / name).read_text(encoding="utf-8")


def test_metrics_and_chat_history_tables_are_dropped():
    ddl = _read_migration("0004_drop_grafana_ai_manager.py")

    assert "DROP TABLE IF EXISTS bot_metrics_events" in ddl
    assert "DROP TABLE IF EXISTS bot_delivery_metrics" in ddl
    assert "DROP TABLE IF EXISTS chat_history" in ddl


def test_assisted_selection_subscription_column_is_removed_by_migration_guard():
    ddl = _read_migration("0001_initial_schema.py")
    assert (
        "ALTER TABLE assisted_selection_requests DROP COLUMN IF EXISTS subscription"
        in ddl
    )
