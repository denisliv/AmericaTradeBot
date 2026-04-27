from app.infrastructure.services.ai_manager import prompts
from app.infrastructure.services.ai_manager.prompts import (
    LEAD_JUDGE_PROMPT,
    REACT_SYSTEM_PROMPT,
)


def test_prompt_does_not_request_lot_or_vin_before_showing_cards():
    prompt = REACT_SYSTEM_PROMPT.lower()

    assert "не проси vin" in prompt
    assert "номер лота" in prompt
    assert "до того как" in prompt


def test_prompt_mentions_budget_only_catalog_recommendations():
    prompt = REACT_SYSTEM_PROMPT.lower()

    assert "3-4" in prompt
    assert "бюджет" in prompt
    assert "cars.md" in prompt


def test_prompt_avoids_permission_loop_for_selected_lot():
    prompt = REACT_SYSTEM_PROMPT.lower()

    assert "не спрашивай разрешение повторно" in prompt
    assert "estimate_landed_cost_for_lot" in prompt
    assert "не обещай отправить карточку" in prompt


def test_prompt_requires_catalog_based_rough_estimate_and_repair_caveat():
    prompt = REACT_SYSTEM_PROMPT.lower()

    assert "cars.md" in prompt
    assert "примерный диапазон" in prompt
    assert "ремонт" in prompt
    assert "после передачи в crm" in prompt


def test_only_runtime_prompts_are_exported():
    assert not hasattr(prompts, "SYSTEM_PROMPT_V2")


def test_lead_judge_allows_human_selection_service_without_car_choice():
    prompt = LEAD_JUDGE_PROMPT.lower()

    assert "подбор человеком" in prompt
    assert "услуг" in prompt
    assert "без выбранного авто" in prompt
    assert "manager_summary" in prompt
