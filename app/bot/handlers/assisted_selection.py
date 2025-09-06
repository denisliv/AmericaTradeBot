import asyncio

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
)
from app.bot.states.states import FSMFillAssistedSelectionForm
from app.infrastructure.database.db import (
    add_assisted_selection_request,
    set_subscription,
)
from app.infrastructure.services.utils import (
    get_assisted_data,
    make_media_group,
    safe_send_media_group,
)
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

assisted_selection_router: Router = Router()


# Этот хэндлер будет срабатывать на кнопку "Нужна помощь в выборе"
# и переводить бота в состояние ожидания выбора кузова
@assisted_selection_router.callback_query(
    F.data.in_({"advice_button", "new_search_button_assisted"}),
    flags={"blocking": "blocking"},
)
async def process_advice_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Укажите предпочтительный кузов автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["body_style_buttons"], width=1
        ),
    )
    await state.set_state(FSMFillAssistedSelectionForm.get_body_style)


# Этот хэндлер будет срабатывать, если выбран кузов
# и переводить бота в состояние ожидания выбора бюджета
@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_body_style)
)
async def process_body_type_button_press(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text="Укажите в какой бюджет планируете покупку:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["budget_buttons"], width=1
        ),
    )
    await state.update_data(body_style=callback.data)
    await state.set_state(FSMFillAssistedSelectionForm.get_budget)


# Этот хэндлер будет срабатывать, если выбран бюджет
# и показывать топ-3 автомобиля
@assisted_selection_router.callback_query(
    StateFilter(FSMFillAssistedSelectionForm.get_budget),
    flags={"long_operation": "typing"},
)
async def process_budget_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await state.update_data(budget=callback.data)

    # Отвечаем на callback после начала длительной операции
    await callback.answer(
        text="Подбираем варианты под Ваши критерии. Это не займет много времени...",
        show_alert=True,
    )

    user_dict = await state.get_data()

    await add_assisted_selection_request(
        conn,
        user_id=callback.from_user.id,
        body_style=user_dict["body_style"],
        budget=user_dict["budget"],
    )
    await state.clear()

    data = await get_assisted_data(user_dict=user_dict, count=10)
    if not data:
        await callback.message.answer(
            text=LEXICON_RU["nothing_found_text"],
            reply_markup=create_choice_keyboard(
                "assisted_subscription_button",
                "new_search_button_assisted",
                "application_for_selection_button",
                width=1,
            ),
        )
        return

    data_buttons = []
    number = 1

    # Показываем первые 3 авто
    for car in data[:3]:
        media_group = await make_media_group(
            car, callback.from_user.first_name or "Пользователь", number
        )
        btn = await safe_send_media_group(callback, media_group, number, car)
        if btn:
            data_buttons.append(btn)
            number += 1
        await asyncio.sleep(0.2)

    # Сохраняем оставшиеся авто и кнопки
    await state.update_data(
        else_data=data[3:],
        old_data_buttons=data_buttons,
        number=number,
        search_type="assisted",
    )

    await callback.message.answer(
        text=LEXICON_RU["top_cars_text"],
        reply_markup=create_auto_keyboard(
            data_buttons, else_car=len(data) > 3, search_type="assisted"
        ),
    )


# Этот хэндлер будет срабатывать на нажатие кнопки "Подписаться" в контексте assisted selection
@assisted_selection_router.callback_query(F.data == "assisted_subscription_button")
async def process_subscription_button_press(
    callback: CallbackQuery,
    conn: AsyncConnection,
):
    limit = 6
    count = limit - await set_subscription(
        conn,
        user_id=callback.from_user.id,
        limit=limit,
        table="assisted_selection_requests",
    )

    if count != 0:
        await callback.message.edit_text(
            text=LEXICON_RU["yes_subscription_text"](count),
            reply_markup=create_choice_keyboard(
                "back_to:main_menu", "new_search_button_assisted"
            ),
        )
    else:
        await callback.message.edit_text(
            text=LEXICON_RU["no_subscription_text"](count),
            reply_markup=create_choice_keyboard(
                "back_to:main_menu", "new_search_button_assisted"
            ),
        )
    await callback.answer()


# Этот хэндлер будет срабатывать на нажатие кнопки "Еще варианты"
# и показывать следующие 3 автомобиля
@assisted_selection_router.callback_query(
    F.data == "else_car_button_assisted", flags={"long_operation": "typing"}
)
async def process_else_car_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    # Отвечаем на callback в начале
    await callback.answer()

    # Получаем сохраненные данные
    user_data = await state.get_data()
    else_data = user_data.get("else_data", [])
    old_data_buttons = user_data.get("old_data_buttons", [])
    number = user_data.get("number", 1)

    if not else_data:
        await callback.message.answer(
            text=LEXICON_RU["no_more_cars_text"],
            reply_markup=create_choice_keyboard(
                "new_search_button_assisted",
                "application_for_selection_button",
                "assisted_subscription_button",
                width=1,
            ),
        )
        return

    new_data_buttons = []

    # Показываем следующие 3 авто (или меньше, если осталось меньше 3)
    cars_to_show = else_data[:3]
    for car in cars_to_show:
        media_group = await make_media_group(
            car, callback.from_user.first_name or "Пользователь", number
        )
        btn = await safe_send_media_group(callback, media_group, number, car)
        if btn:
            new_data_buttons.append(btn)
            number += 1
        await asyncio.sleep(0.2)

    # Объединяем старые и новые кнопки
    all_data_buttons = old_data_buttons + new_data_buttons

    # Обновляем сохраненные данные
    remaining_data = else_data[3:]
    await state.update_data(
        else_data=remaining_data,
        old_data_buttons=all_data_buttons,
        number=number,
        search_type="assisted",
    )

    # Отправляем обновленную клавиатуру
    await callback.message.answer(
        text=LEXICON_RU["top_cars_text"],
        reply_markup=create_auto_keyboard(
            all_data_buttons, else_car=len(remaining_data) > 0, search_type="assisted"
        ),
    )
