"""Copart matching rules, now that they live in SQL.

These assertions moved here from test_salesdata_filters.py when the snapshot
went from an in-process list into PostgreSQL. The rules are the same and the
reasons they exist are the same; only the place that enforces them changed.
"""

import pytest

from app.infrastructure.database.sales_lots import (
    random_top_cars,
    replace_sales_lots,
    search_cars,
)
from app.infrastructure.services.salesdata import to_snapshot_record

_ANY_YEAR = (1990, 2030)


def _row(**overrides) -> dict:
    """Build a CSV-shaped row with sane defaults for the fields under test."""
    row = {
        "Make": "VOLKSWAGEN",
        "Model Group": "TAOS",
        "Model Detail": "TAOS",
        "Year": "2022",
        "Odometer": "50000",
        "Sale Date M/D/CY": "20260101",
        "Buy-It-Now Price": "12500",
        "Lot number": "12345678",
        "Color": "WHITE",
        "Engine": "1.5L",
        "Drive": "AWD",
        "Transmission": "AUTOMATIC",
        "Fuel Type": "GAS",
        "Image URL": "https://example.invalid/images/12345678",
        "Damage Description": "FRONT END",
        "Trim": "SE",
        "Body Style": "SPORT UTILITY",
    }
    row.update(overrides)
    return row


async def _load(conn, *rows: dict) -> None:
    """Put exactly these rows into the snapshot."""

    async def _batches():
        yield [to_snapshot_record(row) for row in rows]

    await replace_sales_lots(conn, _batches())


async def _search(conn, **kwargs) -> list[dict]:
    params = {
        "brand": "VOLKSWAGEN",
        "model": "TAOS",
        "year": _ANY_YEAR,
        "odometer": None,
        "buy_now_only": False,
        "limit": 60,
    }
    params.update(kwargs)
    rows, _ = await search_cars(conn, **params)
    return rows


# --- как модель на кнопке находит строки Copart -----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group", "detail"),
    [
        ("TAOS", "TAOS"),
        ("TAOS SE", "TAOS"),
        ("TAOS S", "TAOS"),
        ("TAOS SEL", "TAOS"),
        # Самая массовая группа: Copart сваливает Taos в "ALL OTHER",
        # а настоящее имя оставляет только в Model Detail
        ("ALL OTHER", "TAOS"),
    ],
)
async def test_model_button_finds_all_copart_spellings(sales_lot_conn, group, detail):
    await _load(sales_lot_conn, _row(**{"Model Group": group, "Model Detail": detail}))

    assert len(await _search(sales_lot_conn)) == 1


@pytest.mark.asyncio
async def test_truncated_model_group_finds_full_name(sales_lot_conn):
    # Copart обрезает Model Group до 10 символов: GRAND CHEROKEE -> "GRAND CHER"
    await _load(
        sales_lot_conn,
        _row(
            **{
                "Make": "JEEP",
                "Model Group": "CHEROKEE",
                "Model Detail": "GRAND CHEROKEE",
            }
        ),
    )

    found = await _search(sales_lot_conn, brand="JEEP", model="GRAND CHER")
    assert len(found) == 1


@pytest.mark.asyncio
async def test_prefix_match_does_not_merge_different_models(sales_lot_conn):
    # "M3" не должен притягивать M340i: это разные автомобили
    await _load(
        sales_lot_conn,
        _row(**{"Make": "BMW", "Model Group": "M340I", "Model Detail": "M340I"}),
    )

    assert await _search(sales_lot_conn, brand="BMW", model="M3") == []


@pytest.mark.asyncio
async def test_prefix_match_keeps_model_variants(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Make": "AUDI", "Model Group": "A4", "Model Detail": "A4 ALLROAD"}),
    )

    assert len(await _search(sales_lot_conn, brand="AUDI", model="A4")) == 1


@pytest.mark.asyncio
async def test_other_model_of_same_brand_is_not_matched(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Model Group": "TIGUAN", "Model Detail": "TIGUAN"}),
    )

    assert await _search(sales_lot_conn) == []


