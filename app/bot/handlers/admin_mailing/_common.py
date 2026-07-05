"""Shared helpers for admin mailing routers."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyKeyboardRemove,
)
from psycopg import AsyncConnection

from app.bot.enums.roles import UserRole
from app.bot.filters.filters import UserRoleFilter
from app.bot.keyboards.admin_reply import create_admin_panel_keyboard
from app.bot.keyboards.keyboards_inline import (
    create_admin_keyboard,
    create_choice_keyboard,
)
from app.bot.states.admin_mailing import FSMAdminMailing
from app.bot.states.admin_panel import FSMAdminPanel
from app.bot.utils.admin_dashboard_text import format_admin_kpi_html
from app.infrastructure.database.users import get_admin_kpi_summary
from app.lexicon.lexicon_ru import (
    LEXICON_ADMIN_BUTTONS_RU,
    LEXICON_ADMIN_RU,
    LEXICON_RU,
)

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL_BUTTON_TEXT = "Перейти в канал"
DEFAULT_CHANNEL_URL = "https://t.me/americatradeby"


def make_admin_router() -> Router:
    """Создаёт Router с фильтром на роль ADMIN (фильтры родителя не наследуются)."""
    r = Router()
    r.message.filter(UserRoleFilter(UserRole.ADMIN))
    r.callback_query.filter(UserRoleFilter(UserRole.ADMIN))
    return r


class AlbumBuffer:
    """Потокобезопасный буфер сообщений альбома + удержание ссылок на задачи."""

    def __init__(self) -> None:
        self._messages: dict[str, list[Message]] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def add(
        self,
        media_group_id: str,
        message: Message,
        starter: Callable[[str], Awaitable[None]],
    ) -> None:
        async with self._lock:
            if media_group_id not in self._messages:
                self._messages[media_group_id] = []
                task = asyncio.create_task(starter(media_group_id))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            self._messages[media_group_id].append(message)

    async def pop(self, media_group_id: str) -> list[Message] | None:
        async with self._lock:
            return self._messages.pop(media_group_id, None)


album_buffer = AlbumBuffer()


def in_mailing_fsm_state(state_name: str | None) -> bool:
    return bool(state_name and str(state_name).startswith("FSMAdminMailing"))


def in_moderation_state(state_name: str | None) -> bool:
    return bool(state_name and "FSMAdminPanel" in str(state_name))


def mailing_payload_from_state(data: dict) -> dict:
    chat_id = data.get("chat_id")
    if chat_id is None:
        raise ValueError("Missing chat_id for admin mailing")
    try:
        normalized_chat_id = int(chat_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid chat_id for admin mailing") from exc

    message_id = data.get("message_id")
    if message_id is not None:
        try:
            message_id = int(message_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid message_id for admin mailing") from exc

    return {
        "chat_id": normalized_chat_id,
        "message_id": message_id,
        "media_items": data.get("media_items"),
        "is_album": bool(data.get("is_album", False)),
        "text_button": data.get("text_button"),
        "url_button": data.get("url_button"),
        "button_message_text": data.get("button_message_text", "👇"),
    }


async def handle_panel_during_moderation_input(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
    text: str,
) -> bool:
    """True — сообщение обработано как кнопка панели (ожидание user_id/@username)."""
    b = LEXICON_ADMIN_BUTTONS_RU
    if text == b["statistics_button"]:
        await state.set_state(None)
        kpi = await get_admin_kpi_summary(conn)
        await message.answer(
            format_admin_kpi_html(kpi),
            parse_mode="HTML",
            reply_markup=create_admin_panel_keyboard(),
        )
        return True
    if text == b["newsletter_button"]:
        if in_mailing_fsm_state(await state.get_state()):
            await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
            return True
        await state.set_state(FSMAdminMailing.get_message)
        await message.answer(
            "Ок.\r\n"
            "Отправь мне сообщение, которое будет использовано как рекламное.\r\n"
            "Можешь использовать текст, одно фото/видео или альбом (до 10 фото/видео).",
            reply_markup=create_admin_panel_keyboard(),
        )
        return True
    if text == b["exit_button"]:
        await state.clear()
        await message.answer(
            f"{message.from_user.first_name}, до свидания! Заходи еще.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            text=LEXICON_RU["/start_text"](message.from_user.first_name),
            reply_markup=create_choice_keyboard(
                "choose_a_car_button",
                "more_information_button",
                "contact_button",
                width=1,
            ),
        )
        return True
    if text == b["ban_user_button"]:
        if in_mailing_fsm_state(await state.get_state()):
            await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
            return True
        await message.answer(
            LEXICON_ADMIN_RU["admin_panel_enter_ban"],
            parse_mode="HTML",
            reply_markup=create_admin_panel_keyboard(),
        )
        await state.set_state(FSMAdminPanel.waiting_ban_input)
        return True
    if text == b["unban_user_button"]:
        if in_mailing_fsm_state(await state.get_state()):
            await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
            return True
        await message.answer(
            LEXICON_ADMIN_RU["admin_panel_enter_unban"],
            parse_mode="HTML",
            reply_markup=create_admin_panel_keyboard(),
        )
        await state.set_state(FSMAdminPanel.waiting_unban_input)
        return True
    return False


def build_media_from_messages(
    messages: list[Message],
) -> list[InputMediaPhoto | InputMediaVideo]:
    media_list: list[InputMediaPhoto | InputMediaVideo] = []
    caption: str | None = None
    for msg in sorted(messages, key=lambda m: m.message_id):
        if msg.photo:
            file_id = msg.photo[-1].file_id
            if caption is None and msg.caption:
                caption = msg.caption
            media_list.append(InputMediaPhoto(media=file_id, caption=caption))
            caption = None
        elif msg.video:
            file_id = msg.video.file_id
            if caption is None and msg.caption:
                caption = msg.caption
            media_list.append(InputMediaVideo(media=file_id, caption=caption))
            caption = None
    return media_list


def build_media_list_from_state(
    media_items: list[dict],
) -> list[InputMediaPhoto | InputMediaVideo]:
    result: list[InputMediaPhoto | InputMediaVideo] = []
    for item in media_items:
        if item["type"] == "photo":
            result.append(
                InputMediaPhoto(media=item["file_id"], caption=item.get("caption"))
            )
        else:
            result.append(
                InputMediaVideo(media=item["file_id"], caption=item.get("caption"))
            )
    return result


async def process_album_after_delay(
    media_group_id: str,
    state: FSMContext,
    bot: Bot,
    chat_id: int,
) -> None:
    await asyncio.sleep(0.5)
    messages = await album_buffer.pop(media_group_id)
    if not messages:
        return
    messages.sort(key=lambda m: m.message_id)
    media_list = build_media_from_messages(messages)
    if not media_list:
        await bot.send_message(
            chat_id, "Не удалось обработать альбом. Отправь фото или видео."
        )
        return

    sorted_msgs = sorted(messages, key=lambda m: m.message_id)
    media_items: list[dict] = []
    for i, m in enumerate(sorted_msgs):
        cap = m.caption if i == 0 else None
        if m.photo:
            media_items.append(
                {"type": "photo", "file_id": m.photo[-1].file_id, "caption": cap}
            )
        elif m.video:
            media_items.append(
                {"type": "video", "file_id": m.video.file_id, "caption": cap}
            )

    await state.update_data(
        message_ids=[m.message_id for m in sorted_msgs],
        chat_id=chat_id,
        media_items=media_items,
        is_album=True,
    )
    await state.set_state(FSMAdminMailing.get_button)
    await bot.send_message(
        chat_id,
        "Ок.\r\n"
        "Я запомнил альбом, который ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


async def admin_confirm(
    message: Message,
    bot: Bot,
    chat_id: int,
    reply_markup,
    state_data: dict,
    state: FSMContext,
) -> None:
    is_album = state_data.get("is_album", False)
    if is_album and state_data.get("media_items"):
        media_list = build_media_list_from_state(state_data["media_items"])
        await bot.send_media_group(chat_id, media=media_list)
        if reply_markup:
            button_text = state_data.get("button_message_text", "👇")
            await bot.send_message(chat_id, text=button_text, reply_markup=reply_markup)
    else:
        message_id = int(state_data.get("message_id")) if state_data else None
        if message_id:
            await bot.copy_message(
                chat_id, chat_id, message_id, reply_markup=reply_markup
            )

    await message.answer(
        text="Вот сообщение, которое будет разослано пользователям. Подтверждаешь?",
        reply_markup=create_admin_keyboard("confirm_sender", "cancel_sender"),
    )
    await state.set_state(FSMAdminMailing.confirm_send)
