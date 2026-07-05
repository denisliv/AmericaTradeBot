"""Building a Telegram media album from a sales data row."""

from aiogram.types import InputMediaPhoto

from app.infrastructure.services.salesdata import parse_buy_now_price
from app.lexicon.lexicon_ru import LEXICON_CAPTION_RU, LEXICON_EN_RU


# Функция подготовки альбома для отправки пользователю
async def make_media_group(car, first_name, number):
    year = car[0]["Year"]
    brand = car[0]["Make"]
    model = car[0]["Model Detail"]
    color = (
        LEXICON_EN_RU["Color"][car[0]["Color"]]
        if car[0]["Color"] in LEXICON_EN_RU["Color"]
        else car[0]["Color"]
    )
    odometer = car[0]["Odometer"]
    engine = car[0]["Engine"]
    drive = (
        LEXICON_EN_RU["Drive"][car[0]["Drive"]]
        if car[0]["Drive"] in LEXICON_EN_RU["Drive"]
        else car[0]["Drive"]
    )
    transmission = (
        LEXICON_EN_RU["Transmission"][car[0]["Transmission"]]
        if car[0]["Transmission"] in LEXICON_EN_RU["Transmission"]
        else car[0]["Transmission"]
    )
    sale_date = car[0]["Sale Date M/D/CY"]

    price_value = parse_buy_now_price(car[0])
    buy_now_price = price_value if price_value > 0 else None

    caption = LEXICON_CAPTION_RU["caption_text"](
        first_name,
        number,
        year,
        brand,
        model,
        color,
        odometer,
        engine,
        drive,
        transmission,
        sale_date,
        buy_now_price,
    )
    media_group = [InputMediaPhoto(media=car[1][0], caption=caption)]
    media_group.extend([InputMediaPhoto(media=file_id) for file_id in car[1][1:]])
    return media_group
