"""Точечные правки из отзыва заказчика после тестирования бота."""

import inspect

import pytest

from app.bot.handlers.self_selection import flow
from app.bot.keyboards.keyboards_inline import SITE_URL
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU


def test_site_link_carries_the_utm_tag():
    # По этой метке заказчик считает переходы из бота в аналитике сайта
    assert SITE_URL == "https://americatrade.by/?utm_source=telegram-bot"


def test_auctions_section_says_whole_cars_not_insurance_cars():
    assert "<b>Аукционы битых и целых авто:</b>" in LEXICON_RU["auctions_text"]
    assert "страховых авто" not in LEXICON_RU["auctions_text"]


def test_nothing_found_message_calls_to_leave_a_request():
    # Без призыва к действию клиент просто уходит из бота
    text = LEXICON_RU["nothing_found_text"]

    assert text.endswith(
        "под Ваши критерии. Можете оставить заявку и менеджер поможет "
        "с подбором автомобиля."
    )


def test_volkswagen_model_button_has_no_trim_suffix():
    models = LEXICON_FORM_BUTTONS_RU["model_buttons"]["VOLKSWAGEN"]

    assert "TAOS" in models
    assert "TAOS SE" not in models


@pytest.mark.parametrize(
    "notice",
    ["Клайпед", "Поти", "2021-2023 годов выпуска"],
)
def test_criteria_steps_show_no_popup_notices(notice):
    """Всплывающие окна после каждого выбора раздражали клиента, их убрали."""
    assert notice not in inspect.getsource(flow)
