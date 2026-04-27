import pytest

from app.infrastructure.services import bitrix_utils


def test_get_bitrix_base_url_requires_env(monkeypatch):
    monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

    with pytest.raises(RuntimeError, match="BITRIX_WEBHOOK_URL"):
        bitrix_utils._get_bitrix_base_url()


def test_get_bitrix_base_url_uses_env(monkeypatch):
    monkeypatch.setenv("BITRIX_WEBHOOK_URL", "https://example.bitrix24.by/rest/1/token/")

    assert (
        bitrix_utils._get_bitrix_base_url()
        == "https://example.bitrix24.by/rest/1/token/crm.lead.add.json"
    )


def test_ai_manager_bitrix_fields_include_lead_details():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={
            "name": "Иван",
            "phone": "+375291112233",
            "intent": "search_cars",
            "brand": "Toyota",
            "model": "Camry",
            "budget": "20000",
            "selected_lot": "123456",
            "confidence": 0.9,
            "dialog_summary": (
                "Клиент интересуется Toyota Camry в бюджете около 20 000$. "
                "Просит менеджера проверить варианты и связаться в Telegram."
            ),
        },
        method="ai_manager_chat",
    )

    comments = fields["FIELDS[COMMENTS]"]
    assert "Toyota" in comments
    assert "Camry" in comments
    assert "20000" in comments
    assert "123456" in comments
    assert "Саммари для менеджера" in comments
    assert "Просит менеджера проверить варианты" in comments


def test_raise_for_bitrix_error_rejects_json_error_payload():
    with pytest.raises(RuntimeError, match="INVALID_CREDENTIALS"):
        bitrix_utils._raise_for_bitrix_error(
            {
                "error": "INVALID_CREDENTIALS",
                "error_description": "Bad webhook",
            }
        )
