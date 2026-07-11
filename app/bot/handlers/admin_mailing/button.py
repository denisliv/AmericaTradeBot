"""Handlers configuring the inline button under the mailing (or skipping it)."""

from aiogram import Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.admin_mailing._common import (
    DEFAULT_CHANNEL_BUTTON_TEXT,
    DEFAULT_CHANNEL_URL,
    admin_confirm,
    make_admin_router,
)
from app.bot.states.admin_mailing import FSMAdminMailing
from app.infrastructure.services.admin_mailing_sender import (
    build_mailing_button_keyboard,
)

router = make_admin_router()


@router.callback_query(StateFilter(FSMAdminMailing.get_button))
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
            added = build_mailing_button_keyboard(
                DEFAULT_CHANNEL_BUTTON_TEXT, DEFAULT_CHANNEL_URL
            )
            await admin_confirm(
                callback.message, bot, chat_id, added, state_data=data, state=state
            )

    await callback.answer()


@router.message(StateFilter(FSMAdminMailing.get_button_text))
async def admin_get_button_text(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Теперь отправь ссылку на ресурс, на который кнопка будет вести."
    )
    await state.update_data(text_button=message.text)
    await state.set_state(FSMAdminMailing.get_button_url)


@router.message(StateFilter(FSMAdminMailing.get_button_url))
async def admin_get_button_url(message: Message, bot: Bot, state: FSMContext) -> None:
    await state.update_data(url_button=message.text)
    data = await state.get_data()
    text_button = data.get("text_button")
    chat_id = int(data.get("chat_id"))
    is_album = data.get("is_album", False)

    added = build_mailing_button_keyboard(text_button, message.text)
    if is_album:
        await message.answer("Введите текст, который будет отображаться над кнопкой:")
        await state.set_state(FSMAdminMailing.get_button_message_text)
    else:
        await admin_confirm(message, bot, chat_id, added, state_data=data, state=state)


@router.message(StateFilter(FSMAdminMailing.get_button_message_text))
async def admin_get_button_message_text(
    message: Message, bot: Bot, state: FSMContext
) -> None:
    await state.update_data(button_message_text=message.text or "👇")
    data = await state.get_data()
    text_button = data.get("text_button")
    url_button = data.get("url_button")
    chat_id = int(data.get("chat_id"))

    added = build_mailing_button_keyboard(text_button, url_button)
    await admin_confirm(message, bot, chat_id, added, state_data=data, state=state)
