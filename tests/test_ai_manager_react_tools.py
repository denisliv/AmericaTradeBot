from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.infrastructure.services.ai_manager.react_tools import (
    ReActDependencies,
    make_react_tool_list,
)
from app.infrastructure.services.ai_manager.schemas import CarCard, LeadDecision
from app.infrastructure.services.ai_manager.tools import ToolResult
from app.infrastructure.services.ai_manager.turn_context import reset_turn, set_turn


class _Metrics:
    def inc_tool(self, name):
        pass

    def inc_leads_ready(self):
        pass

    def inc_leads_sent(self):
        pass

    def inc_leads_rejected_by_judge(self):
        pass


def test_react_tools_include_autonomy_helpers():
    deps = ReActDependencies(
        llm=object(),
        rag=object(),
        base_tools=object(),
        metrics=_Metrics(),
        judge_runnable=object(),
        lead_confidence_threshold=0.75,
        search_result_count=3,
        rag_top_k=4,
        cars_catalog_path=Path("data/ai_manager/cars.md"),
    )

    names = {tool.name for tool in make_react_tool_list(deps)}

    assert "lookup_auction_lot" in names
    assert "explain_landed_cost_components" in names
    assert "quick_vehicle_specs" in names
    assert "estimate_landed_cost_for_lot" in names


class _BaseTools:
    async def lookup_lot_by_number(self, lot_query):
        car = CarCard(
            lot_number="90141575",
            year=2025,
            make="CHEVROLET",
            model="EQUINOX",
            preview_image_url="https://example.com/car.jpg",
            lot_url="https://www.copart.com/lot/90141575/",
            caption="2025 CHEVROLET EQUINOX",
        )
        return ToolResult(
            ok=True,
            message="ok",
            payload={
                "car": car,
                "lot": {
                    "fuel_type": "ELECTRIC",
                    "price_source": "Buy Now",
                    "price_usd": 7899.0,
                },
            },
        )


class _LeadBaseTools:
    def __init__(self):
        self.created_lead = None

    async def create_lead(self, *, tg_login, tg_id, data, method):
        self.created_lead = {
            "tg_login": tg_login,
            "tg_id": tg_id,
            "data": data,
            "method": method,
        }
        return ToolResult(ok=True, message="ok")


class _JudgeRunnable:
    async def ainvoke(self, messages):
        return LeadDecision(
            ready=True,
            confidence=0.91,
            manager_summary=(
                "Клиент заинтересован в услуге подбора авто человеком, конкретную модель не выбрал. "
                "Просит менеджера связаться и помочь подобрать вариант под бюджет."
            ),
        )


def _deps_with_base_tools(base_tools):
    return ReActDependencies(
        llm=object(),
        rag=object(),
        base_tools=base_tools,
        metrics=_Metrics(),
        judge_runnable=object(),
        lead_confidence_threshold=0.75,
        search_result_count=3,
        rag_top_k=4,
        cars_catalog_path=Path("data/ai_manager/cars.md"),
    )


@pytest.mark.asyncio
async def test_lookup_auction_lot_does_not_resend_already_shown_card():
    turn = {
        "cars": [],
        "last_shown_cars": [{"lot_number": "90141575"}],
    }
    token = set_turn(turn)
    try:
        tools = make_react_tool_list(_deps_with_base_tools(_BaseTools()))
        lookup_tool = next(tool for tool in tools if tool.name == "lookup_auction_lot")

        result = await lookup_tool.ainvoke({"lot_or_url": "90141575"})
    finally:
        reset_turn(token)

    assert turn["cars"] == []
    assert "Карточка уже была отправлена ранее" in result


@pytest.mark.asyncio
async def test_submit_lead_to_crm_sends_manager_summary_without_selected_car():
    base_tools = _LeadBaseTools()
    deps = ReActDependencies(
        llm=object(),
        rag=object(),
        base_tools=base_tools,
        metrics=_Metrics(),
        judge_runnable=_JudgeRunnable(),
        lead_confidence_threshold=0.75,
        search_result_count=3,
        rag_top_k=4,
        cars_catalog_path=Path("data/ai_manager/cars.md"),
    )
    turn = {
        "user_id": 123,
        "username": "ivan_auto",
        "user_context": {"name": "Иван", "username": "ivan_auto"},
        "last_shown_cars": [],
    }
    messages = [
        HumanMessage(content="Хочу, чтобы менеджер сам подобрал мне машину из США."),
        AIMessage(content="Да, можем передать заявку менеджеру."),
        HumanMessage(content="Да, передайте, пусть свяжется."),
    ]
    token = set_turn(turn)
    try:
        tools = make_react_tool_list(deps)
        submit_tool = next(tool for tool in tools if tool.name == "submit_lead_to_crm")

        result = await submit_tool.ainvoke(
            {
                "state": {"messages": messages},
                "user_note": "Клиент хочет подбор авто человеком",
            }
        )
    finally:
        reset_turn(token)

    assert "Лид передан" in result
    assert base_tools.created_lead["method"] == "ai_manager_chat"
    assert base_tools.created_lead["data"]["selected_lot"] is None
    assert "подбора авто человеком" in base_tools.created_lead["data"]["dialog_summary"]
