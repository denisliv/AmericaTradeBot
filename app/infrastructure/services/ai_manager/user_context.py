import logging
from typing import Any

from psycopg import AsyncConnection

from app.infrastructure.database.db import (
    get_assisted_selection_request,
    get_chat_history,
    get_self_selection_requests,
    get_user,
    get_user_subscriptions,
)
from app.infrastructure.services.ai_manager.schemas import UserContext

logger = logging.getLogger(__name__)


class UserContextService:
    """Aggregates user information for autonomous agent decisions."""

    async def get_context(
        self,
        conn: AsyncConnection,
        *,
        user_id: int,
        chat_history_limit: int = 20,
    ) -> UserContext:
        user = await get_user(conn, user_id=user_id)
        self_subs = await get_user_subscriptions(conn, user_id=user_id)
        chat_history = await get_chat_history(conn, user_id=user_id, limit=chat_history_limit)
        recent_self = await get_self_selection_requests(conn, user_id=user_id, limit=5)
        latest_self = recent_self[0] if recent_self else None
        latest_assisted = await get_assisted_selection_request(conn, user_id=user_id)

        if user is None:
            logger.warning("User %s not found while building AI context", user_id)
            return UserContext(
                user_id=user_id,
                username=None,
                name=None,
                active_car_count=0,
                recent_self_selection_requests=[],
                self_subscriptions=[],
                recent_chat_messages=chat_history,
                latest_self_request=None,
                latest_assisted_request=None,
            )

        return UserContext(
            user_id=user.user_id,
            username=user.username,
            name=user.name,
            active_car_count=user.active_car_count,
            recent_self_selection_requests=[
                self._serialize_namedtuple(item) for item in recent_self
            ],
            self_subscriptions=[self._serialize_namedtuple(item) for item in self_subs],
            recent_chat_messages=chat_history,
            latest_self_request=(
                self._serialize_namedtuple(latest_self) if latest_self else None
            ),
            latest_assisted_request=(
                self._serialize_namedtuple(latest_assisted) if latest_assisted else None
            ),
        )

    @staticmethod
    def _serialize_namedtuple(obj: Any) -> dict[str, Any]:
        if hasattr(obj, "_asdict"):
            return obj._asdict()
        return dict(obj)

