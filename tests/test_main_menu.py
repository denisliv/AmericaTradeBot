"""Main menu and contacts branch must match the Miro conversation-flow diagram verbatim."""

from aiogram.enums import ButtonStyle

from app.bot.handlers.users import create_info_hub_keyboard
from app.bot.keyboards.keyboards_inline import (
    REVIEWS_GOOGLE_URL,
    REVIEWS_YANDEX_URL,
    SITE_URL,
    create_choice_keyboard,
    create_contact_received_keyboard,
    create_contacts_keyboard,
    create_why_americatrade_keyboard,
)
from app.bot.keyboards.keyboards_reply import create_call_request_keyboard
from app.lexicon.lexicon_ru import LEXICON_RU

MAIN_MENU_BUTTONS = (
    "choose_a_car_button",
    "more_information_button",
    "why_americatrade_button",
    "contact_button",
)


def test_start_text_matches_diagram():
    text = LEXICON_RU["/start_text"]("Денис")
    assert text == (
        "👋 Здравствуйте, Денис!\r\n"
        "На связи компания AmericaTrade. Мы уже более 10 лет помогаем подбирать "
        "и доставлять автомобили из США в Беларусь - выгодно, безопасно и с полным "
        "сопровождением вплоть до постановки авто на учет.\r\n\n"
        "Здесь вы можете:\r\n"
        "- Узнать все об особенностях авто из США\r\n"
        "- Первым видеть самые горячие лоты на аукционах\r\n"
        "- Подписаться на обновления по интересующим вас маркам и моделям"
    )


def test_main_menu_buttons_match_diagram():
    keyboard = create_choice_keyboard(*MAIN_MENU_BUTTONS, width=1)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == [
        "✅ Подобрать авто из США",
        "🤔 Все об авто из США",
        "⭐ Почему именно AmericaTrade?",
        "🙎‍♂️ Помощь и контакты",
    ]


def test_contacts_text_matches_diagram():
    assert LEXICON_RU["contacts_text"] == (
        "<b>Контакты AmericaTrade: </b>\r\n\n"
        "📞 +375 44 723-24-25\r\n"
        "<a href='https://www.instagram.com/americatrade.by'>📱 Инстаграм</a>\r\n"
        "<a href='https://t.me/americatradeby'>📱 Телеграм канал</a>\r\n"
        "<a href='https://www.tiktok.com/@americatrade'>📱 Тик-ток</a>\r\n"
        "📧 info@americatrade.by\r\n\n"
        "г. Минск, ул. Либаво-Роменская, 23, офис 816"
    )


def test_contacts_keyboard_matches_diagram():
    keyboard = create_contacts_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [button.text for button in buttons] == [
        "Наш сайт",
        "⭐ Отзывы Яндекс",
        "⭐ Отзывы Google",
        "✅ Оставить заявку на бесплатную консультацию",
        "🔙 Назад",
    ]
    assert [button.url for button in buttons[:3]] == [
        SITE_URL,
        REVIEWS_YANDEX_URL,
        REVIEWS_GOOGLE_URL,
    ]
    # CTA (зеленая) ведет в флоу заявки, "Назад" - на шаг назад (главное меню)
    assert buttons[3].callback_data == "application_for_selection_button"
    assert buttons[3].style == ButtonStyle.SUCCESS
    assert buttons[4].callback_data == "back_to:main_menu"


def test_info_hub_text_matches_diagram():
    assert LEXICON_RU["more_information_text"] == (
        "<b>🇺🇸 Авто из США - это не миф о дешевизне</b>\r\n\n"
        "Это реальная экономия до 40% по сравнению с авторынком РБ\r\n"
        "Американский рынок - один из крупнейших в мире. Здесь можно найти "
        "комплектации, которых нет на других рынках, по ценам, которые заставят "
        "вас удивиться.\r\n\n"
        "Мы работаем на этом рынке и знаем каждый шаг пути - от аукциона в Штатах "
        "до вашего гаража в Беларуси.\r\n\n"
        "Выберите, что вас интересует:"
    )


def test_info_hub_keyboard_matches_diagram():
    keyboard = create_info_hub_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "💰Почему авто из США - это выгодно?",
        "⌛ Как происходит процесс покупки авто?",
        "🔨 На каких аукционах происходит покупка?",
        "💸 Из чего складывается цена?",
        "⭐ Почему именно AmericaTrade?",
        "🔙 Назад",
    ]
    # Из хаба раздел "Почему AmericaTrade" открывается со своим callback,
    # чтобы показать в нем кнопку "Назад"
    assert buttons[4].callback_data == "why_americatrade_from_hub"


