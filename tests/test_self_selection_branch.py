"""Branch "🚗 Да, указать марку и модель" must match the Miro diagram."""

from aiogram.enums import ButtonStyle

from app.bot.keyboards.keyboards_inline import (
    create_choice_keyboard,
    create_self_lead_keyboard,
    create_self_results_keyboard,
)
from app.lexicon.lexicon_ru import (
    LEXICON_FORM_BUTTONS_RU,
    LEXICON_RU,
    LEXICON_RU_CSV,
)


def test_year_buttons_match_diagram():
    assert LEXICON_FORM_BUTTONS_RU["year_buttons"] == [
        "до 2016",
        "2016-2020",
        "2021-2023",
        "2024-2026",
        "Любой год",
    ]


def test_search_years_have_csv_mappings():
    # "до 2016" ведет на консультацию и в CSV-поиск не попадает
    for year in LEXICON_FORM_BUTTONS_RU["year_buttons"]:
        if year == "до 2016":
            continue
        year_range = LEXICON_RU_CSV[year]
        assert len(year_range) == 2 and year_range[0] <= year_range[1], year


def test_self_lead_screen_matches_diagram():
    assert LEXICON_RU["self_lead_intro_text"] == (
        "👀 Оставьте ваш номер телефона и наш менеджер свяжется с вами в ближайшее "
        "время - уточнит детали по вашему запросу, ответит на ваши вопросы "
        "и предоставит детальный расчет\r\n\n"
        "Консультация бесплатная, без обязательств"
    )
    keyboard = create_self_lead_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("📞 Отправить мой номер", "send_phone_inline"),
        ("🚗 Изменить запрос", "change_request_button"),
        ("В меню", "back_to:main_menu"),
    ]


def test_car_selected_mark_names_the_car():
    # Отметка выбора заменяет кнопку карточки, экран телефона приходит ниже
    assert LEXICON_RU["car_selected_text"]("BMW X5") == (
        "✅ Вы выбрали: <b>BMW X5</b>"
    )


def test_old_year_lead_text_matches_diagram():
    assert LEXICON_RU["old_year_lead_text"] == (
        "👀 Видим, мы уже на пути к приобретению авто.\r\n\n"
        "На аукционах варианты обновляются каждый день, наш менеджер может "
        "проконсультировать по всем нюансам.\r\n\n"
        "Оставьте ваш номер телефона для бесплатной консультации."
    )


def test_auction_status_buttons_are_blue():
    keyboard = create_choice_keyboard(
        *(
            (callback_data, text_key, ButtonStyle.PRIMARY)
            for callback_data, text_key in LEXICON_FORM_BUTTONS_RU[
                "auction_status_buttons"
            ]
        ),
        width=1,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("Фиксированная цена КУПИТЬ СЕЙЧАС 🔥", "Только BUY NOW"),
        ("Все варианты", "Все варианты"),
    ]
    assert all(button.style == ButtonStyle.PRIMARY for button in buttons)


def test_self_results_keyboard_matches_diagram():
    keyboard = create_self_results_keyboard(else_car=True)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🔔 Следить за вариантами по модели", "sub_new:self"),
        ("🚗 Изменить запрос", "change_request_button"),
        ("Подобрать еще", "else_car_button_self"),
        ("Оставить заявку на бесплатный подбор", "self_request_button"),
    ]


def test_self_results_keyboard_without_pagination():
    keyboard = create_self_results_keyboard(else_car=False)
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "else_car_button_self" not in callbacks
