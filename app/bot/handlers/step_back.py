"""Кнопка "Назад" на шагах выбора критериев подбора.

Роутер подключается первым: хэндлеры шагов ловят в своём состоянии любой
callback и приняли бы "Назад" за выбранную марку или тип кузова.
"""

import logging
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callback_data import STEP_BACK_PREFIX
from app.bot.handlers.assisted_selection import show_body_style_step
from app.bot.handlers.self_selection.flow import (
    show_brand_step,
    show_model_step,
    show_year_step,
)
from app.bot.keyboards.keyboards_inline import create_choose_a_car_keyboard
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

logger = logging.getLogger(__name__)

step_back_router = Router()


async def _show_start(message: Message, state: FSMContext, data: dict) -> None:
    """Экран "Вы уже определились" - начало подбора."""
    await state.clear()
    await message.edit_text(
        text=LEXICON_RU["choose_a_car_text"],
        reply_markup=create_choose_a_car_keyboard(),
    )


async def _show_model(message: Message, state: FSMContext, data: dict) -> None:
    brand = data.get("brand")
    if brand in LEXICON_FORM_BUTTONS_RU["model_buttons"]:
        await show_model_step(message, state, brand)
        return
    # Марки нет в данных FSM или она устарела - возвращаем на шаг выше
    await show_brand_step(message, state)


# Экран, на который возвращает "Назад". Ключи используются в callback_data
# кнопок: TARGETS и клавиатуры шагов обязаны совпадать (см. тесты).
TARGETS: dict[str, Callable[[Message, FSMContext, dict], Awaitable[None]]] = {
    "start": _show_start,
    "brand": lambda message, state, data: show_brand_step(message, state),
    "model": _show_model,
    "year": lambda message, state, data: show_year_step(message, state),
    "body_style": lambda message, state, data: show_body_style_step(message, state),
}


@step_back_router.callback_query(F.data.startswith(STEP_BACK_PREFIX))
async def process_step_back(callback: CallbackQuery, state: FSMContext):
    """Возврат на предыдущий шаг подбора с восстановлением состояния FSM."""
    target = callback.data[len(STEP_BACK_PREFIX) :]
    show_step = TARGETS.get(target)
    if show_step is None:
        logger.warning("Unknown step_back target: %s", target)
        await callback.answer()
        return

    await show_step(callback.message, state, await state.get_data())
    await callback.answer()