def test_info_sections_have_diagram_headers():
    # Каждый раздел хаба начинается с заголовка из диаграммы
    expected_headers = {
        "why_profitable_text": "<b>🤔  Почему авто из США - это выгодно?</b>",
        "purchasing_process_text": "<b>🤔  Как происходит процесс покупки авто из США?</b>",
        "auctions_text": "<b>🤔 На каких аукционах происходит покупка?</b>",
        "price_breakdown_text": "<b>🤔 Из чего складывается итоговая цена авто из США?</b>",
        "why_americatrade_text": "<b>🤔 Почему именно AmericaTrade?</b>",
    }
    for key, header in expected_headers.items():
        assert LEXICON_RU[key].startswith(header), key


def test_why_profitable_highlights_market_comparison_block():
    # Красный пунктирный блок с диаграммы выделен цитатой перед "Мы делаем иначе"
    text = LEXICON_RU["why_profitable_text"]
    quote_start = text.index("<blockquote><b>Как это работает на рынке:</b>")
    quote_end = text.index("</blockquote>")
    assert quote_start < quote_end < text.index("<b>Мы делаем иначе")


def test_why_americatrade_keyboard_matches_diagram():
    keyboard = create_why_americatrade_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [button.text for button in buttons] == [
        "✅ Оставить заявку на бесплатную консультацию",
        "⭐ Посмотреть отзывы в Яндекс",
        "⭐ Посмотреть отзывы в Google",
        "В меню",
    ]
    assert buttons[0].callback_data == "application_for_selection_button"
    assert buttons[1].url == REVIEWS_YANDEX_URL
    assert buttons[2].url == REVIEWS_GOOGLE_URL
    assert buttons[3].callback_data == "back_to:main_menu"


def test_why_americatrade_keyboard_from_hub_has_back_button():
    # При заходе из хаба между CTA и "В меню" появляется "Назад" (возврат в хаб)
    keyboard = create_why_americatrade_keyboard(show_back=True)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons[-2:]] == [
        ("🔙 Назад", "back_to:info_hub"),
        ("В меню", "back_to:main_menu"),
    ]


def test_consultation_intro_matches_diagram():
    assert LEXICON_RU["consultation_intro_text"] == (
        "🎯 Отлично! Мы передадим запрос менеджеру, он свяжется с вами, уточнит "
        "детали, ответит на все ваши вопросы и поможет с выбором\r\n\n"
        "Чтобы вы могли получить бесплатную консультацию, оставьте ваш номер телефона"
    )
    # Отправка номера в два шага: зеленая инлайн-кнопка + "В меню" для выхода
    keyboard = create_choice_keyboard(
        ("send_phone_inline", "send_my_phone_button", ButtonStyle.SUCCESS),
        "back_to:main_menu",
        width=1,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("📞 Отправить мой номер", "send_phone_inline"),
        ("В меню", "back_to:main_menu"),
    ]
    assert buttons[0].style == ButtonStyle.SUCCESS
    # Второй шаг - reply-кнопка, отправляющая контакт
    reply_keyboard = create_call_request_keyboard(text_key="send_my_phone_button")
    reply_buttons = [button for row in reply_keyboard.keyboard for button in row]
    assert [(button.text, button.request_contact) for button in reply_buttons] == [
        ("📞 Отправить мой номер", True),
    ]


def test_contact_received_matches_diagram():
    assert LEXICON_RU["contact_received_text"] == (
        "✅ Контакт получен!\r\n"
        "Наш менеджер уже видит ваш запрос и свяжется в ближайшее время. "
        "А пока  можете узнать подробнее об авто из США"
    )
    keyboard = create_contact_received_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🤔 Все об авто из США", "more_information_button"),
        ("В меню", "back_to:main_menu"),
    ]


def test_info_section_keyboard_has_consultation_back_and_menu():
    keyboard = create_choice_keyboard(
        ("application_for_selection_button", "free_consultation_button"),
        ("back_to:info_hub", "back_button"),
        "back_to:main_menu",
        width=1,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        (
            "✅ Оставить заявку на бесплатную консультацию",
            "application_for_selection_button",
        ),
        ("🔙 Назад", "back_to:info_hub"),
        ("В меню", "back_to:main_menu"),
    ]
