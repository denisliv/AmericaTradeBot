from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.infrastructure.database.orm_models import SelfSelectionRow
from app.lexicon.lexicon_ru import (
    LEXICON_ADMIN_BUTTONS_RU,
    LEXICON_BUTTONS_RU,
)


# Функция, генерирующая клавиатуру для выбора пользователем дальнейшего шага
def create_choice_keyboard(*buttons: str, width: int = 2) -> InlineKeyboardMarkup:
    kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
    kb_builder.row(
        *[
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU[button]
                if button in LEXICON_BUTTONS_RU
                else button,
                callback_data=button,
            )
            for button in buttons
        ],
        width=width,
    )
    return kb_builder.as_markup()


# Функция, генерирующая клавиатуру для перехода на сайт
def create_url_keyboard(back: bool = False, width: int = 2) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    buttons = [
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["url_site_button"], url="https://americatrade.by"
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_yandex_button"],
            url="https://yandex.by/maps/org/america_trade/209802914458/reviews/?ll=27.562783%2C53.871084&z",
        ),
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["reviews_google_button"],
            url="https://www.google.com/maps/place/America+Trade/@53.8715902,27.5585072,16z/data=!4m8!3m7!1s0x46dbd10c8f4ca66d:0xc0b4e3cdc9108439!8m2!3d53.8711443!4d27.5627987!9m1!1b1!16s%2Fg%2F11wfs6slw5?entry=ttu&g_ep=EgoyMDI1MDcyMy4wIKXMDSoASAFQAw%3D%3D",
        ),
    ]

    if back:
        buttons.append(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_to:main_menu"],
                callback_data="back_to:main_menu",
            )
        )

    kb.row(*buttons, width=width)
    return kb.as_markup()


# Функция, генерирующая клавиатуру для выбора понравившегося автомобиля
def create_auto_keyboard(
    buttons: list[tuple[str, str]],
    width: int = 1,
    else_car: bool = True,
    search_type: str = "self",
) -> InlineKeyboardMarkup:
    kb_builder = InlineKeyboardBuilder()

    # Основные кнопки (список автомобилей)
    kb_builder.row(
        *[InlineKeyboardButton(text=text, callback_data=cb) for text, cb in buttons],
        width=width,
    )

    # Кнопки действий
    action_buttons = []
    if else_car:
        if search_type == "assisted":
            action_buttons.append(
                InlineKeyboardButton(
                    text=LEXICON_BUTTONS_RU["else_car_button"],
                    callback_data="else_car_button_assisted",
                )
            )
        else:
            action_buttons.append(
                InlineKeyboardButton(
                    text=LEXICON_BUTTONS_RU["else_car_button"],
                    callback_data="else_car_button_self",
                )
            )

    action_buttons.extend(
        [
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["new_search_button"],
                callback_data="new_search_button_assisted"
                if search_type == "assisted"
                else "new_search_button_self",
            ),
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["application_for_selection_button"],
                callback_data="application_for_selection_button",
            ),
        ]
    )

    if search_type != "assisted":
        action_buttons.append(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["subscription_button"],
                callback_data="self_subscription_button",
            )
        )

    action_buttons.append(
        InlineKeyboardButton(
            text=LEXICON_BUTTONS_RU["back_to:main_menu"],
            callback_data="back_to:main_menu",
        )
    )

    kb_builder.row(*action_buttons, width=width)

    return kb_builder.as_markup()


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
        except:
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
            callback_data = f"view_subscription_self_{sub.id}"
            kb_builder.add(
                InlineKeyboardButton(text=button_text, callback_data=callback_data)
            )

    # Добавляем кнопку "Назад" если нужно
    if show_back_button:
        kb_builder.add(
            InlineKeyboardButton(
                text=LEXICON_BUTTONS_RU["back_to:more_info"],
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
