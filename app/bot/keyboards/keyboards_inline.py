from aiogram.enums import ButtonStyle
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callback_data import SubscribeCB, ViewSubscriptionCB
from app.infrastructure.database.models import SelfSelectionRow
from app.lexicon.lexicon_ru import (
    LEXICON_ADMIN_BUTTONS_RU,
    LEXICON_BUTTONS_RU,
)

ChoiceButton = (
    str
    | tuple[str | CallbackData, str]
    | tuple[str | CallbackData, ButtonStyle]
    | tuple[str | CallbackData, str, ButtonStyle]
)


# Функция, генерирующая клавиатуру для выбора пользователем дальнейшего шага
def create_choice_keyboard(*buttons: ChoiceButton, width: int = 2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    items = []
    for button in buttons:
        style: ButtonStyle | None = None
        if isinstance(button, tuple):
            if len(button) == 3:
                callback, text_key, style = button
            else:
                first, second = button
                if isinstance(second, ButtonStyle):
                    callback, text_key, style = first, first, second
                else:
                    callback, text_key = first, second
        else:
            callback, text_key = button, button
        text = LEXICON_BUTTONS_RU.get(text_key, text_key)
        callback_data = callback.pack() if isinstance(callback, CallbackData) else callback
        items.append(InlineKeyboardButton(
            text=text, callback_data=callback_data, style=style
        ))
    kb_builder.row(*items, width=width)
    return kb_builder.as_markup()


SITE_URL = "https://americatrade.by"
REVIEWS_YANDEX_URL = "https://yandex.by/maps/org/america_trade/209802914458/reviews/?ll=27.562783%2C53.871084&z"
REVIEWS_GOOGLE_URL = "https://www.google.com/maps/place/America+Trade/@53.8715902,27.5585072,16z/data=!4m8!3m7!1s0x46dbd10c8f4ca66d:0xc0b4e3cdc9108439!8m2!3d53.8711443!4d27.5627987!9m1!1b1!16s%2Fg%2F11wfs6slw5?entry=ttu&g_ep=EgoyMDI1MDcyMy4wIKXMDSoASAFQAw%3D%3D"


# Функция, генерирующая клавиатуру экрана "✅ Контакт получен!"
def create_contact_received_keyboard() -> InlineKeyboardMarkup:
    return create_choice_keyboard(
        "more_information_button",
        "back_to:main_menu",
        width=1,
    )


# Функция, генерирующая клавиатуру раздела "⭐ Почему именно AmericaTrade?".
# show_back добавляет кнопку "Назад" (возврат в хаб) - только при заходе из хаба
def create_why_americatrade_keyboard(show_back: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["free_consultation_button"],
            callback_data="application_for_selection_button",
            style=ButtonStyle.SUCCESS,
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_yandex_long_button"],
            url=REVIEWS_YANDEX_URL,
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_google_long_button"],
            url=REVIEWS_GOOGLE_URL,
        ),
    ]
    if show_back:
        buttons.append(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_button"],
                callback_data="back_to:info_hub",
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["back_to:main_menu"],
            callback_data="back_to:main_menu",
        )
    )
    kb.row(*buttons, width=1)
    return kb.as_markup()


# Функция, генерирующая клавиатуру экрана "Помощь и контакты"
def create_contacts_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["url_site_button"], url=SITE_URL
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_yandex_button"],
            url=REVIEWS_YANDEX_URL,
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_google_button"],
            url=REVIEWS_GOOGLE_URL,
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["free_consultation_button"],
            callback_data="application_for_selection_button",
            style=ButtonStyle.SUCCESS,
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["back_button"],
            callback_data="back_to:main_menu",
        ),
        width=1,
    )
    return kb.as_markup()


# Функция, генерирующая клавиатуру действий после выдачи авто по марке/модели.
# Кнопки расчета по конкретному авто идут отдельными сообщениями под
# каждой медиагруппой (см. safe_send_media_group).
def create_self_results_keyboard(*, else_car: bool = True) -> InlineKeyboardMarkup:
    kb_builder = InlineKeyboardBuilder()

    action_buttons = [
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["follow_model_button"],
            callback_data=SubscribeCB(source="self").pack(),
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["change_request_button"],
            callback_data="change_request_button",
        ),
    ]
    if else_car:
        action_buttons.append(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["else_car_button"],
                callback_data="else_car_button_self",
            )
        )
    action_buttons.append(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["self_request_button"],
            callback_data="self_request_button",
            style=ButtonStyle.SUCCESS,
        )
    )

    kb_builder.row(*action_buttons, width=1)

    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру экрана "👀 Оставьте ваш номер телефона..."
def create_self_lead_keyboard() -> InlineKeyboardMarkup:
    return create_choice_keyboard(
        ("send_phone_inline", "send_my_phone_button", ButtonStyle.SUCCESS),
        "change_request_button",
        "back_to:main_menu",
        width=1,
    )


# Функция, генерирующая клавиатуру действий после ТОП-подборки по кузову/бюджету
def create_assisted_results_keyboard() -> InlineKeyboardMarkup:
    return create_choice_keyboard(
        ("change_request_assisted", "change_request_button"),
        ("else_car_button_assisted", "else_car_button"),
        ("self_request_button", "self_request_button", ButtonStyle.SUCCESS),
        width=1,
    )


def format_date(created_at) -> str:
    """Форматирует дату в строку DD.MM.YYYY"""
    if hasattr(created_at, "strftime"):
        return created_at.strftime("%Y-%m-%d")
    else:
        try:
            from datetime import datetime

            if isinstance(created_at, str):
                parsed_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                return parsed_date.strftime("%Y-%m-%d")
            else:
                return str(created_at)
        except ValueError:
            return str(created_at)


def create_subscriptions_keyboard(
    self_selection_subs: list[SelfSelectionRow] = None,
    show_back_button: bool = True,
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для отображения подписок пользователя

    Args:
        self_selection_subs: Список self selection подписок
        show_back_button: Показывать ли кнопку "Назад"

    Returns:
        InlineKeyboardMarkup: Готовая клавиатура
    """
    kb_builder = InlineKeyboardBuilder()

    # Добавляем кнопки для self selection подписок
    if self_selection_subs:
        for sub in self_selection_subs:
            date_str = format_date(sub.created_at)
            button_text = f"{date_str} ▪ {sub.brand} {sub.model} ▪ {sub.year}"
            kb_builder.add(
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=ViewSubscriptionCB(
                        source="self", subscription_id=sub.id
                    ).pack(),
                )
            )

    # Добавляем кнопку "Назад" если нужно
    if show_back_button:
        kb_builder.add(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_button"],
                callback_data="back_to:main_menu",
            )
        )

    # Настраиваем расположение кнопок (по одной в строке)
    kb_builder.adjust(1)

    return kb_builder.as_markup()


def create_admin_keyboard(*buttons: str, width: int = 2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=LEXICON_ADMIN_BUTTONS_RU[button]
                if button in LEXICON_ADMIN_BUTTONS_RU
                else button,
                callback_data=button,
            )
            for button in buttons
        ],
        width=width,
    )
    return kb_builder.as_markup()
