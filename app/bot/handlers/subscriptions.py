import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_subscriptions_keyboard,
    format_date,
)
from app.infrastructure.database.db import (
    delete_subscription,
    get_self_selection_subscription_by_id,
    get_user_subscriptions,
    record_metric_event,
)
from app.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU

logger = logging.getLogger(__name__)

subscriptions_router = Router()


def _parse_subscription_callback_data(data: str, expected_prefix: str) -> tuple[str, int] | None:
    parts = data.split("_")
    if len(parts) != 4:
        return None
    if f"{parts[0]}_{parts[1]}" != expected_prefix:
        return None
    subscription_type = parts[2]
    if subscription_type != "self":
        return None
    try:
        subscription_id = int(parts[3])
    except (TypeError, ValueError):
        return None
    return subscription_type, subscription_id


# Этот хэндлер срабатывает на команду /subscription и callback back_to_subscriptions
@subscriptions_router.message(Command(commands="subscription"))
@subscriptions_router.callback_query(F.data == "back_to_subscriptions")
async def process_subscription_command(
    event: Message | CallbackQuery,
    conn,
    state: FSMContext,
):
    # Получаем user_id в зависимости от типа события
    user_id = event.from_user.id

    # Получаем подписки пользователя
    self_selection_subs = await get_user_subscriptions(conn, user_id=user_id)
    if len(self_selection_subs) == 0:
        # Нет подписок
        text = LEXICON_RU["no_subscriptions_text"]
        keyboard = create_choice_keyboard(
            "choose_a_car_button",
            "back_to:main_menu",
            width=1,
        )

        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text=text, reply_markup=keyboard)
            await event.answer()
        else:
            await event.answer(text=text, reply_markup=keyboard)
        return

    text = LEXICON_RU["subscriptions_list_text"]
    keyboard = create_subscriptions_keyboard(
        self_selection_subs=self_selection_subs,
        show_back_button=True,
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text=text, reply_markup=keyboard)
        await event.answer()
    else:
        await event.answer(text=text, reply_markup=keyboard)
    await state.clear()


# Этот хэндлер будет срабатывать на просмотр self selection подписок
@subscriptions_router.callback_query(F.data == "view_self_selection_subscriptions")
async def process_view_self_selection_subscriptions(
    callback: CallbackQuery,
    conn,
):
    # Получаем self selection подписки пользователя
    self_selection_subs = await get_user_subscriptions(
        conn, user_id=callback.from_user.id
    )

    text = LEXICON_RU["subscriptions_list_text"]

    # Используем новую функцию для создания клавиатуры
    keyboard = create_subscriptions_keyboard(
        self_selection_subs=self_selection_subs, show_back_button=True
    )

    await callback.message.edit_text(
        text=text,
        reply_markup=keyboard,
    )
    await callback.answer()


# Этот хэндлер будет срабатывать на просмотр подписки
@subscriptions_router.callback_query(F.data.startswith("view_subscription_"))
async def process_view_subscription(
    callback: CallbackQuery,
    conn,
):
    parsed = _parse_subscription_callback_data(
        callback.data, expected_prefix="view_subscription"
    )
    if parsed is None:
        await record_metric_event(
            conn,
            event_name="invalid_callback",
            user_id=callback.from_user.id,
        )
        await callback.answer("Некорректная подписка", show_alert=True)
        return
    subscription_type, subscription_id = parsed

    if subscription_type == "self":
        # Получаем данные self selection подписки
        row = await get_self_selection_subscription_by_id(
            conn, user_id=callback.from_user.id, subscription_id=subscription_id
        )
        if row is None:
            await process_view_self_selection_subscriptions(callback, conn)
            return
        brand, model, year, odometer, auction_status, created_at = row

        # Форматируем дату создания
        date_str = format_date(created_at)

        text = f"<b>Автомобиль: {brand} {model}</b>\n\n"
        text += f"• Модельный год: {year}\n"
        text += f"• Пробег: {odometer}\n"
        text += f"• Статус аукциона: {auction_status}\n"
        text += f"• Дата создания: {date_str}\n\n"

    # Добавляем кнопки
    buttons = [
        (
            LEXICON_BUTTONS_RU["delete_subscription_button"],
            f"delete_subscription_{subscription_type}_{subscription_id}",
        ),
        (
            LEXICON_BUTTONS_RU["back_to:more_info"],
            f"view_{subscription_type}_selection_subscriptions",
        ),
        (LEXICON_BUTTONS_RU["back_to:main_menu"], "back_to:main_menu"),
    ]

    kb_builder = InlineKeyboardBuilder()
    for button_text, callback_data in buttons:
        kb_builder.add(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )
    kb_builder.adjust(1)

    await callback.message.edit_text(
        text=text,
        reply_markup=kb_builder.as_markup(),
    )
    await callback.answer()


# Этот хэндлер будет срабатывать на удаление подписки
@subscriptions_router.callback_query(F.data.startswith("delete_subscription_"))
async def process_delete_subscription(
    callback: CallbackQuery,
    conn,
):
    parsed = _parse_subscription_callback_data(
        callback.data, expected_prefix="delete_subscription"
    )
    if parsed is None:
        await record_metric_event(
            conn,
            event_name="invalid_callback",
            user_id=callback.from_user.id,
        )
        await callback.answer("Некорректная подписка", show_alert=True)
        return
    subscription_type, subscription_id = parsed

    table = f"{subscription_type}_selection_requests"

    # Удаляем подписку
    success = await delete_subscription(
        conn,
        user_id=callback.from_user.id,
        subscription_id=subscription_id,
        table=table,
    )

    if success:
        await callback.answer("Подписка удалена", show_alert=True)
        await process_view_self_selection_subscriptions(callback, conn)
    else:
        await callback.answer("Ошибка при удалении подписки", show_alert=True)
