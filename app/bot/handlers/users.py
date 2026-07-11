import logging

from aiogram import Bot, F, Router
from aiogram.enums import BotCommandScopeType, ButtonStyle
from aiogram.filters import KICKED, ChatMemberUpdatedFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommandScopeChat,
    CallbackQuery,
    ChatMemberUpdated,
    FSInputFile,
    Message,
)
from psycopg.connection_async import AsyncConnection

from app.bot.enums.roles import UserRole
from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_contacts_keyboard,
    create_why_americatrade_keyboard,
)
from app.bot.keyboards.menu_button import get_main_menu_commands
from app.infrastructure.database.nurture import add_nurture_state
from app.infrastructure.database.users import (
    add_user,
    change_user_alive_status,
    get_user,
)
from app.infrastructure.paths import LOGO_JPG
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

        # Ставим нового пользователя в прогревочную цепочку рассылок
        await add_nurture_state(conn, user_id=message.from_user.id)
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
            "why_americatrade_button",
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


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "🙎‍♂️ Помощь и контакты"
@user_router.callback_query(F.data == "contact_button")
async def process_contact_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    if LOGO_JPG.exists():
        await callback.message.answer_photo(
            photo=FSInputFile(LOGO_JPG),
            caption=LEXICON_RU["contacts_text"],
            reply_markup=create_contacts_keyboard(),
        )
    else:
        # Логотип - runtime-файл (data/ не в git), без него отправляем только текст
        logger.warning("Logo file not found: %s", LOGO_JPG)
        await callback.message.answer(
            text=LEXICON_RU["contacts_text"],
            reply_markup=create_contacts_keyboard(),
        )


def create_info_hub_keyboard():
    """Клавиатура хаба "Все об авто из США": 5 разделов + возврат на шаг назад."""
    return create_choice_keyboard(
        "why_profitable_button",
        "purchasing_process_button",
        "auctions_button",
        "price_breakdown_button",
        # Отдельный callback, чтобы раздел знал, что зашли из хаба (нужна кнопка "Назад")
        ("why_americatrade_from_hub", "why_americatrade_button"),
        ("back_to:main_menu", "back_button"),
        width=1,
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "🤔 Все об авто из США"
@user_router.callback_query(F.data == "more_information_button")
async def process_more_information_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["more_information_text"],
        reply_markup=create_info_hub_keyboard(),
    )


# Разделы хаба "Все об авто из США": callback кнопки -> ключ текста в LEXICON_RU
_INFO_SECTIONS = {
    "why_profitable_button": "why_profitable_text",
    "purchasing_process_button": "purchasing_process_text",
    "auctions_button": "auctions_text",
    "price_breakdown_button": "price_breakdown_text",
}


# Этот хэндлер будет срабатывать на нажатие кнопок-разделов хаба "Все об авто из США"
@user_router.callback_query(F.data.in_(set(_INFO_SECTIONS)))
async def process_info_section_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU[_INFO_SECTIONS[callback.data]],
        reply_markup=create_choice_keyboard(
            (
                "application_for_selection_button",
                "free_consultation_button",
                ButtonStyle.SUCCESS,
            ),
            ("back_to:info_hub", "back_button"),
            "back_to:main_menu",
            width=1,
        ),
    )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "⭐ Почему именно AmericaTrade?"
# Кнопка есть в главном меню и в хабе: "Назад" показывается только при заходе из хаба
@user_router.callback_query(
    F.data.in_({"why_americatrade_button", "why_americatrade_from_hub"})
)
async def process_why_americatrade_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        text=LEXICON_RU["why_americatrade_text"],
        reply_markup=create_why_americatrade_keyboard(
            show_back=callback.data == "why_americatrade_from_hub"
        ),
    )


# Этот хэндлер будет срабатывать на кнопку "Назад" и "Вернуться в начало"
# и предоставлять пользователю инлайн-кнопки с выбором
@user_router.callback_query(F.data.startswith("back_to:"))
async def procces_back_button_press(callback: CallbackQuery):
    await callback.answer()
    target = callback.data.split(":")[1]

    if target == "main_menu":
        text = LEXICON_RU["/start_text"](callback.from_user.first_name)
        keyboard = create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "why_americatrade_button",
            "contact_button",
            width=1,
        )
        # Экран контактов - фото с подписью, его нельзя превратить в текст через edit_text
        if callback.message.text is None:
            await callback.message.delete()
            await callback.message.answer(text=text, reply_markup=keyboard)
        else:
            await callback.message.edit_text(text=text, reply_markup=keyboard)
    elif target == "info_hub":
        await callback.message.edit_text(
            text=LEXICON_RU["more_information_text"],
            reply_markup=create_info_hub_keyboard(),
        )


# Этот хэндлер будет срабатывать на нажатие инлайн-кнопки "✅ Подобрать авто из США"
@user_router.callback_query(F.data == "choose_a_car_button")
async def process_choose_a_car_press(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        text=LEXICON_RU["choose_a_car_text"],
        reply_markup=create_choice_keyboard("knowing_button", "advice_button", width=1),
    )
