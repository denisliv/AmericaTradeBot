"""Локальная галерея примеров для assisted selection.

Каталог собирается скриптом ``scripts/import_gallery.py`` из выгрузки Google
Drive: ``<кузов>/<бюджет>/<приоритет>_<марка_модель>/*.jpg`` плюс манифест
``gallery.json`` с приоритетом и полным названием каждого авто::

    {"suv": {"0-12k": [{"priority": 1,
                        "title": "2021 Chevrolet Equinox",
                        "folder": "001_2021_chevrolet_equinox",
                        "photos": 8}]}}

Порядок выдачи задаёт заказчик нумерацией папок в Drive, поэтому подборка идёт
строго по приоритету, а не случайно.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, Optional

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from app.infrastructure.paths import ASSISTED_GALLERY_DIR
from app.lexicon.lexicon_ru import LEXICON_ASSISTED_GALLERY_RU

logger = logging.getLogger(__name__)

ASSISTED_GALLERY_ROOT: Final[Path] = ASSISTED_GALLERY_DIR
MANIFEST_NAME: Final[str] = "gallery.json"

BODY_DIR: Final[dict[str, str]] = {
    "🚙 Кроссовер/SUV": "suv",
    "🚗 Седан/Хэтчбек": "sedan",
    "⚡Электромобиль": "electric",
}

# Вариант "тип не выбран": подборка собирается по всем кузовам сразу
ANY_BODY_KEY: Final[str] = "Еще не решил/разные варианты"

BUDGET_DIR: Final[dict[str, str]] = {
    "до 12 000$": "0-12k",
    "12 000$ - 15 000$": "12k-15k",
    "15 000$ - 20 000$": "15k-20k",
    "20 000$ - 30 000$": "20k-30k",
    "30 000$ - 50 000$": "30k-50k",
    "50 000$ +": "50k-plus",
}

# Сколько фото уходит в одном альбоме карточки
MAX_PHOTOS: Final[int] = 5
# Размер страницы подборки
PAGE_SIZE: Final[int] = 3


@dataclass(frozen=True)
class AssistedGalleryPick:
    car_folder: str
    display_title: str
    image_paths: list[Path]
    body_style_key: str
    budget_key: str


@lru_cache(maxsize=1)
def _load_manifest(root: Path) -> dict:
    """Read ``gallery.json``; an absent manifest means an empty gallery."""
    path = root / MANIFEST_NAME
    if not path.is_file():
        logger.warning("Gallery manifest not found: %s", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _ordered_cars(root: Path, body_key: str, budget_slug: str) -> list[dict]:
    manifest = _load_manifest(root)
    cars = manifest.get(BODY_DIR[body_key], {}).get(budget_slug, [])
    return sorted(cars, key=lambda car: car["priority"])


def _interleave(
    groups: list[list[tuple[str, dict]]],
) -> list[tuple[str, dict]]:
    """Merge per-body lists so that the types alternate instead of going in blocks."""
    merged: list[tuple[str, dict]] = []
    for position in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if position < len(group):
                merged.append(group[position])
    return merged


def get_gallery_page(
    body_style_key: str,
    budget_key: str,
    *,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    root: Optional[Path] = None,
) -> tuple[list[AssistedGalleryPick], int]:
    """Return one page of the selection, ordered by the customer's priority.

    Args:
        body_style_key: Body style button text.
        budget_key: Budget button text.
        offset: Position in the category the previous page stopped at.
        limit: Page size.
        root: Gallery root, for tests.

    Returns:
        Cars of the page and the offset the next page must start from. The
        offset counts scanned positions, not delivered cards: a car skipped
        because its folder went missing must not shift the next page back onto
        an already shown car.
    """
    base = root or ASSISTED_GALLERY_ROOT
    budget_slug = BUDGET_DIR.get(budget_key)
    if not budget_slug:
        return [], offset

    if body_style_key == ANY_BODY_KEY:
        # Типы кузова чередуются, иначе первая страница была бы из одних кроссоверов
        ordered = _interleave(
            [
                [(key, car) for car in _ordered_cars(base, key, budget_slug)]
                for key in BODY_DIR
            ]
        )
    elif body_style_key in BODY_DIR:
        ordered = [
            (body_style_key, car)
            for car in _ordered_cars(base, body_style_key, budget_slug)
        ]
    else:
        return [], offset

    picks: list[AssistedGalleryPick] = []
    position = offset
    while position < len(ordered) and len(picks) < limit:
        body_key, car = ordered[position]
        position += 1
        car_dir = base / BODY_DIR[body_key] / budget_slug / car["folder"]
        if not car_dir.is_dir():
            # Манифест разошелся с файлами (например, неполный перенос на сервер)
            logger.warning("Gallery folder is missing: %s", car_dir)
            continue
        images = sorted(
            (p for p in car_dir.iterdir() if p.is_file()), key=lambda p: p.name.lower()
        )
        if not images:
            logger.warning("Gallery folder without images: %s", car_dir)
            continue
        picks.append(
            AssistedGalleryPick(
                car_folder=car["folder"],
                display_title=car["title"],
                image_paths=images[:MAX_PHOTOS],
                body_style_key=body_key,
                budget_key=budget_key,
            )
        )
    return picks, position


def parse_ag_lead_callback(
    data: str, *, root: Optional[Path] = None
) -> Optional[tuple[str, str, str, str]]:
    """Возвращает (car_folder, body_key_ru, budget_key_ru, display_title) или None."""
    parts = data.split("|", 3)
    if len(parts) != 4 or parts[0] != "ag_lead":
        return None
    _, car_folder, body_slug, budget_slug = parts
    body_ru = next((k for k, v in BODY_DIR.items() if v == body_slug), body_slug)
    budget_ru = next(
        (k for k, v in BUDGET_DIR.items() if v == budget_slug), budget_slug
    )
    title = _title_by_folder(
        root or ASSISTED_GALLERY_ROOT, body_slug, budget_slug, car_folder
    )
    return car_folder, body_ru, budget_ru, title


def _title_by_folder(
    root: Path, body_slug: str, budget_slug: str, car_folder: str
) -> str:
    """Look the display title up in the manifest; fall back to the folder name."""
    cars = _load_manifest(root).get(body_slug, {}).get(budget_slug, [])
    for car in cars:
        if car["folder"] == car_folder:
            return car["title"]
    return car_folder.replace("_", " ").strip()


def make_ag_lead_callback(pick: AssistedGalleryPick) -> str:
    # callback_data Telegram ≤ 64 байт
    body_slug = BODY_DIR[pick.body_style_key]
    budget_slug = BUDGET_DIR[pick.budget_key]
    raw = f"ag_lead|{pick.car_folder}|{body_slug}|{budget_slug}"
    encoded = raw.encode("utf-8")
    if len(encoded) <= 64:
        return raw
    # Укорачиваем только имя папки авто
    max_car = 64 - len(f"ag_lead||{body_slug}|{budget_slug}".encode("utf-8"))
    if max_car < 1:
        return "ag_lead|x|sedan|0-12k"[:64]
    car = pick.car_folder.encode("utf-8")[:max_car].decode("utf-8", errors="ignore")
    return f"ag_lead|{car}|{body_slug}|{budget_slug}"


def build_top_media_group(
    first_name: str,
    pick: AssistedGalleryPick,
) -> list[InputMediaPhoto]:
    """Альбом одного авто из ТОП-подборки: подпись на первом фото."""
    caption = LEXICON_ASSISTED_GALLERY_RU["caption"](
        first_name,
        pick.display_title,
        pick.body_style_key,
        pick.budget_key,
    )
    media: list[InputMediaPhoto] = []
    for i, path in enumerate(pick.image_paths):
        cap = caption if i == 0 else None
        media.append(InputMediaPhoto(media=FSInputFile(path), caption=cap))
    return media


async def safe_send_assisted_gallery_media_group(
    callback: CallbackQuery,
    media_group: list[InputMediaPhoto],
) -> bool:
    """Send one album, retrying only errors that can succeed on a second try.

    ``TelegramBadRequest`` means Telegram rejected the content itself (broken or
    unsupported file, oversized image): a retry would fail the same way, so the
    card is skipped and the reason is logged.

    Returns:
        True if the album was delivered.
    """
    for attempt in range(2):
        try:
            await callback.message.answer_media_group(media=media_group)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramBadRequest as e:
            logger.warning("Gallery album rejected by Telegram: %s", e)
            return False
        except (TelegramNetworkError, TelegramServerError) as e:
            logger.warning("Gallery album not sent (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(1)
    return False