@pytest.mark.asyncio
async def test_all_models_matches_any_model_of_brand(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Make": "BMW", "Model Group": "X5", "Model Detail": "X5"}),
    )

    assert len(await _search(sales_lot_conn, brand="BMW", model="ALL MODELS")) == 1


@pytest.mark.asyncio
async def test_all_models_still_checks_brand_and_year(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Make": "AUDI", "Model Group": "Q5", "Model Detail": "Q5"}),
    )

    found = await _search(sales_lot_conn, brand="BMW", model="ALL MODELS")
    assert found == []


@pytest.mark.asyncio
async def test_model_matching_ignores_surrounding_spaces(sales_lot_conn):
    # Раньше сравнение шло по row.get(...).strip(), и фид приносит такие значения
    await _load(sales_lot_conn, _row(**{"Model Group": "  TAOS  "}))

    assert len(await _search(sales_lot_conn)) == 1


# --- цена BUY NOW -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["0", "", "N/A"])
async def test_buy_now_only_drops_lot_without_usable_price(sales_lot_conn, price):
    await _load(sales_lot_conn, _row(**{"Buy-It-Now Price": price}))

    assert await _search(sales_lot_conn, buy_now_only=True) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["12500", "8500.0"])
async def test_buy_now_only_keeps_lot_with_positive_price(sales_lot_conn, price):
    # Copart пишет цену и целым числом, и с дробной частью
    await _load(sales_lot_conn, _row(**{"Buy-It-Now Price": price}))

    assert len(await _search(sales_lot_conn, buy_now_only=True)) == 1


@pytest.mark.asyncio
async def test_all_variants_keep_lot_without_price(sales_lot_conn):
    # Без фильтра "только BUY NOW" аукционные лоты показываются наравне
    await _load(sales_lot_conn, _row(**{"Buy-It-Now Price": "0"}))

    assert len(await _search(sales_lot_conn, buy_now_only=False)) == 1


# --- год, дата торгов, пробег ----------------------------------------------


@pytest.mark.asyncio
async def test_year_outside_the_requested_range_is_dropped(sales_lot_conn):
    await _load(sales_lot_conn, _row(**{"Year": "2019"}))

    assert await _search(sales_lot_conn, year=(2021, 2023)) == []


@pytest.mark.asyncio
async def test_unreadable_year_never_matches(sales_lot_conn):
    # Раньше int("") бросал ValueError и строка выпадала из подбора
    await _load(sales_lot_conn, _row(**{"Year": ""}))

    assert await _search(sales_lot_conn) == []


@pytest.mark.asyncio
async def test_lot_that_is_no_longer_on_sale_is_dropped(sales_lot_conn):
    await _load(sales_lot_conn, _row(**{"Sale Date M/D/CY": "0"}))

    assert await _search(sales_lot_conn) == []


@pytest.mark.asyncio
async def test_odometer_filter_keeps_only_the_requested_range(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Odometer": "30000", "Lot number": "inside"}),
        _row(**{"Odometer": "300000", "Lot number": "outside"}),
    )

    found = await _search(sales_lot_conn, odometer=(0, 100000))
    assert [row["Lot number"] for row in found] == ["inside"]


@pytest.mark.asyncio
async def test_unreadable_odometer_is_dropped_only_when_mileage_matters(
    sales_lot_conn,
):
    await _load(sales_lot_conn, _row(**{"Odometer": "N/A"}))

    assert await _search(sales_lot_conn, odometer=(0, 100000)) == []
    assert len(await _search(sales_lot_conn, odometer=None)) == 1


# --- что уезжает наружу -----------------------------------------------------


@pytest.mark.asyncio
async def test_row_comes_back_as_the_csv_wrote_it(sales_lot_conn):
    # Карточка авто печатает год и пробег дословно: разобранное число изменило
    # бы подпись под фотографией, а .strip() на числе вообще упал бы
    source = _row(**{"Year": "2022", "Odometer": "50000"})
    await _load(sales_lot_conn, source)

    (found,) = await _search(sales_lot_conn)
    assert found == source


