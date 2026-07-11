import pytest

from app.infrastructure.database.selections import (
    SubscriptionOutcome,
    delete_subscription,
    set_subscription,
)


@pytest.mark.asyncio
async def test_set_subscription_rejects_unsupported_table():
    outcome, active_count = await set_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        table="unknown_table",
    )
    assert outcome is SubscriptionOutcome.NOT_FOUND
    assert active_count == 0


@pytest.mark.asyncio
async def test_set_subscription_rejects_assisted_selection_table():
    outcome, active_count = await set_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        table="assisted_selection_requests",
    )
    assert outcome is SubscriptionOutcome.NOT_FOUND
    assert active_count == 0


@pytest.mark.asyncio
async def test_delete_subscription_returns_false_for_unsupported_table():
    result = await delete_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        subscription_id=5,
        table="unknown_table",
    )
    assert result is False


@pytest.mark.asyncio
async def test_delete_subscription_returns_false_for_assisted_selection_table():
    result = await delete_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        subscription_id=5,
        table="assisted_selection_requests",
    )
    assert result is False
