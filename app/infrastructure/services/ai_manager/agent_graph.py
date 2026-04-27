"""LangGraph ReAct agent for the AI manager (tools: RAG, cars.md, CSV, CRM)."""

from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from psycopg import AsyncConnection

from app.infrastructure.services.ai_manager.knowledge_base import KnowledgeBaseService
from app.infrastructure.services.ai_manager.metrics import AIManagerMetrics
from app.infrastructure.services.ai_manager.prompts import DECOMPOSER_PROMPT, REACT_SYSTEM_PROMPT
from app.infrastructure.services.ai_manager.react_tools import ReActDependencies, make_react_tool_list
from app.infrastructure.services.ai_manager.schemas import (
    AIReply,
    CarCard,
    DecompositionHint,
    LeadDecision,
    UserContext,
)
from app.infrastructure.services.ai_manager.tools import AIManagerTools
from app.infrastructure.services.ai_manager.turn_context import get_turn, reset_turn, set_turn
from app.infrastructure.services.ai_manager.user_context import UserContextService

logger = logging.getLogger(__name__)


def _user_context_to_dict(ctx: UserContext) -> dict[str, Any]:
    return {
        "user_id": ctx.user_id,
        "username": ctx.username,
        "name": ctx.name,
        "active_car_count": ctx.active_car_count,
        "recent_self_selection_requests": ctx.recent_self_selection_requests or [],
        "self_subscriptions": ctx.self_subscriptions or [],
        "self_subscriptions_count": len(ctx.self_subscriptions or []),
        "latest_self_request": ctx.latest_self_request,
        "latest_assisted_request": ctx.latest_assisted_request,
    }


def _user_context_system_message(user_ctx: dict[str, Any]) -> SystemMessage:
    compact_context = {
        "name": user_ctx.get("name"),
        "username": user_ctx.get("username"),
        "active_car_count": user_ctx.get("active_car_count", 0),
        "recent_self_selection_requests": user_ctx.get(
            "recent_self_selection_requests", []
        ),
        "self_subscriptions": user_ctx.get("self_subscriptions", []),
        "self_subscriptions_count": user_ctx.get("self_subscriptions_count", 0),
        "latest_self_request": user_ctx.get("latest_self_request"),
        "latest_assisted_request": user_ctx.get("latest_assisted_request"),
    }
    return SystemMessage(
        content=(
            "DB user_context for this Telegram user. Sections are distinct: "
            "recent_self_selection_requests are the last viewed/requested cars, "
            "self_subscriptions are active monitoring subscriptions, "
            "latest_assisted_request is the latest assisted search. Use these facts "
            "to avoid asking repeated questions; do not reveal raw JSON to the user.\n"
            f"user_context={json.dumps(compact_context, ensure_ascii=False, default=str)}"
        )
    )


