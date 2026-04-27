import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.db import (
    get_admin_mailing_waiting_user_ids,
    update_admin_mailing_status,
)

logger = logging.getLogger(__name__)


class AdminMailingSender:
    """Копия подхода Auto4Export SenderList: copy_message / media_group + учёт в admin_mailing."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @staticmethod
    async def get_keyboard(
        text_button: str, url_button: str
    ) -> InlineKeyboardMarkup:
        keyboard_builder = InlineKeyboardBuilder()
        keyboard_builder.button(text=text_button, url=url_button)
        keyboard_builder.adjust(1)
        return keyboard_builder.as_markup()

    @staticmethod
    def _build_media_list(
        media_items: list[dict],
    ) -> list[InputMediaPhoto | InputMediaVideo]:
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
        try:
            await self.bot.copy_message(
                user_id,
                from_chat_id,
                message_id,
                reply_markup=keyboard,
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self.send_message(
                conn,
                user_id,
                from_chat_id,
                message_id,
                keyboard,
                media_items=media_items,
                is_album=is_album,
                button_message_text=button_message_text,
            )
        except Exception as e:
            await update_admin_mailing_status(
                conn,
                user_id=user_id,
                status="unsuccessful",
                description=str(e),
            )
        else:
            await update_admin_mailing_status(
                conn,
                user_id=user_id,
                status="success",
                description="No errors",
            )
            return True
        return False

    async def _send_album(
        self,
        conn: AsyncConnection,
        user_id: int,
        media_items: list[dict],
        keyboard: InlineKeyboardMarkup | None = None,
        button_message_text: str = "👇",
    ) -> bool:
        try:
            media_list = self._build_media_list(media_items)
            await self.bot.send_media_group(user_id, media=media_list)
            if keyboard:
                await self.bot.send_message(
                    user_id,
                    text=button_message_text,
                    reply_markup=keyboard,
                )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            return await self._send_album(
                conn, user_id, media_items, keyboard, button_message_text
            )
        except Exception as e:
            await update_admin_mailing_status(
                conn,
                user_id=user_id,
                status="unsuccessful",
                description=str(e),
            )
            return False
        await update_admin_mailing_status(
            conn,
            user_id=user_id,
            status="success",
            description="No errors",
        )
        return True

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
    ) -> int:
        keyboard = None
        if text_button and url_button:
            keyboard = await self.get_keyboard(text_button, url_button)

        count = 0
        try:
            async with db_pool.connection() as conn:
                await conn.set_autocommit(True)
                user_ids = await get_admin_mailing_waiting_user_ids(conn)
                for uid in user_ids:
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
                    await asyncio.sleep(0.1)
        finally:
            logger.info("Admin mailing finished: %s successful deliveries", count)
        return count
