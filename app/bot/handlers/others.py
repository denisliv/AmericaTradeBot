from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards.keyboards_inline import create_url_keyboard
from app.lexicon.lexicon_ru import LEXICON_RU

others_router: Router = Router()


# Этот хэндлер будет реагировать на отправку телефонного номера
@others_router.message(F.contact)
async def call_request_answer(message: Message):
    await message.answer(
        text=LEXICON_RU["call_request_answer_text"], reply_markup=create_url_keyboard()
    )


# Этот хэндлер будет реагировать на любые сообщения пользователя,
# не предусмотренные логикой работы бота
@others_router.message()
async def other_fsm_answer(message: Message):
    await message.delete()
