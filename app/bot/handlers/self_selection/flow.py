"""FSM-flow self_selection: brand → model → year → odometer → auction_status."""

import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.callback_data import SubscribeCB
from app.bot.keyboards.keyboards_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
)
from app.bot.states.states import FSMFillSelfSelectionForm
from app.bot.utils.media import safe_send_media_group
from app.infrastructure.database.selections import add_self_selection_request
from app.infrastructure.services.car_media import make_media_group
from app.infrastructure.services.salesdata import get_data
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

router = Router()


@router.callback_query(
    F.data.in_({"knowing_button", "new_search_button_self"}),
    flags={"blocking": "blocking"},
)
async def process_new_search_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.clear()
    await callback.message.edit_text(
        text="Укажите марку автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["brand_buttons"], width=2
        ),
    )
    await callback.answer()
    await state.set_state(FSMFillSelfSelectionForm.get_brand)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_brand))
async def process_brand_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    model_buttons = LEXICON_FORM_BUTTONS_RU["model_buttons"].get(callback.data)
    if model_buttons is None:
        await callback.answer(
            "Марка не найдена, выберите вариант из списка", show_alert=True
        )
        await callback.message.edit_text(
            text="Укажите марку автомобиля:",
            reply_markup=create_choice_keyboard(
                *LEXICON_FORM_BUTTONS_RU["brand_buttons"], width=2
            ),
        )
        await state.set_state(FSMFillSelfSelectionForm.get_brand)
        return

    await callback.answer(
        text="""При выборе объема двигателя учитывайте,
что на данный момент в связи с введенными санкциями,
авто с объемом до 1.9 доставляются через Клайпеду (Литва),
а авто объемом выше 1.9 - через Поти (Грузия)""",
        show_alert=True,
    )
    await callback.message.edit_text(
        text="Укажите модель автомобиля:",
        reply_markup=create_choice_keyboard(*model_buttons, width=2),
    )
    await state.update_data(brand=callback.data)
    await state.set_state(FSMFillSelfSelectionForm.get_model)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_model))
async def process_model_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer(
        text="""Наиболее выгодными предложениями для покупки авто из-за границы
являются варианты 2021-2023 годов выпуска (от 3 до 5 лет)""",
        show_alert=True,
    )
    await callback.message.edit_text(
        text="Укажите год выпуска автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["year_buttons"], width=1
        ),
    )
    await state.update_data(model=callback.data)
    await state.set_state(FSMFillSelfSelectionForm.get_year)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_year))
async def process_year_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Укажите желаемый пробег автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["odometer_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.update_data(year=callback.data)
    await state.set_state(FSMFillSelfSelectionForm.get_odometer)


@router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_odometer))
async def process_drive_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.message.edit_text(
        text="Какие варианты хотели бы увидеть?",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["auction_status_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.update_data(odometer=callback.data)
    await state.set_state(FSMFillSelfSelectionForm.get_auction_status)


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

    await add_self_selection_request(
        conn,
        user_id=callback.from_user.id,
        brand=user_dict["brand"],
        model=user_dict["model"],
        year=user_dict["year"],
        odometer=user_dict["odometer"],
        auction_status=user_dict["auction_status"],
    )
    await state.clear()

    data = await get_data(user_dict=user_dict, count=10)
    if not data:
        await callback.message.answer(
            text=LEXICON_RU["nothing_found_text"],
            reply_markup=create_choice_keyboard(
                (SubscribeCB(source="self"), "subscription_button"),
                "new_search_button_self",
                ("application_for_selection_button", ButtonStyle.SUCCESS),
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
        reply_markup=create_auto_keyboard(else_car=len(data) > 0, search_type="self"),
    )
