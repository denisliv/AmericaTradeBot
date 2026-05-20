"""Auto-selection lead handlers: choose lot, phone form, Bitrix submit."""

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.bot.states.states import FSMFillPhoneForm
from app.infrastructure.database.db import record_metric_event
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.lexicon.lexicon_ru import LEXICON_RU

router = Router()


@router.callback_query(F.data.startswith("Лот №:"))
async def process_auto_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    if conn is not None:
        await record_metric_event(
            conn,
            event_name="self_clicked_lot",
            user_id=callback.from_user.id,
        )
    data = {"name": callback.from_user.first_name, "lot": callback.data}
    if callback.from_user.username:
        if conn is not None:
            await record_metric_event(
                conn,
                event_name="self_lead_sent",
                user_id=callback.from_user.id,
            )
        await bitrix_send_data(
            tg_login=callback.from_user.username,
            tg_id=callback.from_user.id,
            data=data,
            method="self_selection",
        )
        await callback.message.edit_text(
            text=LEXICON_RU["phone_request_answer_text"],
            reply_markup=create_choice_keyboard(
                "back_to:main_menu",
                "contact_button",
            ),
        )
    else:
        msg = await callback.message.answer(
            text=LEXICON_RU["choose_phone_request_text"],
            reply_markup=create_call_request_keyboard(),
        )
        await state.update_data(old_message_id=msg.message_id)
        await state.update_data(data=data)
        await state.set_state(FSMFillPhoneForm.get_phone)

    await callback.answer()


@router.message(F.contact, StateFilter(FSMFillPhoneForm.get_phone))
async def process_phone_sent(
    message: Message,
    bot: Bot,
    state: FSMContext,
    conn: AsyncConnection,
):
    data = await state.get_data()
    old_message_id = data.get("old_message_id")
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()

    if data.get("bitrix_method") == "assisted_gallery":
        lead = {
            "name": data.get("name"),
            "phone": message.contact.phone_number,
            "car_title": data.get("car_title"),
            "body_style": data.get("body_style"),
            "budget": data.get("budget"),
        }
        await state.clear()
        await bitrix_send_data(
            tg_login=message.from_user.username,
            tg_id=message.from_user.id,
            data=lead,
            method="assisted_gallery",
        )
    else:
        data["phone"] = message.contact.phone_number
        await state.clear()
        if conn is not None:
            await record_metric_event(
                conn,
                event_name="self_lead_sent",
                user_id=message.from_user.id,
            )
        await bitrix_send_data(
            tg_login=message.from_user.username,
            tg_id=message.from_user.id,
            data=data,
            method="self_selection",
        )

    await message.answer(
        text=LEXICON_RU["phone_request_answer_text"],
        reply_markup=create_choice_keyboard(
            "back_to:main_menu",
            "contact_button",
        ),
    )
