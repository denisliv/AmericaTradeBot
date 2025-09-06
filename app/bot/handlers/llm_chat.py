import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from psycopg.connection_async import AsyncConnection

from app.bot.keyboards.keyboards_inline import create_choice_keyboard
from app.bot.keyboards.keyboards_reply import get_chat_keyboard
from app.infrastructure.database.db import (
    add_chat_message,
    clear_chat_history,
    get_chat_history,
)
from app.infrastructure.services.llm_service import LLMService

logger = logging.getLogger(__name__)

llm_chat_router = Router()


class ChatStates(StatesGroup):
    """Состояния для чата с LLM"""

    waiting_for_message = State()


@llm_chat_router.message(Command(commands=["chat"]))
async def start_chat_command(
    message: Message,
    state: FSMContext,
    llm_service: LLMService,
):
    """Начинает чат с LLM моделью"""

    # Проверяем, валиден ли API ключ
    if not llm_service.is_valid_api_key():
        await message.answer(
            "⚠️ Чат с AI-ассистентом временно недоступен.\n"
            "Обратитесь к менеджеру для получения консультации.",
            reply_markup=create_choice_keyboard(
                "choose_a_car_button",
                "more_information_button",
                "contact_button",
                width=1,
            ),
        )
        return

    # Приветственное сообщение
    welcome_text = (
        "🤖 <b>AI-ассистент AmericaTrade</b>\n\n"
        "Привет! Я ваш персональный AI-помощник по вопросам покупки автомобилей из США.\n\n"
        "Я могу помочь вам с:\n"
        "• Информацией о процессе покупки\n"
        "• Советами по выбору автомобиля\n"
        "• Вопросами по доставке и таможне\n"
        "• Общей информацией о компании\n\n"
        "Просто напишите ваш вопрос, и я постараюсь помочь!\n\n"
        "💡 <i>Для выхода из чата используйте команду /exit</i>"
    )

    await message.answer(welcome_text, reply_markup=get_chat_keyboard())
    await state.set_state(ChatStates.waiting_for_message)

    logger.info(f"User {message.from_user.id} started chat with LLM")


@llm_chat_router.message(Command(commands=["exit"]))
async def exit_chat_command(
    message: Message,
    state: FSMContext,
):
    """Выход из чата с LLM"""
    await state.clear()

    await message.answer(
        "👋 Вы вышли из чата с AI-ассистентом.\nВозвращаюсь в главное меню!",
        reply_markup=create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "contact_button",
            width=1,
        ),
    )

    logger.info(f"User {message.from_user.id} exited LLM chat")


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
        "👋 Вы вышли из чата с AI-ассистентом.\nВозвращаюсь в главное меню!",
        reply_markup=create_choice_keyboard(
            "choose_a_car_button",
            "more_information_button",
            "contact_button",
            width=1,
        ),
    )

    logger.info(f"User {message.from_user.id} exited LLM chat via button")


@llm_chat_router.message(ChatStates.waiting_for_message)
async def handle_chat_message(
    message: Message,
    state: FSMContext,
    conn: AsyncConnection,
    llm_service: LLMService,
):
    """Обрабатывает сообщения в чате с LLM"""

    user_message = message.text.strip()
    user_id = message.from_user.id

    if not user_message:
        await message.answer("Пожалуйста, напишите ваш вопрос.")
        return

    # Показываем, что бот печатает
    await message.answer("🤔 Думаю над ответом...")

    try:
        # Получаем историю чата
        chat_history = await get_chat_history(conn, user_id=user_id, limit=10)

        # Получаем ответ от LLM
        llm_response = await llm_service.get_response(
            user_id=user_id, message=user_message, conversation_history=chat_history
        )

        # Сохраняем сообщение пользователя
        await add_chat_message(conn, user_id=user_id, role="user", content=user_message)

        # Сохраняем ответ ассистента
        await add_chat_message(
            conn, user_id=user_id, role="assistant", content=llm_response
        )

        # Отправляем ответ
        await message.answer(
            f"🤖 <b>AI-ассистент:</b>\n\n{llm_response}",
            reply_markup=get_chat_keyboard(),
        )

        logger.info(f"LLM response sent to user {user_id}")

    except Exception as e:
        logger.error(f"Error processing chat message for user {user_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке вашего сообщения.\n"
            "Попробуйте позже или обратитесь к менеджеру.",
            reply_markup=get_chat_keyboard(),
        )


@llm_chat_router.callback_query(F.data == "clear_chat_history")
async def clear_history_callback(
    callback: CallbackQuery,
    conn: AsyncConnection,
):
    """Обработчик кнопки очистки истории чата"""
    await clear_chat_history(conn, user_id=callback.from_user.id)

    await callback.message.edit_text(
        "🗑️ История чата очищена!\nТеперь мы начнем разговор заново."
    )

    await callback.answer("История чата очищена!")
    logger.info(f"User {callback.from_user.id} cleared chat history via button")


@llm_chat_router.callback_query(F.data == "exit_chat")
async def exit_chat_callback(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Обработчик кнопки выхода из чата"""
    await state.clear()

    await callback.message.edit_text(
        "👋 Вы вышли из чата с AI-ассистентом.\nВозвращаюсь в главное меню!"
    )

    await callback.answer("Вы вышли из чата!")
    logger.info(f"User {callback.from_user.id} exited LLM chat via button")
