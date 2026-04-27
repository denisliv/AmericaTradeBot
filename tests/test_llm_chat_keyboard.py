from types import SimpleNamespace

import pytest
from aiogram.types import ReplyKeyboardRemove

from app.bot.handlers.llm_chat import exit_chat_button, exit_chat_command


class _State:
    def __init__(self):
        self.cleared = False

    async def clear(self):
        self.cleared = True


class _Message:
    def __init__(self):
        self.from_user = SimpleNamespace(id=123)
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_exit_chat_command_removes_reply_keyboard():
    message = _Message()
    state = _State()

    await exit_chat_command(message, state)

    assert state.cleared is True
    assert any(isinstance(markup, ReplyKeyboardRemove) for _, markup in message.answers)


@pytest.mark.asyncio
async def test_exit_chat_button_removes_reply_keyboard():
    message = _Message()
    state = _State()

    await exit_chat_button(message, state)

    assert state.cleared is True
    assert any(isinstance(markup, ReplyKeyboardRemove) for _, markup in message.answers)
