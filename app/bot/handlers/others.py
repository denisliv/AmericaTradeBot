from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import create_contact_received_keyboard
from app.config import Config
from app.infrastructure.database.nurture import set_nurture_shift
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.lexicon.lexicon_ru import LEXICON_RU

others_router: Router = Router()


# Этот хэндлер будет реагировать на отправку телефонного номера вне флоу заявки
# (например, reply-кнопкой из старого сообщения): контакт все равно уходит в Bitrix
@others_router.message(F.contact)
async def call_request_answer(
    message: Message,
    state: FSMContext,
    config: Config,
    conn: AsyncConnection,
):
    await bitrix_send_data(
        tg_login=message.from_user.username,
        tg_id=message.from_user.id,
        data={
            "name": message.from_user.first_name,
            "phone": message.contact.phone_number,
        },
        method="consultation_request",
        webhook_url=config.bitrix.webhook_url,
    )

    # Заявка оставлена: еще не отправленные шаги рассылки смещаются на 3 дня
    await set_nurture_shift(conn, user_id=message.from_user.id)

    await message.answer(
        text=LEXICON_RU["contact_received_text"],
        reply_markup=create_contact_received_keyboard(),
    )
    await state.clear()


# Этот хэндлер будет реагировать на любые сообщения пользователя,
# не предусмотренные логикой работы бота
@others_router.message()
async def other_fsm_answer(message: Message):
    await message.answer(text=LEXICON_RU["unknown_message_hint_text"])