@pytest.mark.asyncio
async def test_search_returns_no_more_than_the_limit(sales_lot_conn):
    await _load(sales_lot_conn, *(_row(**{"Lot number": str(n)}) for n in range(10)))

    assert len(await _search(sales_lot_conn, limit=4)) == 4


@pytest.mark.asyncio
async def test_search_reports_how_many_matched_beyond_the_limit(sales_lot_conn):
    await _load(sales_lot_conn, *(_row(**{"Lot number": str(n)}) for n in range(10)))

    rows, matched = await search_cars(
        sales_lot_conn,
        brand="VOLKSWAGEN",
        model="TAOS",
        year=_ANY_YEAR,
        odometer=None,
        buy_now_only=False,
        limit=4,
    )
    assert len(rows) == 4
    assert matched == 10


# --- подборка для прогревочной рассылки -------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body_style",
    ["SPORT UTILITY", "SUV", "4DR SPOR UTILITY", "sport utility"],
)
async def test_suv_group_covers_every_copart_spelling(sales_lot_conn, body_style):
    await _load(sales_lot_conn, _row(**{"Body Style": body_style}))

    found = await random_top_cars(
        sales_lot_conn, body_group="suv", min_year=2022, limit=10
    )
    assert len(found) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body_style", ["SEDAN", "SEDAN 4DR", "SEDAN 4D"])
async def test_sedan_group_covers_every_copart_spelling(sales_lot_conn, body_style):
    await _load(sales_lot_conn, _row(**{"Body Style": body_style}))

    found = await random_top_cars(
        sales_lot_conn, body_group="sedan", min_year=2022, limit=10
    )
    assert len(found) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body_style", "group"),
    [
        ("SPORT UTILITY", "sedan"),
        ("4DR SPOR UTILITY", "sedan"),
        ("SEDAN 4DR", "suv"),
    ],
)
async def test_body_groups_do_not_overlap(sales_lot_conn, body_style, group):
    await _load(sales_lot_conn, _row(**{"Body Style": body_style}))

    found = await random_top_cars(
        sales_lot_conn, body_group=group, min_year=2022, limit=10
    )
    assert found == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body_style", ["PICKUP", "WAGON", "", None])
async def test_other_body_styles_belong_to_no_group(sales_lot_conn, body_style):
    await _load(sales_lot_conn, _row(**{"Body Style": body_style}))

    for group in ("suv", "sedan"):
        found = await random_top_cars(
            sales_lot_conn, body_group=group, min_year=2022, limit=10
        )
        assert found == [], group


@pytest.mark.asyncio
async def test_newsletter_offers_only_fresh_lots_with_a_price(sales_lot_conn):
    await _load(
        sales_lot_conn,
        _row(**{"Year": "2021", "Lot number": "too-old"}),
        _row(**{"Buy-It-Now Price": "0", "Lot number": "no-price"}),
        _row(**{"Sale Date M/D/CY": "0", "Lot number": "not-on-sale"}),
        _row(**{"Lot number": "offered"}),
    )

    found = await random_top_cars(
        sales_lot_conn, body_group="suv", min_year=2022, limit=10
    )
    assert [row["Lot number"] for row in found] == ["offered"]


@pytest.mark.asyncio
async def test_unknown_body_group_offers_nothing(sales_lot_conn):
    await _load(sales_lot_conn, _row())

    found = await random_top_cars(
        sales_lot_conn, body_group="coupe", min_year=2022, limit=10
    )
    assert found == []


# --- загрузка снимка --------------------------------------------------------


@pytest.mark.asyncio
async def test_loading_a_snapshot_replaces_the_previous_one(sales_lot_conn):
    await _load(sales_lot_conn, _row(**{"Lot number": "old"}))
    await _load(sales_lot_conn, _row(**{"Lot number": "new"}))

    found = await _search(sales_lot_conn)
    assert [row["Lot number"] for row in found] == ["new"]
