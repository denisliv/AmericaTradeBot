"""Car card content: the client reads this text before leaving a request.

Covers the customer's feedback on the card: the fixed BUY NOW price must be
named as such, the damage type must be visible, the name must not be cut, and
fields the auction left empty must not show up as dangling labels.
"""

import csv

import pytest

from app.infrastructure.paths import SALESDATA_CSV
from app.infrastructure.services.car_media import (
    LOT_CALLBACK_PREFIX,
    build_car_title,
    make_lot_callback,
    parse_lot_callback,
    translate,
)
from app.lexicon.lexicon_ru import LEXICON_CAPTION_RU

CAPTION = LEXICON_CAPTION_RU["caption_text"]


def _full_row(**overrides) -> dict:
    row = {
        "Make": "VOLKSWAGEN",
        "Model Detail": "TAOS",
        "Trim": "SE",
        "Year": "2022",
        "Color": "BLUE",
        "Engine": "1.5L 4",
        "Transmission": "AUTOMATIC",
        "Drive": "ALL WHEEL DRIVE",
        "Odometer": "10000",
        "Damage Description": "FRONT END",
        "Sale Date M/D/CY": "20260810",
        "Buy-It-Now Price": "12500",
    }
    row.update(overrides)
    return row


def test_fixed_price_is_named_fixed_price():
    # Клиент должен понимать, что это цена "купить сейчас", а не оценка
    caption = CAPTION("Антон", 1, "VOLKSWAGEN TAOS", buy_now_price=12500)

    assert "💵 Фиксированная цена: 12 500$" in caption
    assert "ориентир" not in caption.lower()


def test_lot_without_fixed_price_shows_no_price_line():
    caption = CAPTION("Антон", 1, "VOLKSWAGEN TAOS", buy_now_price=None)

    assert "Фиксированная цена" not in caption


def test_damage_type_is_shown():
    caption = CAPTION("Антон", 1, "VOLKSWAGEN TAOS", damage="Передняя часть")

    assert "✅ Вид повреждения: Передняя часть" in caption


def test_empty_fields_are_skipped_instead_of_dangling_labels():
    # У 6% лотов Copart не заполняет двигатель и привод: пустая строка
    # "✅ Привод:" в карточке выглядит как поломка бота
    caption = CAPTION(
        "Антон",
        1,
        "CHEVROLET EQUINOX",
        year="2022",
        engine="",
        drive="",
        odometer="",
        damage="",
    )

    assert "✅ Объем двигателя" not in caption
    assert "✅ Привод" not in caption
    assert "✅ Пробег" not in caption
    assert "✅ Вид повреждения" not in caption
    assert "✅ Модельный год: 2022" in caption


def test_odometer_is_converted_to_kilometres():
    caption = CAPTION("Антон", 1, "VOLKSWAGEN TAOS", odometer="10000")

    assert "✅ Пробег: 16093 км." in caption


def test_unscheduled_auction_date():
    assert "⌛ Дата аукциона: Не назначена" in CAPTION("Антон", 1, "X", sale_date="0")
    assert "⌛ Дата аукциона: 2026-08-10" in CAPTION(
        "Антон", 1, "X", sale_date="20260810"
    )


def test_title_keeps_trim_because_copart_hides_the_real_model_there():
    # Mini Countryman лежит в Copart как модель COOPER, а COUNTRYMAN - в Trim
    row = _full_row(Make="MINI", **{"Model Detail": "COOPER", "Trim": "COUNTRYMAN S"})

    assert build_car_title(row) == "MINI COOPER COUNTRYMAN S"


def test_title_does_not_duplicate_trim_already_in_the_model():
    row = _full_row(Make="TOYOTA", **{"Model Detail": "CAMRY LE", "Trim": "LE"})

    assert build_car_title(row) == "TOYOTA CAMRY LE"


def test_title_without_trim():
    row = _full_row(Make="BMW", **{"Model Detail": "X5", "Trim": ""})

    assert build_car_title(row) == "BMW X5"


def test_lot_callback_survives_hyphen_in_make():
    # Разбор по "-" разрывал MERCEDES-BENZ и показывал "MERCEDES BENZ GLK"
    row = _full_row(
        Make="MERCEDES-BENZ", **{"Model Detail": "GLK", "Trim": "", "Lot number": "123"}
    )

    lot, title = parse_lot_callback(make_lot_callback(row))

    assert lot == "123"
    assert title == "MERCEDES-BENZ GLK"


def test_lot_callback_understands_old_mailings():
    # В уже разосланных сообщениях остался прежний формат с "-"
    lot, title = parse_lot_callback(f"{LOT_CALLBACK_PREFIX}555-BMW-X5")

    assert lot == "555"
    assert title == "BMW X5"


def test_lot_callback_fits_telegram_limit():
    row = _full_row(
        Make="LAND ROVER",
        **{
            "Model Detail": "RANGE ROVER VELAR R-DYNAMIC",
            "Trim": "SE LONG WHEELBASE",
            "Lot number": "91763525",
        },
    )

    assert len(make_lot_callback(row).encode("utf-8")) <= 64


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ALL WHEEL DRIVE", "Полный"),
        ("All wheel drive", "Полный"),
        ("FRONT WHEEL DRIVE", "Передний"),
        ("Front-wheel Drive", "Передний"),
        ("REAR WHEEL DRIVE", "Задний"),
        ("4X4 W/REAR WHEEL DRV", "Полный"),
    ],
)
def test_drive_is_translated_regardless_of_copart_spelling(raw, expected):
    # Copart пишет привод в разных регистрах; по точному ключу совпадало ~6% строк
    assert translate("Drive", raw) == expected


def test_unknown_values_are_hidden_not_shown_as_unknown():
    assert translate("Drive", "UNKNOWN") == ""
    assert translate("Transmission", "UNKNOWN") == ""


def test_unmapped_value_falls_back_to_the_original():
    assert translate("Drive", "12X4") == "12X4"


@pytest.mark.skipif(not SALESDATA_CSV.is_file(), reason="salesdata.csv is runtime data")
def test_every_drive_and_transmission_value_in_real_csv_is_translated():
    """Guards against Copart introducing a new spelling we would show in English."""
    with SALESDATA_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    untranslated = set()
    for row in rows:
        for field in ("Drive", "Transmission"):
            value = (row.get(field) or "").strip()
            if value and translate(field, value) == value:
                untranslated.add((field, value))

    # Мусорные значения самого Copart, не относящиеся к легковым авто
    allowed = {
        ("Drive", "4X2"),
        ("Drive", "12X4"),
        ("Drive", "8X4"),
        ("Drive", "AUTOMATIC"),
        ("Transmission", "GAS"),
    }
    assert untranslated <= allowed, untranslated
