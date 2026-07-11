"""Auto-selection lead handlers: chosen lot / free request → phone capture screen."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.handlers.consultation_request import set_lead_context
from app.bot.keyboards.keyboards_inline import create_self_lead_keyboard
from app.lexicon.lexicon_ru import LEXICON_RU

router = Router()


# Этот хэндлер будет срабатывать на кнопку "📋 Получить детальный расчет Авто № N":
# помечает выбранную карточку и показывает экран запроса телефона последним
# сообщением; выбранное авто уходит в комментарий Bitrix-лида
@router.callback_query(F.data.startswith("Лот №:"))
async def process_auto_press(callback: CallbackQuery, state: FSMContext):
    # Формат callback: "Лот №: {lot}-{Make}-{Model Detail}"
    lot_description = callback.data.split("-")
    lot_number = lot_description[0][7:]
    car_title = " ".join(lot_description[1:])

    data = await state.get_data()
    # Нажатая кнопка заменяется отметкой выбора, экран телефона приходит
    # новым сообщением внизу чата - иначе он теряется среди других карточек
    await callback.message.edit_text(text=LEXICON_RU["car_selected_text"](car_title))
    await callback.message.answer(
        text=LEXICON_RU["self_lead_intro_text"],
        reply_markup=create_self_lead_keyboard(),
    )
    await set_lead_context(
        state,
        brand=data.get("brand", ""),
        model=data.get("model", ""),
        year=data.get("year", ""),
        lot=lot_number,
        car_title=car_title,
    )
    await callback.answer()


# Этот хэндлер будет срабатывать на кнопку "Оставить заявку на бесплатный подбор"
# на экранах результатов: выбранные критерии (марка/модель/год либо кузов/бюджет)
# уходят в комментарий Bitrix-лида
@router.callback_query(F.data == "self_request_button")
async def process_self_request_press(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text(
        text=LEXICON_RU["self_lead_intro_text"],
        reply_markup=create_self_lead_keyboard(),
    )
    await set_lead_context(
        state,
        brand=data.get("brand", ""),
        model=data.get("model", ""),
        year=data.get("year", ""),
        body_style=data.get("body_style", ""),
        budget=data.get("budget", ""),
    )
    await callback.answer()
