import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyKeyboardRemove,
)
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.bot.enums.roles import UserRole
from app.bot.filters.filters import UserRoleFilter
from app.bot.keyboards.admin_reply import create_admin_panel_keyboard
from app.bot.keyboards.keyboards_inline import (
    create_admin_keyboard,
    create_choice_keyboard,
)
from app.bot.states.admin_mailing import FSMAdminMailing
from app.bot.states.admin_panel import FSMAdminPanel
from app.bot.utils.admin_dashboard_text import format_admin_dashboard_html
from app.bot.utils.admin_user_moderation import try_ban_user, try_unban_user
from app.infrastructure.database.db import (
    admin_mailing_delete_table,
    admin_mailing_prepare_for_broadcast,
    get_admin_dashboard_stats,
)
from app.infrastructure.services.admin_mailing_sender import AdminMailingSender
from app.lexicon.lexicon_ru import (
    LEXICON_ADMIN_BUTTONS_RU,
    LEXICON_ADMIN_RU,
    LEXICON_RU,
)

logger = logging.getLogger(__name__)

admin_mailing_router = Router()
admin_mailing_router.message.filter(UserRoleFilter(UserRole.ADMIN))
admin_mailing_router.callback_query.filter(UserRoleFilter(UserRole.ADMIN))

DEFAULT_CHANNEL_BUTTON_TEXT = "Перейти в канал"
DEFAULT_CHANNEL_URL = "https://t.me/americatradeby"

_album_buffer: dict[str, list[Message]] = {}


def _in_mailing_fsm_state(state_name: str | None) -> bool:
    return bool(state_name and str(state_name).startswith("FSMAdminMailing"))


def _in_moderation_state(state_name: str | None) -> bool:
    return bool(state_name and "FSMAdminPanel" in str(state_name))


def _mailing_payload_from_state(data: dict) -> dict:
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


async def _handle_panel_during_moderation_input(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
    text: str,
) -> bool:
    """
    True — сообщение обработано как кнопка панели
    (ожидание user_id / @username для бана/разбана).
    """
    b = LEXICON_ADMIN_BUTTONS_RU
    if text == b["statistics_button"]:
        await state.set_state(None)
        stats = await get_admin_dashboard_stats(conn)
        await message.answer(
            format_admin_dashboard_html(stats),
            parse_mode="HTML",
            reply_markup=create_admin_panel_keyboard(),
        )
        return True
    if text == b["newsletter_button"]:
        if _in_mailing_fsm_state(await state.get_state()):
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
        if _in_mailing_fsm_state(await state.get_state()):
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
        if _in_mailing_fsm_state(await state.get_state()):
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


def _build_media_from_messages(
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


async def _process_album_after_delay(
    media_group_id: str,
    state: FSMContext,
    bot: Bot,
    chat_id: int,
) -> None:
    await asyncio.sleep(0.5)
    if media_group_id not in _album_buffer:
        return
    messages = _album_buffer.pop(media_group_id)
    messages.sort(key=lambda m: m.message_id)
    media_list = _build_media_from_messages(messages)
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
                {
                    "type": "photo",
                    "file_id": m.photo[-1].file_id,
                    "caption": cap,
                }
            )
        elif m.video:
            media_items.append(
                {
                    "type": "video",
                    "file_id": m.video.file_id,
                    "caption": cap,
                }
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


@admin_mailing_router.message(Command(commands=["admin"]))
async def admin_panel(message: Message) -> None:
    await message.answer(
        text=f"Здорова {message.from_user.first_name}. Снизу админ-панель. Чего изволите?",
        reply_markup=create_admin_panel_keyboard(),
    )


@admin_mailing_router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["statistics_button"])
async def admin_users_button_press(
    message: Message, state: FSMContext, conn: AsyncConnection
) -> None:
    s = await state.get_state()
    if _in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if _in_moderation_state(s):
        await state.set_state(None)
    statistics = await get_admin_dashboard_stats(conn)
    await message.answer(
        format_admin_dashboard_html(statistics),
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
    )


@admin_mailing_router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["exit_button"])
async def admin_exit_button_press(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        text=f"{message.from_user.first_name}, до свидания! Заходи еще.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        text=LEXICON_RU["/start_text"](message.from_user.first_name),
        reply_markup=create_choice_keyboard(
            "choose_a_car_button", "more_information_button", "contact_button", width=1
        ),
    )


