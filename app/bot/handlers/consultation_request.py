from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.bot.states.states import FSMFillConsultationRequestForm
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.lexicon.lexicon_ru import LEXICON_RU

consultation_request_router: Router = Router()


# Этот хэндлер будет срабатывать на кнопку "Оставить заявку на бесплатный подбор"
# и переводить бота в состояние ожидания ввода имени
@consultation_request_router.callback_query(
    F.data == "application_for_selection_button"
)
async def process_application_for_selection_button_press(
    callback: CallbackQuery, state: FSMContext
):
    msg = await callback.message.edit_text(
        text=LEXICON_RU["application_for_selection_text"]
    )
    await state.update_data(old_message_id=msg.message_id)
    await state.set_state(FSMFillConsultationRequestForm.get_name)


# Этот хэндлер будет срабатывать на ввод имени
# и переводить бота в состояние ожидания ввода телефона
@consultation_request_router.message(
    StateFilter(FSMFillConsultationRequestForm.get_name)
)
async def process_name_input(
    message,
    state: FSMContext,
    bot: Bot,
):
    data = await state.get_data()
    old_message_id = data.get("old_message_id")
    await bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await message.delete()
    msg = await message.answer(
        text=LEXICON_RU["choose_phone_request_text"],
        reply_markup=create_call_request_keyboard(),
    )
    await state.update_data(name=message.text)
    await state.update_data(old_message_id=msg.message_id)
    await state.set_state(FSMFillConsultationRequestForm.get_phone)


# Этот хэндлер будет срабатывать на ввод телефона
# и завершать процесс подачи заявки
@consultation_request_router.message(
    StateFilter(FSMFillConsultationRequestForm.get_phone)
)
async def process_phone_input(message, state: FSMContext, bot: Bot):
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
        )

        await message.answer(
            text=LEXICON_RU["phone_request_answer_text_v2"],
            reply_markup=create_choice_keyboard(
                "back_to:main_menu",
                "contact_button",
            ),
        )

        await state.clear()

    except AttributeError:
        await message.delete()
        await message.answer(
            text="Это не номер телефона. Нажмите <b>Отправить номер телефона</b> на клавиатуре снизу"
        )
        await state.set_state(FSMFillConsultationRequestForm.get_phone)
