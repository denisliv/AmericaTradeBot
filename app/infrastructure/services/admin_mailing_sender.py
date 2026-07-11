import asyncio
import logging
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.admin_mailing import (
    get_admin_mailing_waiting_user_ids,
    update_admin_mailing_status,
)
from app.infrastructure.services.safe_send import SendStatus, send_to_user_safely

logger = logging.getLogger(__name__)

_MAX_RETRY_ATTEMPTS = 3
_RETRY_TOTAL_CAP_SECONDS = 120
_PROGRESS_EVERY = 25


def build_mailing_button_keyboard(
    text_button: str, url_button: str
) -> InlineKeyboardMarkup:
    """Единая зеленая URL-кнопка рассылки (используется в превью и отправке)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text_button,
                    url=url_button,
                    style=ButtonStyle.SUCCESS,
                )
            ]
        ]
    )


def build_media_list(
    media_items: list[dict],
) -> list[InputMediaPhoto | InputMediaVideo]:
    """Единый построитель InputMedia из media_items (рассылка и превью)."""
    result: list[InputMediaPhoto | InputMediaVideo] = []
    for item in media_items:
        if item["type"] == "photo":
            result.append(
                InputMediaPhoto(
                    media=item["file_id"],
                    caption=item.get("caption"),
                )
            )
        elif item["type"] == "video":
            result.append(
                InputMediaVideo(
                    media=item["file_id"],
                    caption=item.get("caption"),
                )
            )
        else:
            raise ValueError(f"Unsupported media type: {item['type']}")
    return result


class AdminMailingSender:
    """Копия подхода Auto4Export SenderList: copy_message / media_group + учёт в admin_mailing."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_message(
        self,
        conn: AsyncConnection,
        user_id: int,
        from_chat_id: int,
        message_id: int | None,
        keyboard: InlineKeyboardMarkup | None = None,
        media_items: list[dict] | None = None,
        is_album: bool = False,
        button_message_text: str = "👇",
    ) -> bool:
        if is_album and media_items:
            return await self._send_album(
                conn,
                user_id,
                media_items,
                keyboard,
                button_message_text,
            )
        if message_id is None:
            await update_admin_mailing_status(
                conn,
                user_id=user_id,
                status="unsuccessful",
                description="no message_id for copy",
            )
            return False

        async def _send() -> None:
            await self.bot.copy_message(
                user_id,
                from_chat_id,
                message_id,
                reply_markup=keyboard,
            )

        return await self._deliver(conn, user_id, _send)

    async def _send_album(
        self,
        conn: AsyncConnection,
        user_id: int,
        media_items: list[dict],
        keyboard: InlineKeyboardMarkup | None = None,
        button_message_text: str = "👇",
    ) -> bool:
        media_list = build_media_list(media_items)

        async def _send() -> None:
            await self.bot.send_media_group(user_id, media=media_list)
            if keyboard:
                await self.bot.send_message(
                    user_id,
                    text=button_message_text,
                    reply_markup=keyboard,
                )

        return await self._deliver(conn, user_id, _send)

    async def _deliver(self, conn: AsyncConnection, user_id: int, send) -> bool:
        """Отправка с ретраями на flood-limit и учетом статуса в admin_mailing."""
        total_wait = 0.0
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRY_ATTEMPTS + 1):
            try:
                status, detail = await send_to_user_safely(
                    send, conn=conn, user_id=user_id
                )
            except TelegramRetryAfter as e:
                last_error = e
                if (
                    attempt >= _MAX_RETRY_ATTEMPTS
                    or total_wait + e.retry_after > _RETRY_TOTAL_CAP_SECONDS
                ):
                    break
                total_wait += e.retry_after
                await asyncio.sleep(e.retry_after)
                continue

            if status is SendStatus.OK:
                await update_admin_mailing_status(
                    conn,
                    user_id=user_id,
                    status="success",
                    description="No errors",
                )
                return True
            await update_admin_mailing_status(
                conn,
                user_id=user_id,
                status="unsuccessful",
                description=detail or status.value,
            )
            return False

        await update_admin_mailing_status(
            conn,
            user_id=user_id,
            status="unsuccessful",
            description=f"retry_after exhausted: {last_error}",
        )
        return False

    async def broadcaster(
        self,
        db_pool: AsyncConnectionPool,
        chat_id: int,
        message_id: int | None = None,
        media_items: list[dict] | None = None,
        is_album: bool = False,
        text_button: str | None = None,
        url_button: str | None = None,
        button_message_text: str = "👇",
        progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> int:
        keyboard = None
        if text_button and url_button:
            keyboard = build_mailing_button_keyboard(text_button, url_button)

        count = 0
        try:
            async with db_pool.connection() as conn:
                await conn.set_autocommit(True)
                user_ids = await get_admin_mailing_waiting_user_ids(conn)
                total = len(user_ids)
                for processed, uid in enumerate(user_ids, 1):
                    success = await self.send_message(
                        conn,
                        int(uid),
                        chat_id,
                        message_id,
                        keyboard,
                        media_items=media_items,
                        is_album=is_album,
                        button_message_text=button_message_text,
                    )
                    if success:
                        count += 1
                    if progress and processed % _PROGRESS_EVERY == 0:
                        try:
                            await progress(processed, total)
                        except Exception as e:
                            logger.debug("Mailing progress report failed: %s", e)
                    await asyncio.sleep(0.1)
        finally:
            logger.info("Admin mailing finished: %s successful deliveries", count)
        return count
