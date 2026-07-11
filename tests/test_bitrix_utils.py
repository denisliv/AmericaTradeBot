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


def test_consultation_lead_includes_body_and_budget_comment():
    # Эмодзи вырезаются: Bitrix (MySQL utf8) обрезает комментарий
    # на первом 4-байтовом символе, теряя весь остальной текст
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={
            "name": "Денис",
            "phone": "+375291234567",
            "body_style": "🚙 Кроссовер/SUV",
            "budget": "15 000$ - 20 000$",
        },
        method="consultation_request",
    )
    assert fields["FIELDS[COMMENTS]"] == (
        "Тип авто: Кроссовер/SUV | Бюджет: 15 000$ - 20 000$"
    )
    # Лид с выбранными критериями - это "Заявка"
    assert fields["FIELDS[TITLE]"] == "AmericaTradeBot | Заявка"


def test_consultation_lead_includes_selected_example():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={
            "name": "Денис",
            "phone": "+375291234567",
            "body_style": "🚗 Седан/Хэтчбек",
            "budget": "до 12 000$",
            "car_title": "Honda Accord",
        },
        method="consultation_request",
    )
    assert fields["FIELDS[COMMENTS]"] == (
        "Тип авто: Седан/Хэтчбек | Бюджет: до 12 000$ | Пример: Honda Accord"
    )


def test_consultation_lead_without_context_has_no_comment():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={"name": "Денис", "phone": "+375291234567"},
        method="consultation_request",
    )
    assert "FIELDS[COMMENTS]" not in fields
    # Без выбранных критериев (из информационных хабов) - "Консультация"
    assert fields["FIELDS[TITLE]"] == "AmericaTradeBot | Консультация"


def test_nurture_lead_title_marks_mailing_source():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={"name": "Денис", "phone": "+375291234567", "source": "nurture"},
        method="consultation_request",
    )
    assert fields["FIELDS[TITLE]"] == "AmericaTradeBot | По рассылке"


def test_consultation_lead_includes_chosen_car_with_lot_link():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={
            "name": "Денис",
            "phone": "+375291234567",
            "brand": "BMW",
            "model": "X5",
            "year": "2021-2023",
            "car_title": "BMW X5",
            "lot": "12345",
        },
        method="consultation_request",
    )
    assert fields["FIELDS[COMMENTS]"] == (
        "Марка: BMW | Модель: X5 | Год: 2021-2023 | Авто: BMW X5 | "
        "Лот №: 12345 | https://www.copart.com/lot/12345/"
    )


def test_consultation_lead_includes_manual_request_details():
    fields = bitrix_utils._build_fields(
        tg_login="user",
        tg_id=123,
        data={
            "name": "Денис",
            "phone": "+375291234567",
            "request_details": "Ищу Audi Q7 до 30 000$, желательно черную",
        },
        method="consultation_request",
    )
    assert fields["FIELDS[COMMENTS]"] == (
        "Запрос клиента: Ищу Audi Q7 до 30 000$, желательно черную"
    )


def test_raise_for_bitrix_error_rejects_json_error_payload():
    with pytest.raises(RuntimeError, match="INVALID_CREDENTIALS"):
        bitrix_utils._raise_for_bitrix_error(
            {
                "error": "INVALID_CREDENTIALS",
                "error_description": "Bad webhook",
            }
        )
