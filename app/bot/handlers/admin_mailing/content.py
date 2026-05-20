"""Handlers receiving the mailing content (text / single media / album)."""

from aiogram import Bot, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.admin_mailing._common import (
    album_buffer,
    make_admin_router,
    process_album_after_delay,
)
from app.bot.keyboards.keyboards_inline import create_admin_keyboard
from app.bot.states.admin_mailing import FSMAdminMailing

router = make_admin_router()


@router.message(StateFilter(FSMAdminMailing.get_message), F.photo | F.video)
async def admin_get_button_media(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.media_group_id:
        async def _starter(mg_id: str) -> None:
            await process_album_after_delay(mg_id, state, bot, message.chat.id)

        await album_buffer.add(message.media_group_id, message, _starter)
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


@router.message(StateFilter(FSMAdminMailing.get_message))
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
