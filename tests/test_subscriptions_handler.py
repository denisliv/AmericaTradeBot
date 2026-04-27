import inspect

from app.bot.handlers.subscriptions import _parse_subscription_callback_data
from app.bot.keyboards.keyboards_inline import create_subscriptions_keyboard


def test_parse_subscription_callback_data_valid_view():
    parsed = _parse_subscription_callback_data(
        "view_subscription_self_42",
        expected_prefix="view_subscription",
    )
    assert parsed == ("self", 42)


def test_parse_subscription_callback_data_invalid_prefix():
    parsed = _parse_subscription_callback_data(
        "delete_subscription_self_42",
        expected_prefix="view_subscription",
    )
    assert parsed is None


def test_parse_subscription_callback_data_invalid_type():
    parsed = _parse_subscription_callback_data(
        "view_subscription_other_42",
        expected_prefix="view_subscription",
    )
    assert parsed is None


def test_parse_subscription_callback_data_invalid_id():
    parsed = _parse_subscription_callback_data(
        "view_subscription_self_abc",
        expected_prefix="view_subscription",
    )
    assert parsed is None


def test_subscriptions_keyboard_ignores_assisted_subscriptions():
    assert "assisted_selection_subs" not in inspect.signature(
        create_subscriptions_keyboard
    ).parameters

    keyboard = create_subscriptions_keyboard(self_selection_subs=[], show_back_button=False)

    callback_data = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert callback_data == []
