from types import SimpleNamespace

from app.infrastructure.services.ai_manager.service import _chat_openai_kwargs


def test_chat_openai_kwargs_supports_gpt_5_mini():
    config = SimpleNamespace(
        openai=SimpleNamespace(
            api_key="key",
            base_url="https://api.openai.com/v1",
            model_name="gpt-5-mini",
        )
    )

    kwargs = _chat_openai_kwargs(config)

    assert kwargs["model_name"] == "gpt-5-mini"
    assert kwargs["reasoning_effort"] == "low"


def test_chat_openai_kwargs_omits_reasoning_for_legacy_chat_models():
    config = SimpleNamespace(
        openai=SimpleNamespace(
            api_key="key",
            base_url="https://api.openai.com/v1",
            model_name="gpt-3.5-turbo",
        )
    )

    kwargs = _chat_openai_kwargs(config)

    assert "reasoning_effort" not in kwargs
