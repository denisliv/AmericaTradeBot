"""LangChain tools for the ReAct AI manager (RAG, cars.md, CSV, CRM)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from psycopg import AsyncConnection

from app.infrastructure.services.ai_manager.cars_catalog import (
    load_cars_catalog,
    recommend_catalog_examples_by_budget,
    search_catalog_examples,
)
from app.infrastructure.services.ai_manager.knowledge_base import KnowledgeBaseService
from app.infrastructure.services.ai_manager.lead_utils import (
    delta_from_card,
    last_user_message_text,
    pick_card_for_lead,
    short_history_text,
)
from app.infrastructure.services.ai_manager.metrics import AIManagerMetrics
from app.infrastructure.services.ai_manager.prompts import LEAD_JUDGE_PROMPT
from app.infrastructure.services.ai_manager.schemas import (
    CarCard,
    CollectedInfo,
    LeadDecision,
)
from app.infrastructure.services.ai_manager.tools import AIManagerTools
from app.infrastructure.services.ai_manager.turn_context import get_turn

logger = logging.getLogger(__name__)


@dataclass
class ReActDependencies:
    """Closures for tools (per-process). Turn-scoped data lives in turn_context."""

    llm: BaseChatModel
    rag: KnowledgeBaseService
    base_tools: AIManagerTools
    metrics: AIManagerMetrics
    judge_runnable: Any  # RunnableSequence returning LeadDecision
    lead_confidence_threshold: float
    search_result_count: int
    rag_top_k: int
    cars_catalog_path: Path


def _inc_tool(metrics: AIManagerMetrics, name: str) -> None:
    metrics.inc_tool(name)


def make_react_tool_list(deps: ReActDependencies) -> list:
    @tool
    async def retrieve_company_knowledge(query: str) -> str:
        """Факты о компании AmericaTrade, аукционах, доставке, договоре, таможне. Передавай сформулированный поисковый запрос на русском или английском."""
        _inc_tool(deps.metrics, "retrieve_company_knowledge")
        if not (query or "").strip():
            return "Пустой запрос."
        try:
            ctx = deps.rag.retrieve(query.strip(), k=deps.rag_top_k)
        except Exception as exc:
            logger.warning("RAG retrieve failed: %s", exc)
            return "В базе знаний сейчас ничего не нашлось. Скажи клиенту, что уточнишь у менеджера."
        if ctx:
            deps.metrics.inc_rag_hits()
        else:
            deps.metrics.inc_rag_miss()
        lines: list[str] = []
        for i, c in enumerate(ctx[:6], 1):
            section = c.get("section", "")
            content = (c.get("content") or "")[:900]
            lines.append(f"[{i}] {section}\n{content}")
        if not lines:
            return "Релевантных фрагментов в базе знаний нет. Не придумывай цифры; предложи связаться с менеджером."
        return "Фрагменты из knowledge base:\n" + "\n\n".join(lines)

    @tool
    def search_cars_markdown_catalog(
        body_or_category: Optional[str] = None,
        budget_usd: Optional[int] = None,
        mode: str = "full_section",
    ) -> str:
        """Справочные ПРИМЕРЫ авто из файла `cars.md` (не лоты аукциона). Кузов/EV + бюджет в USD. mode: full_section | one_per_price_band (по одному примеру в каждой ценовой группе) | all_in_category (всё в разделе)."""
        _inc_tool(deps.metrics, "search_cars_markdown_catalog")
        cat = load_cars_catalog(deps.cars_catalog_path)
        m_norm = (mode or "full_section").strip()
        if budget_usd is not None and not body_or_category:
            text, _entries = recommend_catalog_examples_by_budget(
                catalog=cat,
                budget_usd=budget_usd,
                limit=4,
            )
            return text
        if m_norm not in ("full_section", "one_per_price_band", "all_in_category"):
            m_norm = "full_section"
        text, _entries = search_catalog_examples(
            catalog=cat,
            body_or_category=body_or_category,
            budget_usd=budget_usd,
            mode=m_norm,  # type: ignore[arg-type]
        )
        return text

    @tool
    async def search_auction_cars(
        brand: Optional[str] = None,
        model: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        budget_from_usd: Optional[int] = None,
        budget_to_usd: Optional[int] = None,
        odometer_from_km: Optional[int] = None,
        odometer_to_km: Optional[int] = None,
        fuel_type: Optional[str] = None,
        body_style: Optional[str] = None,
        buy_now_only: bool = False,
    ) -> str:
        """Найти реальные лоты Copart в salesdata.csv с фото. Нужен хотя бы один ориентир: бренд+модель+год/бюджет, или бренд+год, или тип топлива/кузова+год/бюджет."""
        _inc_tool(deps.metrics, "search_auction_cars")
        turn = get_turn()
        info = CollectedInfo(
            brand=brand,
            model=model,
            year_from=year_from,
            year_to=year_to,
            budget_from_usd=budget_from_usd,
            budget_to_usd=budget_to_usd,
            odometer_from_km=odometer_from_km,
            odometer_to_km=odometer_to_km,
            fuel_type=(fuel_type or None),
            body_style=body_style,
            buy_now_only=buy_now_only or None,
        )
        if not info.search_ready():
            return (
                "Недостаточно критериев для поиска по аукциону. "
                f"Соберите: {', '.join(info.missing_for_search())} (или сузьте запрос). "
            )
        result = await deps.base_tools.search_cars_by_ranges(
            info=info, count=deps.search_result_count
        )
        if not result.ok:
            return result.message
        payload = result.payload or {}
        cars_raw = payload.get("cars") or []
        cars = [
            car.model_dump()
            if isinstance(car, CarCard)
            else CarCard.model_validate(car).model_dump()
            for car in cars_raw
        ]
        relaxed = list(payload.get("relaxed_fields") or [])
        if cars:
            deps.metrics.add_cars_shown(len(cars))
        turn["cars"] = [CarCard.model_validate(c) for c in cars]
        turn["last_shown_cars"] = cars
        preview = [
            f"{c.get('year')} {c.get('make')} {c.get('model')} лот {c.get('lot_number')}"
            for c in cars[:5]
        ]
        note = f" Показано карточек: {len(cars)}."
        if relaxed:
            note += f" (критерии ослаблены: {', '.join(relaxed)})"
        if not cars:
            return (
                result.message or "Лотов нет."
            ) + " Предложи подписку на мониторинг."
        return "Найдены лоты: " + "; ".join(preview) + note

    @tool
    async def lookup_auction_lot(lot_or_url: str) -> str:
        """Найти конкретный лот Copart из salesdata.csv по номеру или ссылке и подготовить карточку пользователю."""
        _inc_tool(deps.metrics, "lookup_auction_lot")
        turn = get_turn()
        previous_cards = list(turn.get("last_shown_cars") or [])
        result = await deps.base_tools.lookup_lot_by_number(lot_or_url)
        if not result.ok:
            return result.message
        payload = result.payload or {}
        car = payload.get("car")
        if not isinstance(car, CarCard):
            car = CarCard.model_validate(car)
        already_shown = any(
            str(prev.get("lot_number") or "") == str(car.lot_number or "")
            for prev in previous_cards
        )
        if not already_shown:
            turn["cars"] = [car]
        turn["last_shown_cars"] = [car.model_dump()]
        lot = payload.get("lot") or {}
        detail_bits = [
            f"топливо={lot.get('fuel_type')}" if lot.get("fuel_type") else "",
            f"двигатель={lot.get('engine')}" if lot.get("engine") else "",
            f"привод={lot.get('drive')}" if lot.get("drive") else "",
            f"цена={lot.get('price_source')} ${lot.get('price_usd'):,.0f}".replace(
                ",", " "
            )
            if lot.get("price_usd")
            else "",
        ]
        details = "; ".join(bit for bit in detail_bits if bit)
        send_note = (
            "Карточка уже была отправлена ранее; не отправляй и не обещай ее повторно."
            if already_shown
            else "Карточка будет отправлена пользователю."
        )
        return (
            f"Лот найден: {car.year or ''} {car.make or ''} {car.model or ''} "
            f"№ {car.lot_number}. {details}. {send_note}"
        ).strip()

    @tool
    async def estimate_landed_cost_for_lot(
        lot_or_url: str = "",
        shipping_mode: str = "container",
        brand: Optional[str] = None,
        model: Optional[str] = None,
        year: Optional[int] = None,
        fuel_type: Optional[str] = None,
    ) -> str:
        """Посчитать примерную стоимость по лоту или по марке/модели/году с ориентиром из cars.md. Не отправляет карточку повторно."""
        _inc_tool(deps.metrics, "estimate_landed_cost_for_lot")
        result = await deps.base_tools.estimate_landed_cost_for_lot(
            lot_query=lot_or_url,
            shipping_mode=shipping_mode,
            brand=brand,
            model=model,
            year=year,
            fuel_type=fuel_type,
        )
        return result.message

    @tool
    async def quick_vehicle_specs(
        brand: str,
        model: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> str:
        """Быстро проверить по CSV тип топлива, кузов, двигатель, привод и трансмиссию для марки/модели/года. Используй для вопросов о растаможке и полной стоимости."""
        _inc_tool(deps.metrics, "quick_vehicle_specs")
        result = await deps.base_tools.quick_vehicle_specs(
            brand=brand,
            model=model,
            year_from=year_from,
            year_to=year_to,
        )
        if not result.ok:
            return result.message
        specs = result.payload.get("specs", {}) if result.payload else {}
        return (
            f"Характеристики по CSV для {brand} {model}: "
            f"топливо={', '.join(specs.get('fuel_types', [])) or 'нет данных'}; "
            f"кузов={', '.join(specs.get('body_styles', [])) or 'нет данных'}; "
            f"двигатель={', '.join(specs.get('engines', [])) or 'нет данных'}; "
            f"годы={', '.join(str(x) for x in specs.get('years', [])) or 'нет данных'}. "
            f"{result.message}"
        )

    @tool
    async def explain_landed_cost_components(user_question: str = "") -> str:
        """Объяснить из чего складывается цена авто под ключ без выдумывания точной итоговой суммы."""
        _inc_tool(deps.metrics, "explain_landed_cost_components")
        query = (
            "Из чего складывается стоимость авто под ключ: ставка, аукционные сборы, "
            "доставка, таможня, договор, оплата, сроки. " + (user_question or "")
        )
        try:
            ctx = deps.rag.retrieve(query, k=deps.rag_top_k)
        except Exception as exc:
            logger.warning("Cost components RAG failed: %s", exc)
            ctx = []
        if not ctx:
            return (
                "Точная стоимость под ключ требует расчета менеджера по конкретному лоту. "
                "Обычно учитываются ставка, аукционные сборы, доставка до Минска, таможня, "
                "банковские комиссии и услуга компании. Не называй итоговую сумму без расчета."
            )
        lines = [
            f"{item.get('section', '')}: {(item.get('content') or '')[:700]}"
            for item in ctx[:4]
        ]
        return (
            "Факты для объяснения стоимости под ключ из базы знаний:\n"
            + "\n\n".join(lines)
            + "\n\nНе называй точную итоговую сумму без расчета менеджера по конкретному лоту."
        )

    @tool
    async def register_monitoring_subscription() -> str:
        """Включить бесплатный мониторинг по последней self-selection заявке клиента. Используй только после явного согласия на подписку/мониторинг."""
        _inc_tool(deps.metrics, "register_monitoring_subscription")
        turn = get_turn()
        conn: AsyncConnection | None = turn.get("conn")
        user_id: int = turn.get("user_id", 0)
        user_ctx: dict[str, Any] = turn.get("user_context") or {}
        if not conn or not user_id:
            return "Нет соединения с БД, подписка не оформлена."
        if user_ctx.get("latest_self_request"):
            table = "self_selection_requests"
        else:
            return (
                "Сначала оформите заявку на самостоятельный подбор в боте, "
                "тогда мониторинг можно будет включить."
            )
        res = await deps.base_tools.add_subscription(
            conn, user_id=user_id, subscription_type=table
        )
        return res.message

    @tool
    async def submit_lead_to_crm(
        state: Annotated[dict, InjectedState],
        user_note: str = "",
    ) -> str:
        """Передать лид в CRM (Bitrix) после явного согласия клиента на связь с менеджером. Используй для выбранного авто/лота, консультации, договора, покупки или когда клиент без выбранного авто хочет подбор человеком / узнать услуги компании."""
        _inc_tool(deps.metrics, "submit_lead_to_crm")
        turn = get_turn() or {}
        messages = (state or {}).get("messages") or []
        last_user = last_user_message_text(list(messages))
        user_id: int = int(turn.get("user_id", 0))
        username: str | None = turn.get("username")
        last_shown: list[dict[str, Any]] = list(turn.get("last_shown_cars") or [])
        user_ctx: dict[str, Any] = turn.get("user_context") or {}
        history_summary = short_history_text(list(messages), max_items=8)

        collected = CollectedInfo()
        selected_card: dict[str, Any] | None = None
        if last_shown:
            selected_card = pick_card_for_lead(last_user, last_shown)
            if selected_card and (
                not collected.model
                or not collected.brand
                or (collected.year_from is None and collected.year_to is None)
            ):
                delta = delta_from_card(selected_card)
                if delta is not None:
                    collected = collected.merge(delta)

        has_contact = bool(user_ctx.get("username")) or bool(collected.contact_phone)
        if not has_contact:
            return (
                "Контакт для CRM не готов: попроси клиента оставить @username в Telegram "
                "или телефон."
            )

        judge_prompt = (
            f"last_user_message: {last_user}\n"
            f"user_note_from_tool: {user_note}\n"
            f"collected_info: {json.dumps(collected.model_dump(), ensure_ascii=False)}\n"
            f"user_context: {json.dumps({k: user_ctx.get(k) for k in ('name', 'username')}, ensure_ascii=False)}\n"
            f"history_summary:\n{history_summary}"
        )
        try:
            decision: LeadDecision = await deps.judge_runnable.ainvoke(
                [
                    SystemMessage(content=LEAD_JUDGE_PROMPT),
                    HumanMessage(content=judge_prompt),
                ]
            )
        except Exception as exc:
            logger.warning("Lead judge failed: %s", exc)
            return "Сервис заявок временно недоступен, попроси клиента написать менеджеру напрямую."

        if not decision.ready or decision.confidence < deps.lead_confidence_threshold:
            deps.metrics.inc_leads_rejected_by_judge()
            return (
                "Согласие неподтверждено или критерии неполные. Уточни намерение и согласие на передачу заявки, "
                f"(подсказка: {decision.reason})"
            )

        payload = {
            "name": user_ctx.get("name") or "Пользователь Telegram",
            "phone": collected.contact_phone or "",
            "source": "AI manager ReAct",
            "intent": last_user,
            "dialog_summary": decision.manager_summary or history_summary,
            "brand": collected.brand,
            "model": collected.model,
            "year_from": collected.year_from,
            "year_to": collected.year_to,
            "budget_from": collected.budget_from_usd,
            "budget_to": collected.budget_to_usd,
            "confidence": decision.confidence,
            "selected_lot": (selected_card or {}).get("lot_number")
            if selected_card
            else None,
        }
        lead_result = await deps.base_tools.create_lead(
            tg_login=username,
            tg_id=user_id,
            data=payload,
            method="ai_manager_chat",
        )
        if lead_result.ok:
            deps.metrics.inc_leads_ready()
            deps.metrics.inc_leads_sent()
            turn["lead_sent"] = True
            return (
                "Лид передан в CRM. Сообщи клиенту, что менеджер свяжется в Telegram."
            )
        return "Техническая ошибка передачи в CRM. Предложи оставить телефон или написать менеджеру напрямую."

    return [
        retrieve_company_knowledge,
        search_cars_markdown_catalog,
        search_auction_cars,
        lookup_auction_lot,
        quick_vehicle_specs,
        estimate_landed_cost_for_lot,
        explain_landed_cost_components,
        register_monitoring_subscription,
        submit_lead_to_crm,
    ]
