from pathlib import Path

_VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _read_migration(name: str) -> str:
    return (_VERSIONS_DIR / name).read_text(encoding="utf-8")


def test_single_init_migration():
    migrations = [
        p.name for p in _VERSIONS_DIR.glob("*.py") if not p.name.startswith("__")
    ]
    assert migrations == ["0001_initial_schema.py"]


def test_init_schema_creates_actual_tables_only():
    ddl = _read_migration("0001_initial_schema.py")

    assert "CREATE TABLE users" in ddl
    assert "CREATE TABLE self_selection_requests" in ddl
    assert "CREATE TABLE assisted_selection_requests" in ddl

    # Grafana/AI-менеджер удалены из проекта: их таблиц не должно быть в схеме
    assert "chat_history" not in ddl
    assert "bot_metrics_events" not in ddl
    assert "bot_delivery_metrics" not in ddl


def test_init_schema_keeps_query_indexes():
    ddl = _read_migration("0001_initial_schema.py")

    assert "idx_users_role" in ddl
    assert "idx_self_selection_subscription" in ddl
    assert "idx_activity_user_day" in ddl
    assert "idx_assisted_activity_user_day" in ddl
