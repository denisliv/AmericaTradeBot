"""Copart sales data: CSV download, validation and car search.

The snapshot is kept in PostgreSQL, not in the process. Holding it parsed in
memory cost 730 MB of resident size for an 84 MB file, and buffering the
download in one piece added another 370 MB peak every hour; both are now
streamed, so this module never holds more than one batch of rows.
"""

import asyncio
import csv
import logging
import os
from itertools import islice
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, List, Optional, Sequence, Tuple

import aiohttp
import async_timeout
from aiohttp.client_exceptions import ContentTypeError
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.infrastructure.database.sales_lots import (
    CSV_COLUMNS,
    count_sales_lots,
    random_top_cars,
    replace_sales_lots,
    search_cars,
)
from app.infrastructure.paths import SALESDATA_CSV
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
    "Damage Description",
    "Trim",
)

# Сколько ждём весь файл: фид около 90 МБ, отдаётся минуты за полторы.
DOWNLOAD_TIMEOUT_SECONDS = 30
# Размер куска при записи на диск. Прежний 1 КБ давал 88 тысяч итераций.
DOWNLOAD_CHUNK_BYTES = 64 * 1024
# Сколько строк разбирается за один заход в рабочем потоке.
COPY_BATCH_ROWS = 5000
# Кодировка фида: у файла бывает BOM.
CSV_ENCODING = "utf-8-sig"

HTTP_OK = 200


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


# Парсинг Buy-It-Now Price из CSV (значение всегда приходит строкой)
def parse_buy_now_price(row: dict) -> int:
    try:
        return int(float(row.get("Buy-It-Now Price") or 0))
    except (TypeError, ValueError):
        return 0


def _parse_year(row: dict) -> Optional[int]:
    """Parse the model year, or None when the feed did not write a usable one.

    A row without a readable year matched no search before this lived in SQL
    either: every search compares the year against a range.
    """
    try:
        return int(row["Year"])
    except (KeyError, TypeError, ValueError):
        return None


def _parse_odometer(row: dict) -> Optional[float]:
    """Parse the mileage, or None when the feed did not write a usable one."""
    try:
        return float(row["Odometer"])
    except (KeyError, TypeError, ValueError):
        return None


def to_snapshot_record(row: dict) -> tuple:
    """Turn one CSV row into the tuple the snapshot table is loaded with.

    The text values go in verbatim — the car card prints year and mileage as
    the feed wrote them. The parsed values that follow exist only so the
    filtering can happen in SQL.

    Args:
        row: One row as csv.DictReader produced it.

    Returns:
        Values in COPY_COLUMNS order.
    """
    text = tuple(row.get(name) for name in CSV_COLUMNS)
    return text + (_parse_year(row), _parse_odometer(row), parse_buy_now_price(row))


# Сколько лотов проверяем на наличие фото за один заход
IMAGE_LOOKUP_BATCH = 12
# Потолок проверок на один поиск: у Copart фото есть примерно у каждого пятого
# лота, поэтому кандидатов приходится перебирать, но не бесконечно
MAX_IMAGE_LOOKUPS = 60


async def collect_cars_with_images(
    candidates: List[dict], count: int
) -> List[Tuple[dict, List[str]]]:
    """Collect up to ``count`` lots that actually have photos.

    Copart serves images for a minority of lots, so checking only the first
    ``count`` candidates regularly yielded nothing and the user saw "нет
    вариантов" on a search that had thousands of matches. Candidates are
    therefore topped up batch by batch until enough lots with photos are found.

    Args:
        candidates: Matching rows in the order they should be offered.
        count: How many cars the caller wants.

    Returns:
        Pairs of row and its image URLs, at most ``count`` items.
    """
    cars: List[Tuple[dict, List[str]]] = []
    async with aiohttp.ClientSession() as aio_session:
        for start in range(
            0, min(len(candidates), MAX_IMAGE_LOOKUPS), IMAGE_LOOKUP_BATCH
        ):
            batch = candidates[start : start + IMAGE_LOOKUP_BATCH]
            images_results = await asyncio.gather(
                *(get_images(row, aio_session) for row in batch)
            )
            cars.extend((row, imgs) for row, imgs in zip(batch, images_results) if imgs)
            if len(cars) >= count:
                break

    if not cars:
        logger.warning(
            "Нет лотов с фото: проверено %d из %d подходящих",
            min(len(candidates), MAX_IMAGE_LOOKUPS),
            len(candidates),
        )
    return cars[:count]


# Получение данных по заявке пользователя
async def get_data(
    user_dict: dict, conn: AsyncConnection, count: int = 6
) -> List[Tuple[dict, List[str]]]:
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

    candidates, matched = await search_cars(
        conn,
        brand=brand,
        model=model,
        year=year,
        odometer=odometer,
        buy_now_only=bool(auction_status),
        limit=MAX_IMAGE_LOOKUPS,
    )
    if not candidates:
        return []

    logger.info("Подбор: подошло %d лотов, проверяем %d", matched, len(candidates))
    return await collect_cars_with_images(candidates, count)


# Критерии ТОП-подборки в рассылке: свежие авто с фиксированной ценой BUY NOW
TOP_CARS_MIN_YEAR = 2022


# Случайное актуальное авто заданной группы кузова с HD-фото (для рассылки)
async def get_random_car_with_images(
    conn: AsyncConnection, body_group: str, attempts: int = 10
) -> Optional[Tuple[dict, List[str]]]:
    sample = await random_top_cars(
        conn,
        body_group=body_group,
        min_year=TOP_CARS_MIN_YEAR,
        limit=attempts,
    )
    if not sample:
        return None

    async with aiohttp.ClientSession() as aio_session:
        for row in sample:
            images = await get_images(row, aio_session)
            if images:
                return row, images
    return None


