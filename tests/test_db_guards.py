import pytest

from app.infrastructure.database.db import delete_subscription, set_subscription


@pytest.mark.asyncio
async def test_set_subscription_returns_zero_for_unsupported_table():
    result = await set_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        table="unknown_table",
    )
    assert result == 0


@pytest.mark.asyncio
async def test_set_subscription_returns_zero_for_assisted_selection_table():
    result = await set_subscription(
        None,  # type: ignore[arg-type]
        user_id=123,
        table="assisted_selection_requests",
    )
    assert result == 0


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
