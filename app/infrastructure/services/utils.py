import asyncio
import csv
import logging
import os
import random
from pathlib import Path
from typing import List, Optional, Tuple

import aiofiles
import aiohttp
import async_timeout
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiohttp.client_exceptions import ContentTypeError

from app.lexicon.lexicon_ru import LEXICON_CAPTION_RU, LEXICON_EN_RU, LEXICON_RU_CSV

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_SALESDATA_COLUMNS = (
    "Make",
    "Model Group",
    "Model Detail",
    "Year",
    "Odometer",
    "Sale Date M/D/CY",
    "Buy-It-Now Price",
    "Lot number",
    "Color",
    "Engine",
    "Drive",
    "Transmission",
    "Fuel Type",
    "Image URL",
)


# Универсальная функция запроса JSON
async def fetch_json(
    session: aiohttp.ClientSession, url: str, timeout: int = 5
) -> Optional[dict]:
    try:
        async with async_timeout.timeout(timeout):
            async with session.get(url) as response:
                return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ContentTypeError) as e:
        logger.warning(f"Ошибка при загрузке JSON {url}: {e}")
        return None


# Получение HD-изображений для авто
async def get_images(
    car: dict, session: aiohttp.ClientSession, max_images: int = 9
) -> List[str]:
    url = car.get("Image URL")
    if not url:
        return []

    response = await fetch_json(session, url)
    if not response:
        return []

    urls = []
    try:
        for img_data in response.get("lotImages", []):
            for link in img_data.get("link", []):
                if link.get("isHdImage"):
                    urls.append(link["url"].strip())
    except KeyError:
        logger.warning(f"Некорректный формат изображений: {url}")

    return urls[:max_images]


# Базовый фильтр по марке/модели/году
def filter_by_make_and_model(row: dict, brand: str, model: str, year: tuple) -> bool:
    try:
        model_matches = model == "ALL MODELS" or row["Model Group"] == model
        return (
            row["Make"] == brand
            and model_matches
            and year[0] <= int(row["Year"]) <= year[1]
            and row["Sale Date M/D/CY"] != "0"
        )
    except (ValueError, KeyError):
        return False


# Универсальный фильтр с доп. параметрами
def match_car(
    row: dict,
    brand: str,
    model: str,
    year: tuple,
    odometer: Optional[tuple] = None,
    auction_status: Optional[str] = None,
) -> bool:
    if not filter_by_make_and_model(row, brand, model, year):
        return False
    if odometer:
        try:
            odo_val = float(row["Odometer"])
            if not (odometer[0] <= odo_val <= odometer[1]):
                return False
        except ValueError:
            return False
    if auction_status and row.get("Buy-It-Now Price") == 0:
        return False
    return True


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
    )
    media_group = [InputMediaPhoto(media=car[1][0], caption=caption)]
    media_group.extend([InputMediaPhoto(media=file_id) for file_id in car[1][1:]])
    return media_group


# Универсальная отправка media_group с обработкой ошибок
async def safe_send_media_group(
    callback: CallbackQuery, media_group, number, car
) -> Optional[Tuple[str, str]]:
    try:
        await callback.message.answer_media_group(media=media_group)
        return (
            f"✅ Авто № {number}",
            f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await callback.message.answer_media_group(media=media_group)
        return (
            f"✅ Авто № {number}",
            f"Лот №: {car[0]['Lot number']}-{car[0]['Make']}-{car[0]['Model Detail']}",
        )
    except TelegramBadRequest as e:
        logger.warning(f"Ошибка TelegramBadRequest: {e}")
        return None


# Получение данных по заявке пользователя
async def get_data(user_dict: dict, count: int = 6) -> List[Tuple[dict, List[str]]]:
    brand = user_dict["brand"]
    model = user_dict["model"]
    year = LEXICON_RU_CSV[user_dict["year"]]
    odometer = (
        LEXICON_RU_CSV.get(user_dict["odometer"]) if user_dict["odometer"] else None
    )
    auction_status = (
        LEXICON_RU_CSV.get(user_dict["auction_status"])
        if user_dict["auction_status"]
        else None
    )

    # Читаем CSV асинхронно
    async with aiofiles.open(
        "data/salesdata.csv", mode="r", encoding="utf-8"
    ) as csvfile:
        csv_lines = await csvfile.readlines()

    reader = csv.DictReader(csv_lines)
    filtered = [
        row
        for row in reader
        if match_car(row, brand, model, year, odometer, auction_status)
    ]

    if not filtered:
        return []

    random.shuffle(filtered)
    selected = filtered[:count]

    # Параллельная загрузка картинок
    async with aiohttp.ClientSession() as aio_session:
        images_results = await asyncio.gather(
            *(get_images(row, aio_session) for row in selected)
        )

    # Возвращаем только те, у которых есть картинки
    cars = [(row, imgs) for row, imgs in zip(selected, images_results) if imgs]
    return cars[:count]


# Функция загрузки данных в csv
def _validate_sales_csv_bytes(content: bytes) -> None:
    if not content.strip():
        raise ValueError("Downloaded CSV is empty")

    text = content.decode("utf-8-sig")
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("Downloaded CSV is empty") from exc

    columns = {column.strip().strip('"') for column in header}
    missing = [column for column in REQUIRED_SALESDATA_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Downloaded CSV missing required columns: {missing}")

    if next(reader, None) is None:
        raise ValueError("Downloaded CSV has no data rows")


async def _write_sales_csv_atomically(filepath: str | Path, content: bytes) -> None:
    target = Path(filepath)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.tmp")
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(content)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


async def download_csv(url: str) -> str:
    filepath = "data/salesdata.csv"

    try:
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(30):  # Таймаут 30 секунд
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(
                            f"Ошибка HTTP {response.status} при загрузке {url}"
                        )
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                        )

                    chunks = []
                    total_bytes = 0
                    while chunk := await response.content.read(1024):
                        chunks.append(chunk)
                        total_bytes += len(chunk)
                    content = b"".join(chunks)
                    _validate_sales_csv_bytes(content)
                    await _write_sales_csv_atomically(filepath, content)

                    logger.info(
                        f"Файл успешно загружен: {filepath} ({total_bytes} байт)"
                    )
                    return filepath

    except asyncio.TimeoutError:
        logger.error(f"Таймаут при загрузке файла с {url}")
        raise
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при загрузке {url}: {e}")
        raise
    except OSError as e:
        logger.error(f"Ошибка записи файла {filepath}: {e}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке {url}: {e}")
        raise
