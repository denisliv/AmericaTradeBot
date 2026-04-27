from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Update
from psycopg_pool import AsyncConnectionPool


class DataBaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        db_pool: AsyncConnectionPool = data.get("db_pool")

        async with db_pool.connection() as connection:
            previous_autocommit = connection.autocommit
            await connection.set_autocommit(True)
            try:
                data["conn"] = connection
                return await handler(event, data)
            finally:
                await connection.set_autocommit(previous_autocommit)
