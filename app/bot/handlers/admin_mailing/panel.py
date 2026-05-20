"""Handlers for the admin panel root: /admin, statistics, exit, ban/unban entry points."""

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from psycopg import AsyncConnection

from app.bot.handlers.admin_mailing._common import (
    in_mailing_fsm_state,
    in_moderation_state,
    make_admin_router,
)
from app.bot.keyboards.admin_reply import create_admin_panel_keyboard
from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.bot.states.admin_mailing import FSMAdminMailing
from app.bot.states.admin_panel import FSMAdminPanel
from app.bot.utils.admin_dashboard_text import format_admin_kpi_html
from app.infrastructure.database.db import get_admin_kpi_summary
from app.lexicon.lexicon_ru import (
    LEXICON_ADMIN_BUTTONS_RU,
    LEXICON_ADMIN_RU,
    LEXICON_RU,
)
from config.config import Config

router = make_admin_router()


@router.message(Command(commands=["admin"]))
async def admin_panel(message: Message) -> None:
    await message.answer(
        text=f"Здорова {message.from_user.first_name}. Снизу админ-панель. Чего изволите?",
        reply_markup=create_admin_panel_keyboard(),
    )


@router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["statistics_button"])
async def admin_users_button_press(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
    config: Config,
) -> None:
    s = await state.get_state()
    if in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if in_moderation_state(s):
        await state.set_state(None)
    kpi = await get_admin_kpi_summary(conn)
    await message.answer(
        format_admin_kpi_html(kpi, grafana_url=config.grafana.url),
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
        disable_web_page_preview=True,
    )


@router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["exit_button"])
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


@router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["newsletter_button"])
async def admin_get_message_start(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        "Ок.\r\n"
        "Отправь мне сообщение, которое будет использовано как рекламное.\r\n"
        "Можешь использовать текст, одно фото/видео или альбом (до 10 фото/видео).",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminMailing.get_message)


@router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["ban_user_button"])
async def admin_ban_button_press(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        LEXICON_ADMIN_RU["admin_panel_enter_ban"],
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminPanel.waiting_ban_input)


@router.message(F.text == LEXICON_ADMIN_BUTTONS_RU["unban_user_button"])
async def admin_unban_button_press(message: Message, state: FSMContext) -> None:
    s = await state.get_state()
    if in_mailing_fsm_state(s):
        await message.answer(LEXICON_ADMIN_RU["admin_mailing_in_progress"])
        return
    if in_moderation_state(s):
        await state.set_state(None)
    await message.answer(
        LEXICON_ADMIN_RU["admin_panel_enter_unban"],
        parse_mode="HTML",
        reply_markup=create_admin_panel_keyboard(),
    )
    await state.set_state(FSMAdminPanel.waiting_unban_input)
