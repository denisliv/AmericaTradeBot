"""Subscription and pagination (else_car) handlers in the self_selection flow."""

import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.callback_data import SubscribeCB
from app.bot.keyboards.keyboards_inline import (
    create_auto_keyboard,
    create_choice_keyboard,
)
from app.infrastructure.database.db import record_metric_event, set_subscription
from app.infrastructure.services.utils import (
    make_media_group,
    safe_send_media_group,
)
from app.lexicon.lexicon_ru import LEXICON_RU

router = Router()


@router.callback_query(SubscribeCB.filter(F.source == "self"))
async def process_subscription_button_press(
    callback: CallbackQuery,
    state: FSMContext,
    conn: AsyncConnection,
):
    await state.clear()
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


@router.callback_query(
    F.data == "else_car_button_self", flags={"long_operation": "typing"}
)
async def process_else_car_button_press(
    callback: CallbackQuery,
    state: FSMContext,
):
    await callback.answer()

    user_data = await state.get_data()
    else_data = user_data.get("else_data", [])
    number = user_data.get("number", 1)

    if not else_data:
        await callback.message.answer(
            text=LEXICON_RU["no_more_cars_text"],
            reply_markup=create_choice_keyboard(
                "new_search_button_self",
                ("application_for_selection_button", ButtonStyle.SUCCESS),
                (SubscribeCB(source="self"), "subscription_button"),
                width=1,
            ),
        )
        return

    cars_to_show = else_data[:3]
    for car in cars_to_show:
        media_group = await make_media_group(
            car, callback.from_user.first_name or "Пользователь", number
        )
        if await safe_send_media_group(callback, media_group, number, car):
            number += 1
        await asyncio.sleep(0.2)

    remaining_data = else_data[3:]
    await state.update_data(
        else_data=remaining_data,
        number=number,
        search_type="self",
    )

    await callback.message.answer(
        text=LEXICON_RU["cars_describe_text"],
        reply_markup=create_auto_keyboard(
            else_car=len(remaining_data) > 0, search_type="self"
        ),
    )
