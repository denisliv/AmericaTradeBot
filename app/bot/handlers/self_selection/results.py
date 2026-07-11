"""Subscription and pagination (else_car) handlers in the self_selection flow."""

import asyncio

from aiogram import F, Router
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from psycopg.connection_async import AsyncConnection

from app.bot.callback_data import SubscribeCB
from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_self_results_keyboard,
)
from app.bot.utils.media import safe_send_media_group
from app.infrastructure.database.selections import (
    SubscriptionOutcome,
    set_subscription,
)
from app.infrastructure.services.car_media import make_media_group
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
    outcome, active_count = await set_subscription(
        conn,
        user_id=callback.from_user.id,
        limit=limit,
        table="self_selection_requests",
    )
    remaining = max(limit - active_count, 0)

    if outcome is SubscriptionOutcome.ACTIVATED:
        text = LEXICON_RU["yes_subscription_text"](remaining)
    elif outcome is SubscriptionOutcome.LIMIT_REACHED:
        text = LEXICON_RU["no_subscription_text"](remaining)
    elif outcome is SubscriptionOutcome.ALREADY_SUBSCRIBED:
        text = LEXICON_RU["already_subscribed_text"](remaining)
    else:
        text = LEXICON_RU["subscription_unavailable_text"]

    await callback.message.edit_text(
        text=text,
        reply_markup=create_choice_keyboard(
            "back_to:main_menu", "change_request_button"
        ),
    )
    await callback.answer()


@router.callback_query(
    F.data == "else_car_button_self",
    flags={"long_operation": "typing", "blocking": "blocking"},
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
                (SubscribeCB(source="self"), "follow_model_button"),
                "change_request_button",
                ("self_request_button", ButtonStyle.SUCCESS),
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
        reply_markup=create_self_results_keyboard(else_car=len(remaining_data) > 0),
    )