def _chat_rows_to_messages(rows: list[dict[str, Any]]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for row in rows:
        role = str(row.get("role", "")).lower()
        content = str(row.get("content", "")).strip()
        if not content:
            continue
        if role in ("user", "human"):
            out.append(HumanMessage(content=content))
        elif role in ("assistant", "ai", "bot"):
            out.append(AIMessage(content=content))
    return out


def _final_assistant_text(messages: list[AnyMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            calls = getattr(m, "tool_calls", None) or []
            if calls:
                continue
            content = m.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str) and item.strip():
                        parts.append(item.strip())
                    elif isinstance(item, dict):
                        t = str(item.get("text") or item.get("content") or "").strip()
                        if t:
                            parts.append(t)
                if parts:
                    return "\n".join(parts).strip()
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            c = m.content
            return c.strip() if isinstance(c, str) else str(c).strip()
    return ""


class AIManagerGraphService:
    """ReAct loop via `create_react_agent` with project tools."""

    def __init__(
        self,
        *,
        llm: ChatOpenAI,
        rag: KnowledgeBaseService,
        tools: AIManagerTools,
        context_service: UserContextService,
        metrics: AIManagerMetrics,
        rag_top_k: int,
        search_result_count: int,
        lead_confidence_threshold: float,
        max_history_messages: int,
        cars_catalog_path: Path,
    ) -> None:
        self.llm = llm
        self.rag = rag
        self.base_tools = tools
        self.context_service = context_service
        self.metrics = metrics
        self.rag_top_k = rag_top_k
        self.search_result_count = search_result_count
        self.lead_confidence_threshold = lead_confidence_threshold
        self.max_history_messages = max_history_messages
        self.cars_catalog_path = cars_catalog_path

        self.judge_runnable = llm.with_structured_output(LeadDecision)
        self._decomposer = llm.with_structured_output(DecompositionHint)

        self._deps = ReActDependencies(
            llm=llm,
            rag=rag,
            base_tools=self.base_tools,
            metrics=metrics,
            judge_runnable=self.judge_runnable,
            lead_confidence_threshold=lead_confidence_threshold,
            search_result_count=search_result_count,
            rag_top_k=rag_top_k,
            cars_catalog_path=cars_catalog_path,
        )
        self._tool_list = make_react_tool_list(self._deps)
        self.react_graph = create_react_agent(
            self.llm,
            tools=self._tool_list,
            prompt=REACT_SYSTEM_PROMPT,
            checkpointer=None,
            version="v2",
        )
        # Last auction cards shown in-session (per user_id), for lead hydration
        self._session_last_shown: dict[int, list[dict[str, Any]]] = {}

    async def run(
        self,
        *,
        conn: AsyncConnection,
        user_id: int,
        username: str | None,
        message: str,
    ) -> AIReply:
        self.metrics.inc_messages()
        ctx = await self.context_service.get_context(
            conn, user_id=user_id, chat_history_limit=self.max_history_messages
        )
        user_ctx = _user_context_to_dict(ctx)
        turn: dict[str, Any] = {
            "conn": conn,
            "user_id": user_id,
            "username": username,
            "user_context": user_ctx,
            "cars": [],
            "lead_sent": False,
            "last_shown_cars": self._session_last_shown.get(user_id, []),
        }
        token = set_turn(turn)
        try:
            history = _chat_rows_to_messages(ctx.recent_chat_messages or [])
            new_human = HumanMessage(content=message)
            # Avoid duplicate if same text already last in history (edge re-send)
            if history and isinstance(history[-1], HumanMessage):
                if (history[-1].content) == new_human.content:
                    history = history[:-1]
            messages_in = await self._maybe_decompose(
                [_user_context_system_message(user_ctx), *history, new_human],
                user_text=message,
            )

            final_state = await self.react_graph.ainvoke(
                {"messages": messages_in},
                config={"recursion_limit": 50},
            )
            out_msgs: list[AnyMessage] = list(final_state.get("messages", []))
            text = _final_assistant_text(out_msgs)
            if not text:
                text = (
                    "Секунду, уточните, пожалуйста, что важно: бюджет, тип авто "
                    "или вопрос по доставке из США."
                )
            t_after = get_turn()
            cars_raw = t_after.get("cars") or turn.get("cars") or []
            cars: list[CarCard] = []
            for x in cars_raw:
                if isinstance(x, CarCard):
                    cars.append(x)
                else:
                    cars.append(CarCard.model_validate(x))
            lead_sent = bool(t_after.get("lead_sent", False))
            if lead_sent:
                text = (
                    f"{text}\n\n"
                    "Передал ваш запрос менеджеру. Он свяжется с вами в Telegram "
                    "и подтвердит следующий шаг."
                ).strip()
            if turn.get("last_shown_cars"):
                self._session_last_shown[user_id] = list(turn["last_shown_cars"])
            return AIReply(text=text, cars=cars, lead_sent=lead_sent)
        except Exception as exc:
            logger.exception("AI manager ReAct failed for user %s: %s", user_id, exc)
            return AIReply(
                text=(
                    "Секунду, технические шероховатости. Попробуйте переформулировать "
                    "вопрос или уточните, что именно вас интересует."
                ),
            )
        finally:
            reset_turn(token)

    async def _maybe_decompose(
        self, messages: list[BaseMessage], *, user_text: str
    ) -> list[BaseMessage]:
        if len(user_text) < 140 and user_text.count("?") < 2:
            return list(messages)
        try:
            hint: DecompositionHint = await self._decomposer.ainvoke(
                [
                    SystemMessage(content=DECOMPOSER_PROMPT),
                    HumanMessage(
                        content=(
                            f"Сообщение:\n{user_text[:1200]}\n\n"
                            "Верни needs_decomposition и subtasks."
                        )
                    ),
                ]
            )
        except Exception as exc:
            logger.debug("Decomposer skip: %s", exc)
            return list(messages)
        if not hint.needs_decomposition or not hint.subtasks:
            return list(messages)
        plan = SystemMessage(
            content=(
                "Сложный запрос пользователя — выполни шаги по порядку инструментами, "
                "затем ответь кратко. Подзадачи:\n- "
                + "\n- ".join(hint.subtasks[:4])
            )
        )
        return [plan, *list(messages)]


# Backwards-compatible re-exports for tests / imports
__all__ = ["AIManagerGraphService"]
