"""Единая классификация ошибок отправки и пометка недоступных пользователей."""

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.infrastructure.services import safe_send
from app.infrastructure.services.safe_send import SendStatus, send_to_user_safely


@pytest.fixture
def marked_dead(monkeypatch):
    marked = []

    async def fake_change_user_alive_status(conn, *, is_alive, user_id):
        marked.append((user_id, is_alive))

    monkeypatch.setattr(
        safe_send, "change_user_alive_status", fake_change_user_alive_status
    )
    return marked


def _raiser(exc):
    async def _send():
        raise exc

    return _send


@pytest.mark.asyncio
async def test_ok_send(marked_dead):
    async def _send():
        pass

    status, detail = await send_to_user_safely(_send, conn=None, user_id=1)
    assert status is SendStatus.OK
    assert detail == ""
    assert marked_dead == []


@pytest.mark.asyncio
async def test_forbidden_marks_user_dead(marked_dead):
    exc = TelegramForbiddenError(method=None, message="bot was blocked by the user")
    status, _ = await send_to_user_safely(_raiser(exc), conn=None, user_id=42)
    assert status is SendStatus.BLOCKED
    assert marked_dead == [(42, False)]


@pytest.mark.asyncio
async def test_unreachable_bad_request_marks_user_dead(marked_dead):
    exc = TelegramBadRequest(method=None, message="Bad Request: chat not found")
    status, _ = await send_to_user_safely(_raiser(exc), conn=None, user_id=42)
    assert status is SendStatus.BLOCKED
    assert marked_dead == [(42, False)]


@pytest.mark.asyncio
async def test_other_bad_request_is_error(marked_dead):
    exc = TelegramBadRequest(method=None, message="Bad Request: message is too long")
    status, detail = await send_to_user_safely(_raiser(exc), conn=None, user_id=42)
    assert status is SendStatus.ERROR
    assert "too long" in detail
    assert marked_dead == []


@pytest.mark.asyncio
async def test_unexpected_exception_is_error(marked_dead):
    status, detail = await send_to_user_safely(
        _raiser(RuntimeError("boom")), conn=None, user_id=42
    )
    assert status is SendStatus.ERROR
    assert detail == "boom"
    assert marked_dead == []


@pytest.mark.asyncio
async def test_retry_after_propagates(marked_dead):
    exc = TelegramRetryAfter(method=None, message="flood", retry_after=13)
    with pytest.raises(TelegramRetryAfter):
        await send_to_user_safely(_raiser(exc), conn=None, user_id=42)
    assert marked_dead == []
