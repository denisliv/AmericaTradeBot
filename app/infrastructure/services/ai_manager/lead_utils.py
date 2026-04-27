"""Helpers for lot selection and CollectedInfo hydration (CRM / lead)."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from app.infrastructure.services.ai_manager.schemas import CollectedInfoDelta

_LOT_NUMBER_RE = re.compile(r"\b(\d{7,10})\b")

_ORDINAL_WORDS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("перв", "первый", "первое", "первая", "first", "1-й", "1й"), 0),
    (("втор", "второй", "second", "2-й", "2й"), 1),
    (("трет", "третий", "третье", "third", "3-й", "3й"), 2),
)

_AFFIRMATIVE_TOKENS: frozenset[str] = frozenset(
    {
        "да",
        "ага",
        "угу",
        "согласен",
        "согласна",
        "согласны",
        "беру",
        "беруем",
        "возьму",
        "хочу",
        "надо",
        "подходит",
        "подойдёт",
        "подойдет",
        "ок",
        "окей",
        "ok",
        "okay",
        "давайте",
        "давай",
    }
)


def last_user_message_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(item.get("text", "")) if isinstance(item, dict) else str(item)
                    for item in content
                ).strip()
    return ""


def short_history_text(
    messages: list[AnyMessage], *, max_items: int = 6, max_chars: int = 300
) -> str:
    lines: list[str] = []
    for message in messages[-max_items:]:
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            continue
        content = (
            message.content
            if isinstance(message.content, str)
            else str(message.content)
        )
        snippet = content.strip().replace("\n", " ")
        if len(snippet) > max_chars:
            snippet = snippet[: max_chars - 1] + "…"
        lines.append(f"{role}: {snippet}")
    return "\n".join(lines)


def pick_card_for_lead(
    user_text: str, cards: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not cards:
        return None
    text = (user_text or "").strip()
    if not text:
        return None

    for lot_match in _LOT_NUMBER_RE.findall(text):
        for card in cards:
            if str(card.get("lot_number") or "").strip() == lot_match:
                return card

    lowered = text.lower()
    for needles, idx in _ORDINAL_WORDS:
        if any(n in lowered for n in needles) and idx < len(cards):
            return cards[idx]

    tokens = {t.strip(" ,.!?") for t in lowered.split()}
    if tokens & _AFFIRMATIVE_TOKENS and len(cards) == 1:
        return cards[0]

    return None


def delta_from_card(card: dict[str, Any]) -> CollectedInfoDelta | None:
    if not card:
        return None
    make = card.get("make") or None
    model = card.get("model") or None
    year = card.get("year")
    year_int: int | None = None
    if isinstance(year, (int, float)):
        year_int = int(year)
    elif isinstance(year, str) and year.strip().isdigit():
        year_int = int(year.strip())

    if not (make or model or year_int):
        return None
    return CollectedInfoDelta(
        brand=make,
        model=model,
        year_from=year_int,
        year_to=year_int,
    )
