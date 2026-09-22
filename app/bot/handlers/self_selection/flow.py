"""FSM-flow self_selection: brand → model → year → auction_status (+ manual request)."""

import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from psycopg.connection_async import AsyncConnection

from app.bot.callback_data import STEP_BACK_PREFIX, SubscribeCB
from app.bot.handlers.consultation_request import set_lead_context
from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_self_lead_keyboard,
    create_self_results_keyboard,
)
from app.bot.states.states import FSMFillSelfSelectionForm
from app.bot.utils.media import safe_send_media_group
from app.infrastructure.database.selections import add_self_selection_request
from app.infrastructure.services.car_media import make_media_group
from app.infrastructure.services.salesdata import get_data
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

router = Router()

# Год "до 2016" ведет сразу на экран консультации, поиск по CSV не выполняется
_OLD_YEAR_KEY = "до 2016"

# Пробег больше не спрашиваем (шага нет на диаграмме Miro): фильтр отключен
_ANY_ODOMETER = "Не имеет значения"


def _create_brand_keyboard():
    return create_choice_keyboard(
        *LEXICON_FORM_BUTTONS_RU["brand_buttons"],
        "manual_option_button",
        (f"{STEP_BACK_PREFIX}start", "back_button"),
        width=2,
    )


async def show_brand_step(message: Message, state: FSMContext) -> None:
    """Screen "выберите марку" - the first step of the brand/model branch."""
    await message.edit_text(
        text="Выберите марку автомобиля:",
        reply_markup=_create_brand_keyboard(),
    )
    await state.set_state(FSMFillSelfSelectionForm.get_brand)


async def show_model_step(message: Message, state: FSMContext, brand: str) -> None:
    """Screen "выберите модель" for the given brand."""
    model_buttons = LEXICON_FORM_BUTTONS_RU["model_buttons"][brand]
    model_entries = [
        ("ALL MODELS", "any_model_button") if model == "ALL MODELS" else model
        for model in model_buttons
    ]
    await message.edit_text(
        text="Выберите модель автомобиля:",
        reply_markup=create_choice_keyboard(
            *model_entries,
            "manual_option_button",
            (f"{STEP_BACK_PREFIX}brand", "back_button"),
            width=2,
        ),
    )
    await state.update_data(brand=brand)
    await state.set_state(FSMFillSelfSelectionForm.get_model)


async def show_year_step(message: Message, state: FSMContext) -> None:
    """Screen "выберите год выпуска"."""
    await message.edit_text(
        text="Выберите год выпуска автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["year_buttons"],
            (f"{STEP_BACK_PREFIX}model", "back_button"),
            width=1,
        ),
    )
    await state.set_state(FSMFillSelfSelectionForm.get_year)


async def show_auction_status_step(message: Message, state: FSMContext) -> None:
    """Screen "какие варианты хотели бы увидеть" - BUY NOW or everything."""
    await message.edit_text(
        text="Какие варианты хотели бы увидеть?",
        reply_markup=create_choice_keyboard(
            *(
                (callback_data, text_key, ButtonStyle.PRIMARY)
                for callback_data, text_key in LEXICON_FORM_BUTTONS_RU[
                    "auction_status_buttons"
                ]
            ),
            (f"{STEP_BACK_PREFIX}year", "back_button"),
            width=1,
        ),
    )
    await state.set_state(FSMFillSelfSelectionForm.get_auction_status)


async def _prompt_manual_request(
    callback: CallbackQuery, state: FSMContext, *, back_target: str
) -> None:
    """Кнопка "Другое": просим описать запрос свободным текстом.

    Args:
        callback: Нажатие кнопки "Другое".
        state: FSM пользователя.
        back_target: Экран, на который вернет "Назад" (шаг, откуда пришли).
    """
    await callback.message.edit_text(
        text=LEXICON_RU["manual_request_text"],
        reply_markup=create_choice_keyboard(
            (f"{STEP_BACK_PREFIX}{back_target}", "back_button"), width=1
        ),
    )
    await callback.answer()
    await state.set_state(FSMFillSelfSelectionForm.get_manual_request)


