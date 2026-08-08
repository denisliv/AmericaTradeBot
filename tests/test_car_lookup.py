"""Подбор не должен объявлять «нет вариантов», когда лоты есть.

Copart отдаёт фото примерно у каждого пятого лота, а карточка без фото не
показывается. Проверка только первых кандидатов давала пустой ответ на поиске,
под который подходят тысячи машин.
"""

import pytest

from app.infrastructure.services import salesdata
from app.infrastructure.services.salesdata import (
    MAX_IMAGE_LOOKUPS,
    collect_cars_with_images,
)


def _rows(total: int) -> list[dict]:
    return [{"Lot number": str(i)} for i in range(total)]


@pytest.fixture
def photos(monkeypatch):
    """Замыкает get_images на набор номеров лотов, у которых «есть фото»."""
    calls = []

    def configure(with_photo: set[str]):
        async def fake_get_images(row, session, max_images=9):
            calls.append(row["Lot number"])
            return ["url"] if row["Lot number"] in with_photo else []

        monkeypatch.setattr(salesdata, "get_images", fake_get_images)

    return configure, calls


@pytest.mark.asyncio
async def test_tops_up_candidates_until_enough_have_photos(photos):
    # Фото только у 30-го и 31-го лота: старый код проверял лишь первые 10
    configure, calls = photos
    configure({"30", "31"})

    cars = await collect_cars_with_images(_rows(100), count=2)

    assert [row["Lot number"] for row, _ in cars] == ["30", "31"]
    assert len(calls) > 10


@pytest.mark.asyncio
async def test_stops_as_soon_as_enough_cars_are_collected(photos):
    configure, calls = photos
    configure({str(i) for i in range(100)})

    cars = await collect_cars_with_images(_rows(100), count=3)

    assert len(cars) == 3
    # Лишние запросы к Copart на каждый поиск ни к чему
    assert len(calls) <= 12


@pytest.mark.asyncio
async def test_lookups_are_capped(photos):
    configure, calls = photos
    configure(set())

    cars = await collect_cars_with_images(_rows(5000), count=10)

    assert cars == []
    assert len(calls) <= MAX_IMAGE_LOOKUPS


@pytest.mark.asyncio
async def test_returns_what_it_found_when_photos_run_out(photos):
    configure, _ = photos
    configure({"1"})

    cars = await collect_cars_with_images(_rows(20), count=10)

    assert [row["Lot number"] for row, _ in cars] == ["1"]


@pytest.mark.asyncio
async def test_order_of_candidates_is_preserved(photos):
    configure, _ = photos
    configure({"2", "5", "9"})

    cars = await collect_cars_with_images(_rows(20), count=3)

    assert [row["Lot number"] for row, _ in cars] == ["2", "5", "9"]
