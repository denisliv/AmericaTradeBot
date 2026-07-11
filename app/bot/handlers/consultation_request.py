from aiogram import Bot, F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_contact_received_keyboard,
)
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.bot.states.states import FSMFillConsultationRequestForm
from app.config import Config
from app.infrastructure.database.nurture import set_nurture_shift
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.lexicon.lexicon_ru import LEXICON_RU

consultation_request_router: Router = Router()

# Все поля контекста заявки, попадающие в Bitrix-лид ("source" - откуда пришел)
_LEAD_CONTEXT_KEYS = (
    "body_style",
    "budget",
    "car_title",
    "brand",
    "model",
    "year",
    "lot",
    "request_details",
    "source",
)


async def set_lead_context(state: FSMContext, **fields: str) -> None:
    """Overwrite the whole Bitrix lead context in FSM data.

    Unset fields are reset to empty strings so that values from previous
    requests of the same user never leak into a new lead.
    """
    context = dict.fromkeys(_LEAD_CONTEXT_KEYS, "")
    context.update(fields)
    await state.update_data(**context)


async def start_consultation_phone_request(
    message,
    state: FSMContext,
    *,
    extra_data: dict | None = None,
) -> None:
    """Show the consultation intro screen with the two-step phone button.

    Args:
        message: Message used as a reply target.
        state: FSM context of the user.
        extra_data: Extra lead context (e.g. body_style/budget) stored in FSM data.
    """
    await message.answer(
        text=LEXICON_RU["consultation_intro_text"],
        reply_markup=create_choice_keyboard(
            ("send_phone_inline", "send_my_phone_button", ButtonStyle.SUCCESS),
            "back_to:main_menu",
            width=1,
        ),
    )
    await set_lead_context(state, **(extra_data or {}))
    await state.set_state(None)


# Этот хэндлер будет срабатывать на инлайн-кнопку "📞 Отправить мой номер"
# (экраны "👀 ..." ветки подбора по марке/модели): показывает reply-кнопку
# отправки контакта; контекст заявки уже лежит в FSM-данных
@consultation_request_router.callback_query(F.data == "send_phone_inline")
async def process_send_phone_inline_press(callback: CallbackQuery, state: FSMContext):
    msg = await callback.message.answer(
        text=LEXICON_RU["press_phone_button_text"],
        reply_markup=create_call_request_keyboard(text_key="send_my_phone_button"),
    )
    await callback.answer()
    await state.set_state(FSMFillConsultationRequestForm.get_phone)
    # intro_message_id - экран с кнопкой 📞: после отправки контакта он
    # редактируется в "Контакт получен"
    await state.update_data(
        name=callback.from_user.first_name,
        old_message_id=msg.message_id,
        intro_message_id=callback.message.message_id,
    )


# Этот хэндлер будет срабатывать на кнопку "✅ Оставить заявку на бесплатную консультацию"
# и показывать интро-экран с кнопками "📞 Отправить мой номер" и "В меню"
@consultation_request_router.callback_query(
    F.data == "application_for_selection_button"
)
async def process_application_for_selection_button_press(
    callback: CallbackQuery, state: FSMContext
):
    # Экран контактов - фото с подписью, его нельзя отредактировать в текст
    await callback.message.delete()
    await start_consultation_phone_request(callback.message, state)
    await callback.answer()


# Этот хэндлер будет срабатывать на CTA-кнопку в сообщениях прогревочной рассылки:
# сообщение рассылки остается, а лид в Bitrix помечается источником "рассылка"
@consultation_request_router.callback_query(F.data == "application_from_nurture")
async def process_application_from_nurture_press(
    callback: CallbackQuery, state: FSMContext
):
    await start_consultation_phone_request(
        callback.message, state, extra_data={"source": "nurture"}
    )
    await callback.answer()


# Этот хэндлер будет срабатывать на ввод телефона
# и завершать процесс подачи заявки
@consultation_request_router.message(
    StateFilter(FSMFillConsultationRequestForm.get_phone)
)
async def process_phone_input(
    message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    conn: AsyncConnection,
):
    try:
        await state.update_data(phone=message.contact.phone_number)
        data = await state.get_data()
        old_message_id = data.get("old_message_id")
        await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
        await message.delete()

        await bitrix_send_data(
            tg_login=message.from_user.username,
            tg_id=message.from_user.id,
            data=data,
            method="consultation_request",
            webhook_url=config.bitrix.webhook_url,
        )

        # Заявка оставлена: еще не отправленные шаги рассылки смещаются на 3 дня
        await set_nurture_shift(conn, user_id=message.from_user.id)

        received_text = LEXICON_RU["contact_received_text"]
        received_keyboard = create_contact_received_keyboard()
        # Экран с кнопкой 📞 заменяется на "Контакт получен", а не дублируется ниже
        intro_message_id = data.get("intro_message_id")
        replaced = False
        if intro_message_id:
            try:
                await bot.edit_message_text(
                    text=received_text,
                    chat_id=message.chat.id,
                    message_id=intro_message_id,
                    reply_markup=received_keyboard,
                )
                replaced = True
            except TelegramBadRequest:
                pass
        if not replaced:
            await message.answer(text=received_text, reply_markup=received_keyboard)

        await state.clear()

    except AttributeError:
        await message.delete()
        await message.answer(
            text="Это не номер телефона. Нажмите <b>📞 Отправить мой номер</b> на клавиатуре снизу"
        )
        await state.set_state(FSMFillConsultationRequestForm.get_phone)
