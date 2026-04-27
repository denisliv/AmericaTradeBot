from app.infrastructure.services.ai_manager.agent_graph import (
    _user_context_system_message,
    _user_context_to_dict,
)
from app.infrastructure.services.ai_manager import prompts, schemas
from app.infrastructure.services.ai_manager.schemas import UserContext


def test_user_context_system_message_contains_db_facts():
    message = _user_context_system_message(
        {
            "name": "Иван",
            "username": "ivan_auto",
            "self_subscriptions_count": 1,
            "latest_self_request": {
                "brand": "Toyota",
                "model": "Camry",
                "year": "2021-2023",
            },
        }
    )

    assert "user_context" in message.content
    assert "Иван" in message.content
    assert "Toyota" in message.content
    assert "Camry" in message.content


def test_user_context_system_message_separates_views_assisted_and_subscriptions():
    message = _user_context_system_message(
        {
            "name": "Иван",
            "username": "ivan_auto",
            "active_car_count": 2,
            "recent_self_selection_requests": [
                {
                    "id": 21,
                    "brand": "BMW",
                    "model": "X5",
                    "year": "2022-2024",
                    "odometer": "до 60000",
                    "auction_status": "buy_now",
                },
                {
                    "id": 20,
                    "brand": "Audi",
                    "model": "Q7",
                    "year": "2021-2023",
                },
            ],
            "latest_assisted_request": {
                "id": 25,
                "body_style": "электромобиль",
                "budget": "50000+",
            },
            "self_subscriptions": [
                {
                    "id": 23,
                    "brand": "PORSCHE",
                    "model": "ALL MODELS",
                    "year": "2024-2025",
                    "odometer": "не важно",
                    "auction_status": "все варианты",
                }
            ],
        }
    )

    assert "recent_self_selection_requests" in message.content
    assert "latest_assisted_request" in message.content
    assert "self_subscriptions" in message.content
    assert "BMW" in message.content
    assert "электромобиль" in message.content
    assert "PORSCHE" in message.content


def test_user_context_to_dict_preserves_subscription_details_and_recent_views():
    ctx = UserContext(
        user_id=42,
        username="ivan_auto",
        name="Иван",
        active_car_count=2,
        recent_self_selection_requests=[
            {
                "id": 21,
                "brand": "BMW",
                "model": "X5",
                "year": "2022-2024",
            }
        ],
        self_subscriptions=[
            {
                "id": 23,
                "brand": "PORSCHE",
                "model": "ALL MODELS",
                "year": "2024-2025",
            }
        ],
        latest_assisted_request={"id": 25, "body_style": "электромобиль"},
    )

    user_context = _user_context_to_dict(ctx)

    assert user_context["recent_self_selection_requests"][0]["brand"] == "BMW"
    assert user_context["self_subscriptions"][0]["brand"] == "PORSCHE"
    assert user_context["self_subscriptions_count"] == 1
    assert user_context["latest_assisted_request"]["id"] == 25


def test_dead_plan_and_execute_artifacts_are_removed():
    assert not hasattr(prompts, "CLASSIFIER_PROMPT")
    assert not hasattr(prompts, "PLANNER_PROMPT")
    assert not hasattr(prompts, "RESPONDER_PROMPT")
    assert not hasattr(schemas, "StateClassification")
    assert not hasattr(schemas, "ExecutionPlan")
