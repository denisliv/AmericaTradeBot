"""Building a Telegram media album from a sales data row."""

import re

from aiogram.types import InputMediaPhoto

from app.infrastructure.services.salesdata import parse_buy_now_price
from app.lexicon.lexicon_ru import LEXICON_CAPTION_RU, LEXICON_EN_RU


def _normalize(value: str) -> str:
    """Bring a CSV value to the form used as a translation key."""
    return re.sub(r"[\s-]+", " ", value).strip().upper()


# Copart пишет одно значение в разных регистрах и с разными дефисами
# ("ALL WHEEL DRIVE", "All wheel drive"), поэтому словари переводов
# индексируются нормализованным ключом.
_TRANSLATIONS: dict[str, dict[str, str]] = {
    field: {_normalize(key): value for key, value in mapping.items()}
    for field, mapping in LEXICON_EN_RU.items()
}


def translate(field: str, value: str) -> str:
    """Translate a CSV value to Russian.

    Args:
        field: Key of the dictionary in ``LEXICON_EN_RU``.
        value: Raw value from the sales data row.

    Returns:
        Russian text, or the original value when it is not in the dictionary.
        An empty string means the field must not be shown.
    """
    normalized = _normalize(value)
    if not normalized:
        return ""
    return _TRANSLATIONS[field].get(normalized, value.strip())


def build_car_title(row: dict) -> str:
    """Build the full car name: make, model and trim.

    ``Model Detail`` alone is not enough: Copart stores a Mini Countryman as
    model ``COOPER`` and keeps ``COUNTRYMAN S`` in ``Trim``.

    Args:
        row: Sales data row.

    Returns:
        Car name, e.g. ``"MINI COOPER COUNTRYMAN S"``.
    """
    make = (row.get("Make") or "").strip()
    model = (row.get("Model Detail") or "").strip()
    trim = (row.get("Trim") or "").strip()
    parts = [part for part in (make, model) if part]
    # Trim иногда повторяет хвост модели ("CAMRY LE" + "LE") - тогда не дублируем
    trim_norm = _normalize(trim)
    if trim_norm and not re.search(
        rf"(?:^| ){re.escape(trim_norm)}(?: |$)", _normalize(model)
    ):
        parts.append(trim)
    return " ".join(parts)


LOT_CALLBACK_PREFIX = "Лот №: "
_LOT_SEPARATOR = "|"
# Ограничение Telegram на callback_data
_MAX_CALLBACK_BYTES = 64


def make_lot_callback(row: dict) -> str:
    """Build ``callback_data`` for the "detailed calculation" button of a lot.

    The car name is cut only if the callback would not fit into Telegram's
    64-byte limit; the caption of the card always keeps the full name.

    Args:
        row: Sales data row.

    Returns:
        Callback payload ``"Лот №: <lot>|<title>"``.
    """
    lot = (row.get("Lot number") or "").strip()
    head = f"{LOT_CALLBACK_PREFIX}{lot}{_LOT_SEPARATOR}"
    budget = _MAX_CALLBACK_BYTES - len(head.encode("utf-8"))
    title = build_car_title(row)
    if len(title.encode("utf-8")) > budget:
        title = title.encode("utf-8")[:budget].decode("utf-8", errors="ignore").strip()
    return f"{head}{title}"


def parse_lot_callback(data: str) -> tuple[str, str]:
    """Split a lot callback into the lot number and the car name.

    Older mailings still carry the previous ``"-"`` separated payload, which
    broke on makes with a hyphen (``MERCEDES-BENZ``); such callbacks are parsed
    by the first separator only.

    Args:
        data: Callback payload starting with ``"Лот №: "``.

    Returns:
        Tuple of lot number and car name.
    """
    body = data[len(LOT_CALLBACK_PREFIX) :]
    separator = _LOT_SEPARATOR if _LOT_SEPARATOR in body else "-"
    lot, _, title = body.partition(separator)
    return lot.strip(), title.replace("-", " ").strip() if separator == "-" else title


# Функция подготовки альбома для отправки пользователю
async def make_media_group(car, first_name, number):
    row = car[0]
    caption = LEXICON_CAPTION_RU["caption_text"](
        first_name,
        number,
        build_car_title(row),
        year=row.get("Year", ""),
        color=translate("Color", row.get("Color", "")),
        engine=row.get("Engine", ""),
        transmission=translate("Transmission", row.get("Transmission", "")),
        drive=translate("Drive", row.get("Drive", "")),
        odometer=row.get("Odometer", ""),
        damage=translate("Damage", row.get("Damage Description", "")),
        sale_date=row.get("Sale Date M/D/CY", ""),
        buy_now_price=parse_buy_now_price(row) or None,
    )
    media_group = [InputMediaPhoto(media=car[1][0], caption=caption)]
    media_group.extend([InputMediaPhoto(media=file_id) for file_id in car[1][1:]])
    return media_group
