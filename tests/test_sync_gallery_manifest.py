"""Ручная чистка фото не должна ломать порядок подборки.

После правки галереи руками манифест начинает обещать авто и фото, которых нет:
бот показал бы такому авто пустую карточку, а дырка в приоритетах сдвинула бы
страницы "Подобрать еще".
"""

import json

from scripts.sync_gallery_manifest import sync


def _gallery(tmp_path, cars: list[tuple[str, int]]):
    """Create a one-category gallery: (folder, photos on disk)."""
    manifest = {"sedan": {"0-12k": []}}
    for priority, (folder, photos) in enumerate(cars, 1):
        car_dir = tmp_path / "sedan" / "0-12k" / folder
        car_dir.mkdir(parents=True)
        for i in range(photos):
            (car_dir / f"{i:02d}.jpg").write_bytes(b"jpg")
        manifest["sedan"]["0-12k"].append(
            {"priority": priority, "title": folder, "folder": folder, "photos": 9}
        )
    return manifest


def test_photo_count_is_recounted(tmp_path):
    manifest = _gallery(tmp_path, [("001_a", 3)])

    synced, changes = sync(tmp_path, manifest, apply=False)

    assert synced["sedan"]["0-12k"][0]["photos"] == 3
    assert changes


def test_car_without_folder_is_dropped_and_priorities_close_the_gap(tmp_path):
    manifest = _gallery(tmp_path, [("001_a", 2), ("002_b", 2), ("003_c", 2)])
    for photo in (tmp_path / "sedan" / "0-12k" / "002_b").iterdir():
        photo.unlink()
    (tmp_path / "sedan" / "0-12k" / "002_b").rmdir()

    synced, _ = sync(tmp_path, manifest, apply=False)

    cars = synced["sedan"]["0-12k"]
    assert [car["folder"] for car in cars] == ["001_a", "003_c"]
    # Иначе страница подборки уперлась бы в дырку в нумерации
    assert [car["priority"] for car in cars] == [1, 2]


def test_empty_folder_is_removed_from_disk(tmp_path):
    manifest = _gallery(tmp_path, [("001_a", 2), ("002_b", 0)])

    sync(tmp_path, manifest, apply=True)

    assert not (tmp_path / "sedan" / "0-12k" / "002_b").exists()


def test_sync_keeps_manually_fixed_titles(tmp_path):
    manifest = _gallery(tmp_path, [("001_a", 2)])
    manifest["sedan"]["0-12k"][0]["title"] = "2023 Mercedes-Benz EQE"

    synced, _ = sync(tmp_path, manifest, apply=False)

    assert synced["sedan"]["0-12k"][0]["title"] == "2023 Mercedes-Benz EQE"


def test_sync_is_idempotent(tmp_path):
    manifest = _gallery(tmp_path, [("001_a", 2)])

    synced, _ = sync(tmp_path, manifest, apply=False)
    synced_again, changes = sync(tmp_path, json.loads(json.dumps(synced)), apply=False)

    assert synced_again == synced
    assert changes == []
