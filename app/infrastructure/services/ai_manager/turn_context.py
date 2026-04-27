"""Per-invocation context for ReAct tools (not serialized in LangGraph state)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_turn: ContextVar[dict[str, Any] | None] = ContextVar("ai_manager_turn_ctx", default=None)


def get_turn() -> dict[str, Any]:
    v = _turn.get()
    if v is None:
        return {}
    return v


def set_turn(data: dict[str, Any]) -> Token:
    return _turn.set(data)


def reset_turn(token: Token) -> None:
    _turn.reset(token)
