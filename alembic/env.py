"""Alembic environment for AmericaTrade.

URL подключения собирается из переменных окружения через config/config.py.
Используется synchronous psycopg-driver SQLAlchemy.
"""

from logging.config import fileConfig
from urllib.parse import quote

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.config import load_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_app_config = load_config()
_db = _app_config.db
_url = (
    f"postgresql+psycopg://{quote(_db.user, safe='')}:{quote(_db.password, safe='')}"
    f"@{_db.host}:{_db.port}/{_db.db}"
)
config.set_main_option("sqlalchemy.url", _url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