@admin_mailing_router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["newsletter_button"])
async def admin_get_message_start(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if _in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if _in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        "Ок.\r\n"
        "Отправь мне сообщение, которое будет использовано как рекламное.\r\n"
        "Можешь использовать текст, одно фото/видео или альбом (до 10 фото/видео).",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminMailing.get_message)


@admin_mailing_router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["ban_user_button"])
async def admin_ban_button_press(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if _in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if _in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        LEXICON_ADMIN_RU["admin_panel_enter_ban"],
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminPanel.waiting_ban_input)


@admin_mailing_router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["unban_user_button"])
async def admin_unban_button_press(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if _in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if _in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        LEXICON_ADMIN_RU["admin_panel_enter_unban"],
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminPanel.waiting_unban_input)


@admin_mailing_router.message(StateFilter(FSMAdminPanel.waiting_ban_input), F.text)
async def admin_ban_id_input(
    message: Message, state: FSMContext, conn: AsyncConnection
) -> None:
    t = (message.text or "").strip()
    if await _handle_panel_during_moderation_input(message, state, conn, t):
        return
    out = await try_ban_user(conn, t)
    await message.answer(out, reply_markup=create_admin_panel_keyboard())
    await state.set_state(None)


@admin_mailing_router.message(StateFilter(FSMAdminPanel.waiting_unban_input), F.text)
async def admin_unban_id_input(
    message: Message, state: FSMContext, conn: AsyncConnection
) -> None:
    t = (message.text or "").strip()
    if await _handle_panel_during_moderation_input(message, state, conn, t):
        return
    out = await try_unban_user(conn, t)
    await message.answer(out, reply_markup=create_admin_panel_keyboard())
    await state.set_state(None)


@admin_mailing_router.message(StateFilter(FSMAdminPanel.waiting_ban_input), ~F.text)
async def admin_ban_id_non_text(message: Message) -> None:
    await message.answer(
        "Введите user_id или @username одним текстовым сообщением.",
        reply_markup=create_admin_panel_keyboard(),
    )


@admin_mailing_router.message(StateFilter(FSMAdminPanel.waiting_unban_input), ~F.text)
async def admin_unban_id_non_text(message: Message) -> None:
    await message.answer(
        "Введите user_id или @username одним текстовым сообщением.",
        reply_markup=create_admin_panel_keyboard(),
    )


@admin_mailing_router.message(
    StateFilter(FSMAdminMailing.get_message), F.photo | F.video
)
async def admin_get_button_media(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.media_group_id:
        mg_id = message.media_group_id
        if mg_id not in _album_buffer:
            _album_buffer[mg_id] = []
            asyncio.create_task(
                _process_album_after_delay(mg_id, state, bot, message.chat.id)
            )
        _album_buffer[mg_id].append(message)
        return

    await state.update_data(
        message_id=message.message_id,
        message_ids=None,
        chat_id=message.from_user.id,
        media_items=None,
        is_album=False,
    )
    await state.set_state(FSMAdminMailing.get_button)
    await message.answer(
        text="Ок.\r\n"
        "Я запомнил сообщение, которое ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


@admin_mailing_router.message(StateFilter(FSMAdminMailing.get_message))
async def admin_get_message_text(message: Message, state: FSMContext) -> None:
    await state.update_data(
        message_id=message.message_id,
        message_ids=None,
        chat_id=message.from_user.id,
        media_items=None,
        is_album=False,
    )
    await state.set_state(FSMAdminMailing.get_button)
    await message.answer(
        text="Ок.\r\n"
        "Я запомнил сообщение, которое ты хочешь разослать.\r\n"
        "Инлайн-кнопку с <i>ссылкой на любой ресурс</i> будем добавлять?",
        reply_markup=create_admin_keyboard("add_button", "no_button", width=2),
    )


@admin_mailing_router.callback_query(StateFilter(FSMAdminMailing.get_button))
async def admin_button_press(
    callback: CallbackQuery, bot: Bot, state: FSMContext
) -> None:
    if callback.data == "add_button":
        await callback.message.answer(
            "Отправь текст, который будет отображаться на кнопке.",
            reply_markup=None,
        )
        await state.set_state(FSMAdminMailing.get_button_text)

    elif callback.data == "no_button":
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(text_button=DEFAULT_CHANNEL_BUTTON_TEXT)
        await state.update_data(url_button=DEFAULT_CHANNEL_URL)
        data = await state.get_data()
        chat_id = int(data.get("chat_id"))
        is_album = data.get("is_album", False)
        if is_album:
            await callback.message.answer(
                "Введите текст, который будет отображаться над кнопкой:"
            )
            await state.set_state(FSMAdminMailing.get_button_message_text)
        else:
            added = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=DEFAULT_CHANNEL_BUTTON_TEXT,
                            url=DEFAULT_CHANNEL_URL,
                        )
                    ]
                ]
            )
            await admin_confirm(
                callback.message, bot, chat_id, added, state_data=data, state=state
            )

    await callback.answer()


