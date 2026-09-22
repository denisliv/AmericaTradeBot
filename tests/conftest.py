import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Правила подбора Copart живут в SQL, поэтому проверяются против настоящего
# PostgreSQL: подделка соединения проверила бы текст запроса, а не его смысл.
# Без адреса базы такие тесты пропускаются, и остальной набор идёт как обычно.
SALES_LOT_DSN_ENV = "AMERICATRADE_TEST_DSN"

_MIGRATION_PATH = PROJECT_ROOT / "alembic" / "versions" / "0002_sales_lot.py"


@pytest.fixture(scope="session")
def event_loop_policy():
    """Keep psycopg usable on Windows.

    psycopg refuses to run async on the ProactorEventLoop that Windows picks by
    default; main.py switches the policy for the same reason. On Linux, where
    the bot actually runs, this changes nothing.
    """
    if sys.platform.startswith("win"):
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


def _sales_lot_ddl() -> tuple[str, ...]:
    """Return the snapshot DDL straight from the migration that owns it."""
    spec = importlib.util.spec_from_file_location("_migration_0002", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SALES_LOT_DDL


@pytest_asyncio.fixture
async def sales_lot_conn():
    """Give a connection to an empty sales_lot table built by the migration DDL."""
    dsn = os.environ.get(SALES_LOT_DSN_ENV)
    if not dsn:
        pytest.skip(f"{SALES_LOT_DSN_ENV} is not set")

    from psycopg import AsyncConnection

    async with await AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute("DROP TABLE IF EXISTS sales_lot CASCADE;")
        for statement in _sales_lot_ddl():
            await conn.execute(statement)
        yield conn
