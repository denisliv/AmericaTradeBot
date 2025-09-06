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
    get_assisted_selection_subscription_by_id,
    get_self_selection_subscription_by_id,
    get_user_subscriptions,
)
from app.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU

logger = logging.getLogger(__name__)

subscriptions_router = Router()


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
    self_selection_subs, assisted_selection_subs = await get_user_subscriptions(
        conn, user_id=user_id
    )

    total_subs = len(self_selection_subs) + len(assisted_selection_subs)

    if total_subs == 0:
        # Нет подписок
        text = LEXICON_RU["no_subscriptions_text"]
        keyboard = create_choice_keyboard(
            "choose_a_car_button",
            "back_to:main_menu",
            width=1,
        )

        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text=text, reply_markup=keyboard.as_markup())
            await event.answer()
        else:
            await event.answer(text=text, reply_markup=keyboard)
        return

    # Есть подписки - показываем текст и кнопки для каждого типа
    text = LEXICON_RU["subscriptions_text"]

    # Создаем кнопки для каждого типа подписки
    kb_builder = InlineKeyboardBuilder()

    # Кнопка для self selection подписок (если есть)
    if self_selection_subs:
        button_text = LEXICON_BUTTONS_RU["self_selection_subscription_button"]
        callback_data = "view_self_selection_subscriptions"
        kb_builder.add(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

    # Кнопка для assisted selection подписок (если есть)
    if assisted_selection_subs:
        button_text = LEXICON_BUTTONS_RU["assisted_selection_subscription_button"]
        callback_data = "view_assisted_selection_subscriptions"
        kb_builder.add(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

    kb_builder.adjust(1)  # По одной кнопке в строке

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text=text, reply_markup=kb_builder.as_markup())
        await event.answer()
    else:
        await event.answer(text=text, reply_markup=kb_builder.as_markup())
    await state.clear()


# Этот хэндлер будет срабатывать на просмотр self selection подписок
@subscriptions_router.callback_query(F.data == "view_self_selection_subscriptions")
async def process_view_self_selection_subscriptions(
    callback: CallbackQuery,
    conn,
):
    # Получаем self selection подписки пользователя
    self_selection_subs, _ = await get_user_subscriptions(
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


# Этот хэндлер будет срабатывать на просмотр assisted selection подписок
@subscriptions_router.callback_query(F.data == "view_assisted_selection_subscriptions")
async def process_view_assisted_selection_subscriptions(
    callback: CallbackQuery,
    conn,
):
    # Получаем assisted selection подписки пользователя
    _, assisted_selection_subs = await get_user_subscriptions(
        conn, user_id=callback.from_user.id
    )

    text = LEXICON_RU["subscriptions_list_text"]

    # Используем новую функцию для создания клавиатуры
    keyboard = create_subscriptions_keyboard(
        assisted_selection_subs=assisted_selection_subs, show_back_button=True
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
    # Парсим callback_data
    parts = callback.data.split("_")
    subscription_type = parts[2]  # self или assisted
    subscription_id = int(parts[3])

    if subscription_type == "self":
        # Получаем данные self selection подписки
        row = await get_self_selection_subscription_by_id(
            conn, user_id=callback.from_user.id, subscription_id=subscription_id
        )
        brand, model, year, odometer, auction_status, created_at = row

        # Форматируем дату создания
        date_str = format_date(created_at)

        text = f"<b>Автомобиль: {brand} {model}</b>\n\n"
        text += f"• Модельный год: {year}\n"
        text += f"• Пробег: {odometer}\n"
        text += f"• Статус аукциона: {auction_status}\n"
        text += f"• Дата создания: {date_str}\n\n"

    elif subscription_type == "assisted":
        # Получаем данные assisted selection подписки
        row = await get_assisted_selection_subscription_by_id(
            conn, user_id=callback.from_user.id, subscription_id=subscription_id
        )
        body_style, budget, created_at = row

        # Форматируем дату создания
        date_str = format_date(created_at)

        text = f"• Кузов: {body_style}\n"
        text += f"• Бюджет: {budget}\n"
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
    # Парсим callback_data
    parts = callback.data.split("_")
    subscription_type = parts[2]  # self или assisted
    subscription_id = int(parts[3])

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
        # Возвращаемся к списку подписок соответствующего типа
        if subscription_type == "self":
            await process_view_self_selection_subscriptions(callback, conn)
        elif subscription_type == "assisted":
            await process_view_assisted_selection_subscriptions(callback, conn)
    else:
        await callback.answer("Ошибка при удалении подписки", show_alert=True)
