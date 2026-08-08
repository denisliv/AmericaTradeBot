"""Drop studio shots on a plain white background from the assisted gallery.

The customer asked to keep only photos with a coloured background. Studio
renders are detected by their border: a plain white cyclorama leaves the frame
edges bright and fully desaturated, while street shots and interiors do not.

A car folder is never emptied: if fewer than ``MIN_KEPT_PHOTOS`` photos would
remain, the folder is left untouched and reported for a manual review.

Usage::

    uv run python scripts/filter_white_bg.py            # report only
    uv run python scripts/filter_white_bg.py --apply    # delete and update the manifest
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Final

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.paths import ASSISTED_GALLERY_DIR  # noqa: E402

logger = logging.getLogger("filter_white_bg")

MANIFEST_NAME: Final[str] = "gallery.json"

# Фон оценивается по четырем углам кадра, а не по всей рамке: у студийной
# циклорамы белые все четыре угла, а у съемки на улице низ кадра - это всегда
# асфальт или трава. Доля белого по всей рамке для этого не годится: черное
# авто в студии дает 0.54, а светлое небо на трассе - 0.42.
MIN_MEAN_WHITE: Final[float] = 0.80
MIN_CORNER_WHITE: Final[float] = 0.50
# Сторона углового квадрата в долях стороны изображения
CORNER_FRACTION: Final[float] = 0.12
# Порог "белого" пикселя в HSV
MIN_VALUE: Final[int] = 238
MAX_SATURATION: Final[int] = 16

# Меньше этого числа фото в папке оставлять нельзя: карточка показывает до 5
MIN_KEPT_PHOTOS: Final[int] = 5


def corner_white_shares(path: Path) -> list[float]:
    """Return the share of white pixels in each of the four image corners."""
    with Image.open(path) as image:
        hsv = image.convert("HSV")
        hsv.thumbnail((240, 240))
        width, height = hsv.size
        pixels = hsv.load()
        size_x = max(3, round(width * CORNER_FRACTION))
        size_y = max(3, round(height * CORNER_FRACTION))

        shares = []
        for x0, y0 in (
            (0, 0),
            (width - size_x, 0),
            (0, height - size_y),
            (width - size_x, height - size_y),
        ):
            white = 0
            for y in range(y0, y0 + size_y):
                for x in range(x0, x0 + size_x):
                    _, saturation, value = pixels[x, y]
                    if value >= MIN_VALUE and saturation <= MAX_SATURATION:
                        white += 1
            shares.append(white / (size_x * size_y))
    return shares


def is_white_studio(path: Path) -> bool:
    """Whether the photo is a studio shot on a plain white background."""
    shares = corner_white_shares(path)
    return (
        sum(shares) / len(shares) >= MIN_MEAN_WHITE and min(shares) >= MIN_CORNER_WHITE
    )


def scan_car(car_dir: Path) -> tuple[list[Path], int]:
    """Return white-background photos of one car and its total photo count."""
    photos = sorted(p for p in car_dir.iterdir() if p.is_file())
    white = [p for p in photos if is_white_studio(p)]
    return white, len(photos)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete the detected photos instead of only reporting them",
    )
    args = parser.parse_args()

    manifest_path = ASSISTED_GALLERY_DIR / MANIFEST_NAME
    if not manifest_path.is_file():
        logger.error(
            "Manifest not found: %s (run import_gallery.py first)", manifest_path
        )
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    deleted = 0
    needs_review: list[str] = []

    for body, budgets in manifest.items():
        for budget, cars in budgets.items():
            for car in cars:
                car_dir = ASSISTED_GALLERY_DIR / body / budget / car["folder"]
                white, total = scan_car(car_dir)
                if not white:
                    continue
                remaining = total - len(white)
                if remaining < MIN_KEPT_PHOTOS:
                    needs_review.append(
                        f"{body}/{budget}/{car['folder']}: "
                        f"{total} фото, из них белых {len(white)}, осталось бы {remaining}"
                    )
                    continue
                if args.apply:
                    for photo in white:
                        photo.unlink()
                    car["photos"] = remaining
                deleted += len(white)

    verb = "Удалено" if args.apply else "Будет удалено"
    logger.info("%s фото на белом фоне: %d", verb, deleted)
    if needs_review:
        logger.warning(
            "Папок не тронуто (осталось бы меньше %d фото): %d",
            MIN_KEPT_PHOTOS,
            len(needs_review),
        )
        for line in needs_review:
            logger.warning("  %s", line)

    if args.apply:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        logger.info("Manifest updated: %s", manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
