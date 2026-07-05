import pytest

from app.infrastructure.services import bitrix_utils


def test_get_bitrix_base_url_rejects_empty_webhook():
    with pytest.raises(RuntimeError, match="BITRIX_WEBHOOK_URL"):
        bitrix_utils._get_bitrix_base_url("")


def test_get_bitrix_base_url_builds_lead_endpoint():
    assert (
        bitrix_utils._get_bitrix_base_url("https://example.bitrix24.by/rest/1/token/")
        == "https://example.bitrix24.by/rest/1/token/crm.lead.add.json"
    )


def test_unsupported_bitrix_method_is_rejected():
    with pytest.raises(ValueError, match="Unsupported bitrix method"):
        bitrix_utils._build_fields(
            tg_login="user",
            tg_id=123,
            data={},
            method="unknown_method",
        )


def test_raise_for_bitrix_error_rejects_json_error_payload():
    with pytest.raises(RuntimeError, match="INVALID_CREDENTIALS"):
        bitrix_utils._raise_for_bitrix_error(
            {
                "error": "INVALID_CREDENTIALS",
                "error_description": "Bad webhook",
            }
        )
