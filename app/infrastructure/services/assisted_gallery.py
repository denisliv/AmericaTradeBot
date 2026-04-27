"""Локальная галерея примеров для assisted selection (кузов → бюджет → папка авто → фото).

Структура каталога (корень по умолчанию ``data/assisted_gallery``)::

    assisted_gallery/
      sedan/
        0-12k/
          toyota_camry/
            01.jpg
            ...
        12k-15k/
        15k-20k/
        20k-30k/
        30k-50k/
        50k-plus/
      suv/
        ...
      electric/
        ...

Имена папок кузова и бюджета — латиница, как в константах ниже.
Папки автомобилей — латиница и подчёркивания (например ``honda_accord``); подпись для
пользователя строится из имени папки автоматически.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from app.lexicon.lexicon_ru import LEXICON_ASSISTED_GALLERY_RU

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSISTED_GALLERY_ROOT: Final[Path] = _PROJECT_ROOT / "data" / "assisted_gallery"

# callback_data Telegram ≤ 64 байт; только ASCII
BODY_DIR: Final[dict[str, str]] = {
    "Седан": "sedan",
    "Кроссовер": "suv",
    "Электромобиль": "electric",
}

BUDGET_DIR: Final[dict[str, str]] = {
    "до 12.000$": "0-12k",
    "12.000$ - 15.000$": "12k-15k",
    "15.000$ - 20.000$": "15k-20k",
    "20.000$ - 30.000$": "20k-30k",
    "30.000$ - 50.000$": "30k-50k",
    "50.000$+": "50k-plus",
}

_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp"}
)


@dataclass(frozen=True)
class AssistedGalleryPick:
    car_folder: str
    display_title: str
    image_paths: list[Path]
    body_style_key: str
    budget_key: str


def _folder_title(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _list_car_dirs(budget_path: Path) -> list[Path]:
    if not budget_path.is_dir():
        return []
    dirs = [
        p for p in budget_path.iterdir() if p.is_dir() and not p.name.startswith(".")
    ]
    return sorted(dirs, key=lambda p: p.name.lower())


def _list_images(car_dir: Path) -> list[Path]:
    files = []
    for p in car_dir.iterdir():
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES:
            files.append(p)
    return sorted(files, key=lambda x: x.name.lower())


def pick_random_assisted_gallery(
    body_style_key: str,
    budget_key: str,
    *,
    max_photos: int = 5,
    root: Optional[Path] = None,
) -> Optional[AssistedGalleryPick]:
    """Случайная папка авто в категории и до ``max_photos`` снимков (без повторов)."""
    base = root or ASSISTED_GALLERY_ROOT
    body_slug = BODY_DIR.get(body_style_key)
    budget_slug = BUDGET_DIR.get(budget_key)
    if not body_slug or not budget_slug:
        return None

    budget_path = base / body_slug / budget_slug
    car_dirs = _list_car_dirs(budget_path)
    if not car_dirs:
        return None

    car_dir = random.choice(car_dirs)
    images = _list_images(car_dir)
    if not images:
        return None

    k = min(max_photos, len(images))
    chosen = random.sample(images, k=k)

    return AssistedGalleryPick(
        car_folder=car_dir.name,
        display_title=_folder_title(car_dir.name),
        image_paths=chosen,
        body_style_key=body_style_key,
        budget_key=budget_key,
    )


def parse_ag_lead_callback(data: str) -> Optional[tuple[str, str, str, str]]:
    """Возвращает (car_folder, body_key_ru, budget_key_ru, display_title) или None."""
    parts = data.split("|", 3)
    if len(parts) != 4 or parts[0] != "ag_lead":
        return None
    _, car_folder, body_slug, budget_slug = parts
    body_ru = next((k for k, v in BODY_DIR.items() if v == body_slug), body_slug)
    budget_ru = next(
        (k for k, v in BUDGET_DIR.items() if v == budget_slug), budget_slug
    )
    return car_folder, body_ru, budget_ru, _folder_title(car_folder)


def make_ag_lead_callback(pick: AssistedGalleryPick) -> str:
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


def build_assisted_gallery_media_group(
    first_name: str,
    pick: AssistedGalleryPick,
) -> list[InputMediaPhoto]:
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
    try:
        await callback.message.answer_media_group(media=media_group)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await callback.message.answer_media_group(media=media_group)
        return True
    except TelegramBadRequest:
        return False