@router.callback_query(
    F.data.in_({"knowing_button", "change_request_button"}),
    flags={"blocking": "blocking"},
)
async def process_new_search_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await show_brand_step(callback.message, state)
    await callback.answer()


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_brand))
async def process_brand_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.data == "manual_option_button":
        await _prompt_manual_request(callback, state, back_target="brand")
        return

    if callback.data not in LEXICON_FORM_BUTTONS_RU["model_buttons"]:
        await callback.answer(
            "Марка не найдена, выберите вариант из списка", show_alert=True
        )
        await show_brand_step(callback.message, state)
        return

    await callback.answer()
    await show_model_step(callback.message, state, callback.data)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_model))
async def process_model_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    if callback.data == "manual_option_button":
        await _prompt_manual_request(callback, state, back_target="model")
        return

    await callback.answer()
    await state.update_data(model=callback.data)
    await show_year_step(callback.message, state)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_year))
async def process_year_button_press(callback: CallbackQuery, state: FSMContext):
    await state.update_data(year=callback.data)

    if callback.data == _OLD_YEAR_KEY:
        # Старые года не ищем на аукционе - сразу предлагаем консультацию
        user_dict = await state.get_data()
        await callback.message.edit_text(
            text=LEXICON_RU["old_year_lead_text"],
            reply_markup=create_choice_keyboard(
                ("send_phone_inline", "send_my_phone_button", ButtonStyle.SUCCESS),
                width=1,
            ),
        )
        await callback.answer()
        await set_lead_context(
            state,
            brand=user_dict.get("brand", ""),
            model=user_dict.get("model", ""),
            year=_OLD_YEAR_KEY,
        )
        await state.set_state(None)
        return

    await show_auction_status_step(callback.message, state)
    await callback.answer()


@router.callback_query(
    StateFilter(FSMFillSelfSelectionForm.get_auction_status),
    flags={"long_operation": "typing"},
)
async def process_auction_status_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await state.update_data(auction_status=callback.data)

    await callback.answer(
        text="Подбираем варианты под Ваши критерии. Это не займет много времени...",
        show_alert=True,
    )

    user_dict = await state.get_data()
    user_dict["odometer"] = _ANY_ODOMETER

    await add_self_selection_request(
        conn,
        user_id=callback.from_user.id,
        brand=user_dict["brand"],
        model=user_dict["model"],
        year=user_dict["year"],
        odometer=_ANY_ODOMETER,
        auction_status=user_dict["auction_status"],
    )
    # brand/model/year остаются в данных FSM: они нужны для контекста Bitrix-лида
    await state.set_state(None)

    data = await get_data(user_dict=user_dict, conn=conn, count=10)
    if not data:
        await callback.message.answer(
            text=LEXICON_RU["nothing_found_text"],
            reply_markup=create_choice_keyboard(
                (SubscribeCB(source="self"), "follow_model_button"),
                "change_request_button",
                ("self_request_button", ButtonStyle.SUCCESS),
                width=1,
            ),
        )
        return

    number = 1
    for car in data[:3]:
        media_group = await make_media_group(
            car, callback.from_user.first_name or "Пользователь", number
        )
        if await safe_send_media_group(callback, media_group, number, car):
            number += 1
        await asyncio.sleep(0.2)

    await state.update_data(
        else_data=data[3:],
        number=number,
        search_type="self",
    )

    await callback.message.answer(
        text=LEXICON_RU["cars_describe_text"],
        # Первые 3 лота уже показаны: кнопка нужна, только если есть остаток
        reply_markup=create_self_results_keyboard(else_car=len(data) > 3),
    )


# Этот хэндлер будет срабатывать на текст запроса после кнопки "Другое"
@router.message(StateFilter(FSMFillSelfSelectionForm.get_manual_request), F.text)
async def process_manual_request_input(message: Message, state: FSMContext):
    await message.answer(
        text=LEXICON_RU["self_lead_intro_text"],
        reply_markup=create_self_lead_keyboard(),
    )
    await set_lead_context(state, request_details=message.text)
    await state.set_state(None)
