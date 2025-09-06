import logging
from typing import Any, Awaitable, Callable

import redis.asyncio as redis
from aiogram import BaseMiddleware
from aiogram.types import Update

logger = logging.getLogger(__name__)


class RedisMiddleware(BaseMiddleware):
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        data["redis"] = self.redis_client
        logger.debug("Redis client added to data")
        return await handler(event, data)