# Функция загрузки данных в csv
def _validate_sales_csv_file(filepath: str | Path) -> None:
    """Check the downloaded file before it replaces the snapshot.

    Reads the header and one data row instead of the whole file: a truncated
    or renamed feed shows up in the first two lines, and decoding 84 MB just to
    look at them was the other half of the hourly memory peak.

    Args:
        filepath: Freshly downloaded CSV.

    Raises:
        ValueError: When the file is empty, carries no data rows, or lost a
            column the bot reads.
    """
    with Path(filepath).open("r", encoding=CSV_ENCODING, newline="") as csvfile:
        reader = csv.reader(csvfile)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("Downloaded CSV is empty") from exc

        columns = {column.strip().strip('"') for column in header}
        missing = [
            column for column in REQUIRED_SALESDATA_COLUMNS if column not in columns
        ]
        if missing:
            raise ValueError(f"Downloaded CSV missing required columns: {missing}")

        if next(reader, None) is None:
            raise ValueError("Downloaded CSV has no data rows")


def _read_snapshot_batch(reader: Iterator[dict], size: int) -> list[tuple]:
    """Parse the next ``size`` rows. Runs in a worker thread."""
    return [to_snapshot_record(row) for row in islice(reader, size)]


async def _iter_snapshot_batches(
    reader: Iterator[dict],
) -> AsyncIterator[Sequence[Sequence[Any]]]:
    """Yield batches of records, parsing each batch off the event loop."""
    while True:
        batch = await asyncio.to_thread(_read_snapshot_batch, reader, COPY_BATCH_ROWS)
        if not batch:
            return
        yield batch


async def load_snapshot(db_pool: AsyncConnectionPool, filepath: str | Path) -> int:
    """Replace the snapshot in PostgreSQL with the contents of this CSV.

    Args:
        db_pool: Pool to take the loading connection from.
        filepath: Validated CSV to load.

    Returns:
        How many rows the snapshot now holds.
    """
    with Path(filepath).open("r", encoding=CSV_ENCODING, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        async with db_pool.connection() as conn:
            loaded = await replace_sales_lots(conn, _iter_snapshot_batches(reader))

    logger.info("Снимок Copart загружен в базу: %d строк", loaded)
    return loaded


async def ensure_snapshot_loaded(db_pool: AsyncConnectionPool) -> None:
    """Load the CSV already on disk when the snapshot table is empty.

    The download job runs on an interval, so after a restart the table would
    otherwise stay empty until the first tick an hour later and every search
    would answer "нет вариантов". The file outlives the process, so the
    snapshot is rebuilt from it instead of waiting for Copart.
    """
    async with db_pool.connection() as conn:
        if await count_sales_lots(conn) > 0:
            return

    if not SALESDATA_CSV.exists():
        logger.warning(
            "Снимок Copart пуст, а файла %s нет: подбор заработает после загрузки фида",
            SALESDATA_CSV,
        )
        return

    logger.info("Снимок Copart пуст, восстанавливаем из %s", SALESDATA_CSV)
    await load_snapshot(db_pool, SALESDATA_CSV)


async def download_csv(url: str, db_pool: AsyncConnectionPool) -> Path:
    """Download the inventory feed and make it the current snapshot.

    The body is streamed to a temporary file and only then validated and
    loaded: the feed is about 90 MB, and holding it in memory as chunks, as one
    blob, as a decoded string and as a list of lines cost 370 MB every hour.

    Args:
        url: Feed URL with the partner access key.
        db_pool: Pool the snapshot is loaded through.

    Returns:
        Path of the stored CSV.

    Raises:
        aiohttp.ClientResponseError: When the feed answers with a non-200 code.
        ValueError: When the downloaded file does not look like the feed.
    """
    filepath = SALESDATA_CSV
    tmp_path = filepath.with_name(f"{filepath.name}.tmp")
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with aiohttp.ClientSession() as session:
            async with async_timeout.timeout(DOWNLOAD_TIMEOUT_SECONDS):
                async with session.get(url) as response:
                    if response.status != HTTP_OK:
                        logger.error("Ошибка HTTP %s при загрузке фида", response.status)
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                        )

                    total_bytes = await _stream_to_file(response, tmp_path)

        await asyncio.to_thread(_validate_sales_csv_file, tmp_path)
        os.replace(tmp_path, filepath)
        logger.info(f"Файл успешно загружен: {filepath} ({total_bytes} байт)")

        await load_snapshot(db_pool, filepath)
        return filepath

    # Адрес фида в лог не пишется ни в одной ветке: в нём партнёрский authKey,
    # а stdout контейнера собирается и уезжает дальше. По той же причине в лог
    # идёт класс исключения, а не его текст: ClientResponseError печатает
    # полный адрес запроса вместе с ключом.
    except asyncio.TimeoutError:
        logger.error("Таймаут при загрузке фида")
        raise
    except aiohttp.ClientError as e:
        logger.error("Ошибка сети при загрузке фида: %s", type(e).__name__)
        raise
    except OSError as e:
        logger.error(f"Ошибка записи файла {filepath}: {e}")
        raise
    except Exception as e:
        logger.error("Неожиданная ошибка при загрузке фида: %s", type(e).__name__)
        raise
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


async def _stream_to_file(response: aiohttp.ClientResponse, tmp_path: Path) -> int:
    """Write the response body to a file chunk by chunk.

    Args:
        response: Open response positioned at the start of the body.
        tmp_path: File to write; replaced if it exists.

    Returns:
        How many bytes were written.
    """
    total_bytes = 0
    with tmp_path.open("wb") as handle:
        async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_BYTES):
            await asyncio.to_thread(handle.write, chunk)
            total_bytes += len(chunk)
    return total_bytes
