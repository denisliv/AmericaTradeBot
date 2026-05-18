import inspect

import pytest

from app.bot.callback_data import (
    DeleteSubscriptionCB,
    SubscribeCB,
    ViewSubscriptionCB,
)
from app.bot.keyboards.keyboards_inline import create_subscriptions_keyboard


def test_view_callback_roundtrip():
    packed = ViewSubscriptionCB(source="self", subscription_id=42).pack()
    unpacked = ViewSubscriptionCB.unpack(packed)
    assert unpacked.source == "self"
    assert unpacked.subscription_id == 42


def test_delete_callback_roundtrip():
    packed = DeleteSubscriptionCB(source="self", subscription_id=42).pack()
    unpacked = DeleteSubscriptionCB.unpack(packed)
    assert unpacked.source == "self"
    assert unpacked.subscription_id == 42


def test_view_callback_distinct_prefix_from_delete():
    view = ViewSubscriptionCB(source="self", subscription_id=42).pack()
    delete = DeleteSubscriptionCB(source="self", subscription_id=42).pack()
    assert view != delete
    with pytest.raises(ValueError):
        ViewSubscriptionCB.unpack(delete)


def test_view_callback_rejects_non_integer_id():
    with pytest.raises(ValueError):
        ViewSubscriptionCB.unpack("sub_view:self:abc")


def test_subscribe_callback_roundtrip():
    packed = SubscribeCB(source="self").pack()
    assert SubscribeCB.unpack(packed).source == "self"


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
