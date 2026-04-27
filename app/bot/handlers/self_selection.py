import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
)
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.bot.states.states import FSMFillPhoneForm, FSMFillSelfSelectionForm
from app.infrastructure.database.db import add_self_selection_request, set_subscription
from app.infrastructure.database.db import record_metric_event
from app.infrastructure.services.bitrix_utils import bitrix_send_data
from app.infrastructure.services.utils import (
    get_data,
    make_media_group,
    safe_send_media_group,
)
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU

self_selection_router: Router = Router()


# Этот хэндлер будет срабатывать на кнопку "Новый поиск" в контексте self selection
@self_selection_router.callback_query(
    F.data.in_({"knowing_button", "new_search_button_self"}),
    flags={"blocking": "blocking"},
)
async def process_new_search_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await callback.message.edit_text(
        text="Укажите марку автомобиля:",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["brand_buttons"], width=2
        ),
    )
    await callback.answer()
    if conn is not None:
        await record_metric_event(
            conn,
            event_name="self_flow_started",
            user_id=callback.from_user.id,
        )
    await state.set_state(FSMFillSelfSelectionForm.get_brand)


# Этот хэндлер будет срабатывать, если введена марка
# и переводить бота в состояние ожидания выбора модели
@self_selection_router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_brand))
async def process_brand_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    model_buttons = LEXICON_FORM_BUTTONS_RU["model_buttons"].get(callback.data)
    if model_buttons is None:
        if conn is not None:
            await record_metric_event(
                conn,
                event_name="invalid_callback",
                user_id=callback.from_user.id,
            )
        await callback.answer("Марка не найдена, выберите вариант из списка", show_alert=True)
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


# Этот хэндлер будет срабатывать, если выбрана модель
# и переводить бота в состояние ожидания выбора года выпуска
@self_selection_router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_model))
async def process_model_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
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
    if conn is not None:
        await record_metric_event(
            conn,
            event_name="self_reached_year_step",
            user_id=callback.from_user.id,
        )
        if callback.data == "ALL MODELS":
            await record_metric_event(
                conn,
                event_name="self_all_models_selected",
                user_id=callback.from_user.id,
            )
    await state.set_state(FSMFillSelfSelectionForm.get_year)


# Этот хэндлер будет срабатывать, если выбран год выпуска
# и переводить бота в состояние ожидания выбора пробега
@self_selection_router.callback_query(StateFilter(FSMFillSelfSelectionForm.get_year))
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


# Этот хэндлер будет срабатывать, если выбран пробег
# и переводить бота в состояние ожидания выбора статуса аукциона
@self_selection_router.callback_query(
    StateFilter(FSMFillSelfSelectionForm.get_odometer)
)
async def process_drive_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await callback.message.edit_text(
        text="Какие варианты хотели бы увидеть?",
        reply_markup=create_choice_keyboard(
            *LEXICON_FORM_BUTTONS_RU["auction_status_buttons"], width=1
        ),
    )
    await callback.answer()
    await state.update_data(odometer=callback.data)
    if conn is not None:
        await record_metric_event(
            conn,
            event_name="self_reached_auction_step",
            user_id=callback.from_user.id,
        )
    await state.set_state(FSMFillSelfSelectionForm.get_auction_status)


# Этот хэндлер будет срабатывать, если выбран статус аукциона
# и выводить из машины состояний
@self_selection_router.callback_query(
    StateFilter(FSMFillSelfSelectionForm.get_auction_status),
    flags={"long_operation": "typing"},
)
async def process_auction_status_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await state.update_data(auction_status=callback.data)

    # Отвечаем на callback после начала длительной операции
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
    await record_metric_event(
        conn,
        event_name="self_completed_search",
        user_id=callback.from_user.id,
    )
    await record_metric_event(
        conn,
        event_name="self_search_with_results" if data else "self_search_without_results",
        user_id=callback.from_user.id,
    )
    if data:
        await record_metric_event(
            conn,
            event_name="self_cars_shown",
            user_id=callback.from_user.id,
            value=float(min(3, len(data))),
        )
    if not data:
        await callback.message.answer(
            text=LEXICON_RU["nothing_found_text"],
            reply_markup=create_choice_keyboard(
                "self_subscription_button",
                "new_search_button_self",
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
        search_type="self",
    )

    await callback.message.answer(
        text=LEXICON_RU["cars_describe_text"],
        reply_markup=create_auto_keyboard(
            data_buttons, else_car=len(data) > 0, search_type="self"
        ),
    )


# Этот хэндлер будет срабатывать на нажатие кнопки "Подписаться" в контексте self selection
@self_selection_router.callback_query(F.data == "self_subscription_button")
async def process_subscription_button_press(
    callback: CallbackQuery,
    conn: AsyncConnection,
):
    limit = 6
    count = limit - await set_subscription(
        conn,
        user_id=callback.from_user.id,
        limit=limit,
        table="self_selection_requests",
    )

    if count != 0:
        await record_metric_event(
            conn,
            event_name="self_subscription_created",
            user_id=callback.from_user.id,
        )
        await callback.message.edit_text(
            text=LEXICON_RU["yes_subscription_text"](count),
            reply_markup=create_choice_keyboard(
                "back_to:main_menu", "new_search_button_self"
            ),
        )
    else:
        await callback.message.edit_text(
            text=LEXICON_RU["no_subscription_text"](count),
            reply_markup=create_choice_keyboard(
                "back_to:main_menu", "new_search_button_self"
            ),
        )
    await callback.answer()


# Этот хэндлер будет срабатывать на нажатие кнопки "Еще варианты"
# и показывать следующие 3 автомобиля
@self_selection_router.callback_query(
    F.data == "else_car_button_self", flags={"long_operation": "typing"}
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
                "new_search_button_self",
                "application_for_selection_button",
                "self_subscription_button",
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
        search_type="self",
    )

    # Отправляем обновленную клавиатуру
    await callback.message.answer(
        text=LEXICON_RU["cars_describe_text"],
        reply_markup=create_auto_keyboard(
            all_data_buttons, else_car=len(remaining_data) > 0, search_type="self"
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки с выбором автомобиля
@self_selection_router.callback_query(F.data.startswith("Лот №:"))
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


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки с выбором автомобиля у пользователей без логина
@self_selection_router.message(F.contact, StateFilter(FSMFillPhoneForm.get_phone))
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
