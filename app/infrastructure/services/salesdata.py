"""Copart sales data: CSV download, validation and car search."""

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
from aiohttp.client_exceptions import ContentTypeError

from app.infrastructure.paths import SALESDATA_CSV
from app.infrastructure.services.salesdata_cache import sales_data_cache
from app.lexicon.lexicon_ru import LEXICON_RU_CSV

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


# Парсинг Buy-It-Now Price из CSV (значение всегда приходит строкой)
def parse_buy_now_price(row: dict) -> int:
    try:
        return int(float(row.get("Buy-It-Now Price") or 0))
    except (TypeError, ValueError):
        return 0


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
    if auction_status and parse_buy_now_price(row) <= 0:
        return False
    return True


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

    rows = await sales_data_cache.get_rows()
    filtered = [
        row
        for row in rows
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


# Группы кузовов для случайной подборки в рассылке
BODY_STYLE_GROUPS = {
    "suv": lambda style: "SPORT UTILITY" in style
    or style.startswith("SUV")
    or style.startswith("4DR SPOR"),
    "sedan": lambda style: style.startswith("SEDAN"),
}


# Случайное актуальное авто заданной группы кузова с HD-фото (для рассылки)
async def get_random_car_with_images(
    body_group: str, attempts: int = 10
) -> Optional[Tuple[dict, List[str]]]:
    matcher = BODY_STYLE_GROUPS.get(body_group)
    if matcher is None:
        return None

    rows = await sales_data_cache.get_rows()
    candidates = [
        row
        for row in rows
        if matcher(row.get("Body Style", "").upper())
        and row.get("Sale Date M/D/CY") != "0"
    ]
    if not candidates:
        return None

    sample = random.sample(candidates, k=min(attempts, len(candidates)))
    async with aiohttp.ClientSession() as aio_session:
        for row in sample:
            images = await get_images(row, aio_session)
            if images:
                return row, images
    return None


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


async def download_csv(url: str) -> Path:
    filepath = SALESDATA_CSV

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
                    sales_data_cache.invalidate()

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
