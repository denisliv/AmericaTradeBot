import logging

from aiogram import Bot, F, Router
from aiogram.enums import BotCommandScopeType
from aiogram.filters import KICKED, ChatMemberUpdatedFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeChat,
    CallbackQuery,
    ChatMemberUpdated,
    Message,
)
from psycopg.connection_async import AsyncConnection

from app.bot.enums.roles import UserRole
from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_url_keyboard,
)
from app.bot.keyboards.menu_button import get_main_menu_commands
from app.infrastructure.database.db import (
    add_user,
    change_user_alive_status,
    get_user,
)
from app.infrastructure.services.promo_newsletter import add_user_to_promo_queue
from app.lexicon.lexicon_ru import LEXICON_RU

logger = logging.getLogger(__name__)

user_router = Router()


# Этот хэндлер срабатывает на команду /start
@user_router.message(Command(commands=["start"]))
async def process_start_command(
    message: Message,
    conn: AsyncConnection,
    bot: Bot,
    admin_ids: list[int],
    state: FSMContext,
    redis,
):
    user_row = await get_user(conn, user_id=message.from_user.id)
    if user_row is None:
        if message.from_user.id in admin_ids:
            user_role = UserRole.ADMIN
        else:
            user_role = UserRole.USER

        await add_user(
            conn,
            user_id=message.from_user.id,
            username=message.from_user.username,
            name=message.from_user.first_name,
            role=user_role,
        )

        # Добавляем пользователя в очередь промо-рассылки через 48 часов
        await add_user_to_promo_queue(message.from_user.id, redis)
    else:
        user_role = UserRole(user_row.role)
        await change_user_alive_status(
            conn,
            is_alive=True,
            user_id=message.from_user.id,
        )
    await bot.set_my_commands(
        commands=get_main_menu_commands(role=user_role),
        scope=BotCommandScopeChat(
            type=BotCommandScopeType.CHAT, chat_id=message.from_user.id
        ),
    )
    await message.answer(
        text=LEXICON_RU["/start_text"](message.from_user.first_name),
        reply_markup=create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "contact_button",
            width=1,
        ),
    )
    await state.clear()


# Этот хэндлер будет срабатывать на блокировку бота пользователем
@user_router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def process_user_blocked_bot(event: ChatMemberUpdated, conn: AsyncConnection):
    logger.info("User %d has blocked the bot", event.from_user.id)
    await change_user_alive_status(conn, user_id=event.from_user.id, is_alive=False)


# Этот хэндлер срабатывает на команду /help
@user_router.message(Command(commands="help"))
async def process_help_command(message: Message, state: FSMContext):
    await message.answer(text=LEXICON_RU.get("/help_text"))
    await state.clear()


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Контакты"
@user_router.callback_query(F.data == "contact_button")
async def process_contact_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["contacts_text"],
        reply_markup=create_url_keyboard(back=True, width=1),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Все об авто из США"
@user_router.callback_query(F.data == "more_information_button")
async def process_more_information_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["more_information_text"],
        reply_markup=create_choice_keyboard(
            "advantages_button",
            "purchasing_process_button",
            "car_delivery_button",
            "back_to:main_menu",
            width=1,
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Преимущества работы с нами"
@user_router.callback_query(F.data == "advantages_button")
async def process_advantages_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["advantages_text"],
        reply_markup=create_choice_keyboard(
            "back_to:main_menu",
            "back_to:more_info",
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Процесс покупки авто из США"
@user_router.callback_query(F.data == "purchasing_process_button")
async def process_purchasing_process_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["purchasing_process_text"],
        reply_markup=create_choice_keyboard(
            "back_to:main_menu",
            "back_to:more_info",
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Доставка авто из США"
@user_router.callback_query(F.data == "car_delivery_button")
async def process_car_delivery_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["car_delivery_text"],
        reply_markup=create_choice_keyboard(
            "back_to:main_menu",
            "back_to:more_info",
        ),
    )


# Этот хэндлер будет срабатывать на кнопку "Назад" и "Вернуться в начало"
# и предоставлять пользователю инлайн-кнопки с выбором
@user_router.callback_query(F.data.startswith("back_to:"))
async def procces_back_button_press(callback: CallbackQuery):
    await callback.answer()
    target = callback.data.split(":")[1]

    if target == "main_menu":
        await callback.message.edit_text(
            text=LEXICON_RU["/start_text"](callback.from_user.first_name),
            reply_markup=create_choice_keyboard(
                "choose_a_car_button",
                "more_information_button",
                "contact_button",
                width=1,
            ),
        )
    elif target == "more_info":
        await callback.message.edit_text(
            text=LEXICON_RU["more_information_text"],
            reply_markup=create_choice_keyboard(
                "advantages_button",
                "purchasing_process_button",
                "car_delivery_button",
                "back_to:main_menu",
                width=1,
            ),
        )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "Подобрать авто"
@user_router.callback_query(F.data.in_({"choose_a_car_button", "new_search_button"}))
async def process_choose_a_car_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        text=LEXICON_RU["choose_a_car_text"],
        reply_markup=create_choice_keyboard("knowing_button", "advice_button", width=1),
    )
