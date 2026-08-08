"""Every criteria screen must offer a way back.

The customer got stuck on the selection steps: once a brand was picked there was
no way to change it without restarting the whole flow.
"""

import pytest

from app.bot.callback_data import STEP_BACK_PREFIX
from app.bot.handlers.assisted_selection import show_body_style_step, show_budget_step
from app.bot.handlers.self_selection import flow
from app.bot.handlers.self_selection.flow import (
    show_auction_status_step,
    show_brand_step,
    show_model_step,
    show_year_step,
)
from app.bot.handlers.step_back import TARGETS
from app.bot.states.states import (
    FSMFillAssistedSelectionForm,
    FSMFillSelfSelectionForm,
)


class FakeMessage:
    """Collects what a step would render instead of calling Telegram."""

    def __init__(self):
        self.text = None
        self.reply_markup = None

    async def edit_text(self, text, reply_markup=None):
        self.text = text
        self.reply_markup = reply_markup


class FakeCallback:
    """Only the parts of CallbackQuery the step screens touch."""

    def __init__(self):
        self.message = FakeMessage()

    async def answer(self, text=None, show_alert=False):
        return None


class FakeState:
    def __init__(self, data=None):
        self._data = data or {}
        self.state = "untouched"

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def set_state(self, state):
        self.state = state


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "kwargs", "back_target", "expected_state"),
    [
        (show_brand_step, {}, "start", FSMFillSelfSelectionForm.get_brand),
        (
            show_model_step,
            {"brand": "BMW"},
            "brand",
            FSMFillSelfSelectionForm.get_model,
        ),
        (show_year_step, {}, "model", FSMFillSelfSelectionForm.get_year),
        (
            show_auction_status_step,
            {},
            "year",
            FSMFillSelfSelectionForm.get_auction_status,
        ),
        (
            show_body_style_step,
            {},
            "start",
            FSMFillAssistedSelectionForm.get_body_style,
        ),
        (
            show_budget_step,
            {},
            "body_style",
            FSMFillAssistedSelectionForm.get_budget,
        ),
    ],
)
async def test_criteria_step_has_back_button(step, kwargs, back_target, expected_state):
    message, state = FakeMessage(), FakeState()

    await step(message, state, **kwargs)

    assert f"{STEP_BACK_PREFIX}{back_target}" in _callbacks(message.reply_markup)
    assert state.state == expected_state


@pytest.mark.asyncio
async def test_back_button_is_labelled_consistently():
    message, state = FakeMessage(), FakeState()

    await show_year_step(message, state)

    labels = [
        button.text
        for row in message.reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith(STEP_BACK_PREFIX)
    ]
    assert labels == ["🔙 Назад"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("step", "kwargs"),
    [
        (show_brand_step, {}),
        (show_model_step, {"brand": "BMW"}),
        (show_year_step, {}),
        (show_auction_status_step, {}),
        (show_body_style_step, {}),
        (show_budget_step, {}),
    ],
)
async def test_every_back_button_has_a_handler(step, kwargs):
    """Кнопка, ведущая в никуда, оставила бы клиента в тупике."""
    message, state = FakeMessage(), FakeState()

    await step(message, state, **kwargs)

    targets = [
        callback[len(STEP_BACK_PREFIX) :]
        for callback in _callbacks(message.reply_markup)
        if callback.startswith(STEP_BACK_PREFIX)
    ]
    assert targets
    for target in targets:
        assert target in TARGETS, target


@pytest.mark.asyncio
@pytest.mark.parametrize("back_target", ["brand", "model"])
async def test_free_form_request_screen_is_not_a_dead_end(back_target):
    # Экран "Другое" не имел ни одной кнопки: выйти можно было только текстом
    callback = FakeCallback()

    await flow._prompt_manual_request(callback, FakeState(), back_target=back_target)

    assert _callbacks(callback.message.reply_markup) == [
        f"{STEP_BACK_PREFIX}{back_target}"
    ]


@pytest.mark.asyncio
async def test_model_step_remembers_the_brand_for_the_next_back():
    message, state = FakeMessage(), FakeState()

    await show_model_step(message, state, "BMW")

    assert (await state.get_data())["brand"] == "BMW"
