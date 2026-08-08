"""Bring ``gallery.json`` back in sync with the files on disk.

Photos are sometimes removed by hand after the import (a manual pass over the
white-background cleanup). The manifest then promises cars and photo counts that
no longer exist, and the bot logs warnings on every selection.

The script recounts photos, drops cars whose folder disappeared or ran out of
images, deletes empty car folders and renumbers priorities so that pages of the
selection stay gapless. Titles corrected by hand are kept.

Usage::

    uv run python scripts/sync_gallery_manifest.py            # report only
    uv run python scripts/sync_gallery_manifest.py --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infrastructure.paths import ASSISTED_GALLERY_DIR  # noqa: E402

logger = logging.getLogger("sync_gallery_manifest")

MANIFEST_NAME: Final[str] = "gallery.json"


def sync(root: Path, manifest: dict, *, apply: bool) -> tuple[dict, list[str]]:
    """Return the corrected manifest and the list of changes."""
    changes: list[str] = []
    synced: dict[str, dict[str, list[dict]]] = {}

    for body, budgets in manifest.items():
        synced[body] = {}
        for budget, cars in budgets.items():
            kept: list[dict] = []
            for car in cars:
                car_dir = root / body / budget / car["folder"]
                where = f"{body}/{budget}/{car['folder']}"
                if not car_dir.is_dir():
                    changes.append(f"убрано из манифеста (нет папки): {where}")
                    continue

                photos = [p for p in car_dir.iterdir() if p.is_file()]
                if not photos:
                    changes.append(f"убрано из манифеста (нет фото): {where}")
                    if apply:
                        car_dir.rmdir()
                    continue

                if len(photos) != car["photos"]:
                    changes.append(f"фото {car['photos']} -> {len(photos)}: {where}")
                    car["photos"] = len(photos)
                kept.append(car)

            for position, car in enumerate(kept, 1):
                if car["priority"] != position:
                    changes.append(
                        f"приоритет {car['priority']} -> {position}: "
                        f"{body}/{budget}/{car['folder']}"
                    )
                    car["priority"] = position
            synced[body][budget] = kept

    return synced, changes


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the corrected manifest and delete empty car folders",
    )
    args = parser.parse_args()

    manifest_path = ASSISTED_GALLERY_DIR / MANIFEST_NAME
    if not manifest_path.is_file():
        logger.error("Manifest not found: %s", manifest_path)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    synced, changes = sync(ASSISTED_GALLERY_DIR, manifest, apply=args.apply)

    if not changes:
        logger.info("Манифест уже соответствует файлам")
        return 0

    logger.info(
        "%s изменений: %d", "Внесено" if args.apply else "Требуется", len(changes)
    )
    for line in changes:
        logger.info("  %s", line)

    if args.apply:
        manifest_path.write_text(
            json.dumps(synced, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        total = sum(len(cars) for b in synced.values() for cars in b.values())
        logger.info("Манифест обновлён: %s (авто: %d)", manifest_path, total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
