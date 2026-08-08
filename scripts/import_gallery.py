"""Import the assisted-selection gallery from the raw Google Drive export.

Reads ``data/gdrive`` (folders named as in Drive, with priority prefixes) and
builds ``data/assisted_gallery``: latin slugs for folders, Telegram-compatible
images and ``gallery.json`` holding the priority and the display title of every
car.

AVIF images are converted to JPEG: Telegram rejects AVIF, and a third of the
export comes in that format.

Titles already present in ``gallery.json`` are preserved on re-runs, so manual
spelling fixes are not lost.

Usage::

    uv run python scripts/import_gallery.py [--force]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Final

import pillow_avif  # noqa: F401  (registers the AVIF plugin in Pillow)
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.paths import ASSISTED_GALLERY_DIR, DATA_DIR  # noqa: E402

logger = logging.getLogger("import_gallery")

SOURCE_DIR: Final[Path] = DATA_DIR / "gdrive"
MANIFEST_NAME: Final[str] = "gallery.json"

BODY_DIRS: Final[dict[str, str]] = {
    "1. Кроссовер": "suv",
    "2. Седан": "sedan",
    "3. Электромобиль": "electric",
}

BUDGET_DIRS: Final[dict[str, str]] = {
    "1. До 12.000": "0-12k",
    "2. До 15.000": "12k-15k",
    "3. До 20.000": "15k-20k",
    "4. 20-30.000": "20k-30k",
    "5. 30-50.000": "30k-50k",
    "6. 50.000+": "50k-plus",
}

# Форматы, которые Telegram принимает как фото
KEEP_SUFFIXES: Final[frozenset[str]] = frozenset({".jpg", ".jpeg", ".png", ".webp"})
CONVERT_SUFFIXES: Final[frozenset[str]] = frozenset({".avif"})

JPEG_QUALITY: Final[int] = 88

_NUMBERED_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(\d+)\s*\.\s*(.+?)\s*$")


class GalleryImportError(Exception):
    """Raised when the source export does not match the expected layout."""


def parse_numbered(name: str) -> tuple[int, str]:
    """Split a Drive folder name into its priority and title.

    Args:
        name: Folder name, e.g. ``"12. 2022 Mitsubishi Eclipse Cross"``.

    Returns:
        Tuple of priority and title.

    Raises:
        GalleryImportError: If the folder has no numeric prefix.
    """
    match = _NUMBERED_RE.match(name)
    if not match:
        raise GalleryImportError(f"Folder without a priority prefix: {name!r}")
    return int(match.group(1)), match.group(2)


def make_slug(priority: int, title: str) -> str:
    """Build a latin folder name that keeps the priority sortable."""
    body = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"{priority:03d}_{body}"


def copy_image(source: Path, target_dir: Path) -> Path:
    """Copy one image into the gallery, converting AVIF to JPEG.

    Args:
        source: Image inside the raw export.
        target_dir: Destination car folder.

    Returns:
        Path of the written file.
    """
    suffix = source.suffix.lower()
    if suffix in CONVERT_SUFFIXES:
        target = target_dir / f"{source.stem}.jpg"
        with Image.open(source) as image:
            image.convert("RGB").save(target, "JPEG", quality=JPEG_QUALITY)
        return target

    target = target_dir / source.name
    shutil.copy2(source, target)
    return target


def load_existing_titles(manifest_path: Path) -> dict[str, str]:
    """Read manually corrected titles from a previous manifest, keyed by slug."""
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        car["folder"]: car["title"]
        for budgets in manifest.values()
        for cars in budgets.values()
        for car in cars
    }


def import_car(source_dir: Path, target_dir: Path) -> tuple[int, int, int]:
    """Copy every image of one car.

    Returns:
        Tuple of (copied, converted, skipped) file counts.
    """
    copied = converted = skipped = 0
    target_dir.mkdir(parents=True, exist_ok=True)
    for image in sorted(source_dir.iterdir(), key=lambda p: p.name.lower()):
        if not image.is_file():
            continue
        suffix = image.suffix.lower()
        if suffix in CONVERT_SUFFIXES:
            copy_image(image, target_dir)
            converted += 1
            copied += 1
        elif suffix in KEEP_SUFFIXES:
            copy_image(image, target_dir)
            copied += 1
        else:
            logger.warning("Unsupported file skipped: %s", image)
            skipped += 1
    return copied, converted, skipped


def import_gallery(source: Path, target: Path, known_titles: dict[str, str]) -> dict:
    """Rebuild the whole gallery and return the manifest."""
    manifest: dict[str, dict[str, list[dict]]] = {}
    total_cars = total_images = total_converted = 0
    empty_cars: list[str] = []

    # data/ не хранится в git, кроме маркеров структуры каталогов
    (target / ".gitkeep").touch()

    for body_name, body_slug in BODY_DIRS.items():
        body_dir = source / body_name
        if not body_dir.is_dir():
            raise GalleryImportError(f"Missing body folder: {body_dir}")
        manifest[body_slug] = {}
        (target / body_slug).mkdir(parents=True, exist_ok=True)
        (target / body_slug / ".gitkeep").touch()

        for budget_name, budget_slug in BUDGET_DIRS.items():
            budget_dir = body_dir / budget_name
            if not budget_dir.is_dir():
                raise GalleryImportError(f"Missing budget folder: {budget_dir}")

            cars: list[dict] = []
            entries = [p for p in budget_dir.iterdir() if p.is_dir()]
            for car_dir in sorted(entries, key=lambda p: parse_numbered(p.name)[0]):
                priority, raw_title = parse_numbered(car_dir.name)
                slug = make_slug(priority, raw_title)
                copied, converted, _ = import_car(
                    car_dir, target / body_slug / budget_slug / slug
                )
                if copied == 0:
                    empty_cars.append(f"{body_slug}/{budget_slug}/{car_dir.name}")
                    shutil.rmtree(
                        target / body_slug / budget_slug / slug, ignore_errors=True
                    )
                    continue
                cars.append(
                    {
                        "priority": priority,
                        "title": known_titles.get(slug, raw_title),
                        "folder": slug,
                        "photos": copied,
                    }
                )
                total_cars += 1
                total_images += copied
                total_converted += converted

            # Приоритеты пересчитываются подряд: в экспорте бывают пропуски
            # из-за пустых папок, а страницы подборки идут без дыр.
            for position, car in enumerate(cars, 1):
                car["priority"] = position
            manifest[body_slug][budget_slug] = cars

    logger.info(
        "Imported %d cars, %d images (%d converted from AVIF)",
        total_cars,
        total_images,
        total_converted,
    )
    if empty_cars:
        logger.warning("Skipped car folders without images: %s", ", ".join(empty_cars))
    return manifest


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing gallery (the manifest titles are kept)",
    )
    args = parser.parse_args()

    if not SOURCE_DIR.is_dir():
        logger.error("Source export not found: %s", SOURCE_DIR)
        return 1

    manifest_path = ASSISTED_GALLERY_DIR / MANIFEST_NAME
    known_titles = load_existing_titles(manifest_path)
    if ASSISTED_GALLERY_DIR.exists() and any(ASSISTED_GALLERY_DIR.iterdir()):
        if not args.force:
            logger.error(
                "%s is not empty; move it away or re-run with --force",
                ASSISTED_GALLERY_DIR,
            )
            return 1
        shutil.rmtree(ASSISTED_GALLERY_DIR)
    ASSISTED_GALLERY_DIR.mkdir(parents=True, exist_ok=True)

    try:
        manifest = import_gallery(SOURCE_DIR, ASSISTED_GALLERY_DIR, known_titles)
    except GalleryImportError as exc:
        logger.error("%s", exc)
        return 1

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    logger.info("Manifest written: %s", manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
