"""Handlers for ban/unban moderation input."""

from aiogram import F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from psycopg import AsyncConnection

from app.bot.handlers.admin_mailing._common import (
    handle_panel_during_moderation_input,
    make_admin_router,
)
from app.bot.keyboards.admin_reply import create_admin_panel_keyboard
from app.bot.states.admin_panel import FSMAdminPanel
from app.bot.utils.admin_user_moderation import try_ban_user, try_unban_user

router = make_admin_router()


@router.message(StateFilter(FSMAdminPanel.waiting_ban_input), F.text)
async def admin_ban_id_input(
    message: Message, state: FSMContext, conn: AsyncConnection
) -> None:
    t = (message.text or "").strip()
    if await handle_panel_during_moderation_input(message, state, conn, t):
        return
    out = await try_ban_user(conn, t)
    await message.answer(out, reply_markup=create_admin_panel_keyboard())
    await state.set_state(None)


@router.message(StateFilter(FSMAdminPanel.waiting_unban_input), F.text)
async def admin_unban_id_input(
    message: Message, state: FSMContext, conn: AsyncConnection
) -> None:
    t = (message.text or "").strip()
    if await handle_panel_during_moderation_input(message, state, conn, t):
        return
    out = await try_unban_user(conn, t)
    await message.answer(out, reply_markup=create_admin_panel_keyboard())
    await state.set_state(None)


@router.message(StateFilter(FSMAdminPanel.waiting_ban_input), ~F.text)
async def admin_ban_id_non_text(message: Message) -> None:
    await message.answer(
        "Введите user_id или @username одним текстовым сообщением.",
        reply_markup=create_admin_panel_keyboard(),
    )


@router.message(StateFilter(FSMAdminPanel.waiting_unban_input), ~F.text)
async def admin_unban_id_non_text(message: Message) -> None:
    await message.answer(
        "Введите user_id или @username одним текстовым сообщением.",
        reply_markup=create_admin_panel_keyboard(),
    )