@admin_mailing_router.message(StateFilter(FSMAdminMailing.get_button_text))
async def admin_get_button_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Теперь отправь ссылку на ресурс, на который кнопка будет вести."
    )
    await state.update_data(text_button=message.text)
    await state.set_state(FSMAdminMailing.get_button_url)


@admin_mailing_router.message(StateFilter(FSMAdminMailing.get_button_url))
async def admin_get_button_url(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.update_data(url_button=message.text)
    data = await state.get_data()
    text_button = data.get("text_button")
    chat_id = int(data.get("chat_id"))
    is_album = data.get("is_album", False)

    added = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text_button, url=message.text)]]
    )
    if is_album:
        await message.answer("Введите текст, который будет отображаться над кнопкой:")
        await state.set_state(FSMAdminMailing.get_button_message_text)
    else:
        await admin_confirm(message, bot, chat_id, added, state_data=data, state=state)


@admin_mailing_router.message(StateFilter(FSMAdminMailing.get_button_message_text))
async def admin_get_button_message_text(
    message: Message, bot: Bot, state: FSMContext
) -> None:
    await state.update_data(button_message_text=message.text or "👇")
    data = await state.get_data()
    text_button = data.get("text_button")
    url_button = data.get("url_button")
    chat_id = int(data.get("chat_id"))

    added = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text_button, url=url_button)]]
    )
    await admin_confirm(message, bot, chat_id, added, state_data=data, state=state)


def _build_media_list_from_state(
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
        else:
            result.append(
                InputMediaVideo(
                    media=item["file_id"],
                    caption=item.get("caption"),
                )
            )
    return result


async def admin_confirm(
    message: Message,
    bot: Bot,
    chat_id: int,
    reply_markup: InlineKeyboardMarkup,
    state_data: dict,
    state: FSMContext,
) -> None:
    is_album = state_data.get("is_album", False)
    if is_album and state_data.get("media_items"):
        media_list = _build_media_list_from_state(state_data["media_items"])
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


@admin_mailing_router.callback_query(
    F.data.in_({"confirm_sender", "cancel_sender"}),
    StateFilter(FSMAdminMailing.confirm_send),
)
async def sender_decide(
    callback: CallbackQuery,
    state: FSMContext,
    db_pool: AsyncConnectionPool,
) -> None:
    data = await state.get_data()
    sender = AdminMailingSender(callback.bot)

    if callback.data == "confirm_sender":
        await callback.message.edit_text("Начинаю рассылку", reply_markup=None)
        try:
            try:
                payload = _mailing_payload_from_state(data)
            except ValueError as exc:
                await callback.message.answer(f"Не могу начать рассылку: {exc}")
                return
            async with db_pool.connection() as conn:
                await conn.set_autocommit(True)
                await admin_mailing_prepare_for_broadcast(conn)
            count = await sender.broadcaster(
                db_pool,
                chat_id=payload["chat_id"],
                message_id=payload["message_id"],
                media_items=payload["media_items"],
                is_album=payload["is_album"],
                text_button=payload["text_button"],
                url_button=payload["url_button"],
                button_message_text=payload["button_message_text"],
            )
            await callback.message.answer(
                f"Успешно разослали рекламное сообщение [{count}] пользователям"
            )
        finally:
            try:
                async with db_pool.connection() as conn:
                    await conn.set_autocommit(True)
                    await admin_mailing_delete_table(conn)
            except Exception as e:
                logger.warning("admin_mailing_delete_table: %s", e, exc_info=True)

    elif callback.data == "cancel_sender":
        await callback.message.edit_text("Отменил рассылку", reply_markup=None)

    await state.clear()
    await callback.answer()
