import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.bot.keyboards.keyboards_reply import get_chat_keyboard
from app.infrastructure.database.db import (
    add_chat_message,
    clear_chat_history,
    record_metric_event,
)
from app.infrastructure.services.ai_manager.schemas import AIReply, CarCard
from app.infrastructure.services.ai_manager.service import AIManagerService

logger = logging.getLogger(__name__)

llm_chat_router = Router()


class ChatStates(StatesGroup):
    """Состояния для чата с AI-менеджером"""

    waiting_for_message = State()


@llm_chat_router.message(Command(commands=["chat"]))
async def start_chat_command(
    message: Message,
    state: FSMContext,
    ai_manager_service: AIManagerService,
    conn: AsyncConnection,
):
    """Начинает чат с AI-менеджером"""

    if not ai_manager_service.is_valid_api_key():
        await message.answer(
            "⚠️ Чат с AI-менеджером временно недоступен.\n"
            "Обратитесь к менеджеру для получения консультации.",
            reply_markup=create_choice_keyboard(
                "choose_a_car_button",
                "more_information_button",
                "contact_button",
                width=1,
            ),
        )
        return

    welcome_text = (
        "🤖 <b>AI-менеджер AmericaTrade</b>\n\n"
        "Привет! Я помогу подобрать авто из США, отвечу по процессу и "
        "помогу перейти к следующему шагу, если вы готовы к покупке.\n\n"
        "💡 <i>Для выхода из чата используйте команду /exit</i>"
    )

    await message.answer(welcome_text, reply_markup=get_chat_keyboard())
    await state.set_state(ChatStates.waiting_for_message)
    await record_metric_event(
        conn,
        event_name="llm_chat_started",
        user_id=message.from_user.id,
    )

    logger.info(f"User {message.from_user.id} started chat with AI manager")


@llm_chat_router.message(Command(commands=["exit"]))
async def exit_chat_command(
    message: Message,
    state: FSMContext,
):
    """Выход из чата с AI-менеджером"""
    await state.clear()

    await message.answer(
        "👋 Вы вышли из чата с AI-менеджером.\nВозвращаюсь в главное меню!",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Главное меню:",
        reply_markup=create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "contact_button",
            width=1,
        ),
    )

    logger.info(f"User {message.from_user.id} exited AI manager chat")


@llm_chat_router.message(Command(commands=["clear_history"]))
async def clear_history_command(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
):
    """Очищает историю чата пользователя"""
    await clear_chat_history(conn, user_id=message.from_user.id)

    await message.answer("🗑️ История чата очищена!\nТеперь мы начнем разговор заново.")

    logger.info(f"User {message.from_user.id} cleared chat history")


@llm_chat_router.message(ChatStates.waiting_for_message, F.text == "🗑️ Очистить историю")
async def clear_history_button(
    message: Message,
    conn: AsyncConnection,
):
    """Обработчик кнопки очистки истории чата"""
    await clear_chat_history(conn, user_id=message.from_user.id)

    await message.answer(
        "🗑️ История чата очищена!\nТеперь мы начнем разговор заново.",
        reply_markup=get_chat_keyboard(),
    )

    logger.info(f"User {message.from_user.id} cleared chat history via button")


@llm_chat_router.message(ChatStates.waiting_for_message, F.text == "🚪 Выйти из чата")
async def exit_chat_button(
    message: Message,
    state: FSMContext,
):
    """Обработчик кнопки выхода из чата"""
    await state.clear()

    await message.answer(
        "👋 Вы вышли из чата с AI-менеджером.\nВозвращаюсь в главное меню!",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Главное меню:",
        reply_markup=create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "contact_button",
            width=1,
        ),
    )

    logger.info(f"User {message.from_user.id} exited AI manager chat via button")


@llm_chat_router.message(ChatStates.waiting_for_message)
async def handle_chat_message(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
    ai_manager_service: AIManagerService,
):
    """Обрабатывает сообщения в чате с AI-менеджером"""

    raw = message.text or ""
    user_message = raw.strip()
    user_id = message.from_user.id

    if not user_message:
        await message.answer("Пожалуйста, напишите ваш вопрос.")
        return

    try:
        async with ChatActionSender(
            bot=message.bot,
            action="typing",
            chat_id=message.chat.id,
            interval=1,
            initial_sleep=0.1,
        ):
            reply: AIReply = await ai_manager_service.get_reply(
                conn,
                user_id=user_id,
                username=message.from_user.username,
                message=user_message,
            )
            reply_text = reply.text.strip() or (
                "Спасибо за сообщение! Я на связи и готов помочь с подбором авто из США. "
                "Уточните, пожалуйста, марку/модель и ваш бюджет."
            )

            await add_chat_message(
                conn, user_id=user_id, role="user", content=user_message
            )
            await add_chat_message(
                conn, user_id=user_id, role="assistant", content=reply_text
            )

        await message.answer(
            f"🤖 <b>AI-менеджер:</b>\n\n{reply_text}",
            reply_markup=get_chat_keyboard(),
        )

        if reply.cars:
            await _send_car_cards(message, reply.cars)

        logger.info(
            "AI manager response sent to user %s (cars=%d, lead_sent=%s)",
            user_id,
            len(reply.cars),
            reply.lead_sent,
        )
        if reply.lead_sent:
            await record_metric_event(
                conn,
                event_name="llm_lead_sent",
                user_id=user_id,
            )

    except Exception as e:
        logger.error(f"Error processing chat message for user {user_id}: {e}")
        await record_metric_event(
            conn,
            event_name="handler_exception",
            user_id=user_id,
        )
        await message.answer(
            "❌ Произошла ошибка при обработке вашего сообщения.\n"
            "Попробуйте позже или обратитесь к менеджеру.",
            reply_markup=get_chat_keyboard(),
        )


async def _send_car_cards(message: Message, cars: list[CarCard]) -> None:
    """Renders each CarCard as answer_photo with caption; falls back to text on failure."""
    for card in cars:
        caption = _format_car_caption(card)
        if card.preview_image_url:
            try:
                await message.answer_photo(
                    photo=card.preview_image_url,
                    caption=caption,
                )
                continue
            except TelegramBadRequest as err:
                logger.warning(
                    "Failed to send car photo for lot %s: %s", card.lot_number, err
                )
        # Fallback: send plain text with the lot URL.
        await message.answer(
            f"{caption}\n{card.lot_url}".strip(),
            disable_web_page_preview=False,
        )


def _format_car_caption(card: CarCard) -> str:
    base = card.caption.strip() if card.caption else ""
    if card.lot_url and card.lot_url not in base:
        base = f"{base}\n{card.lot_url}".strip()
    return base[:1024]
