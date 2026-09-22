"""Queries over the Copart inventory snapshot.

The snapshot lives in PostgreSQL rather than in the process: the CSV holds
about 145 000 rows, and keeping them parsed in memory cost 730 MB of resident
size. Filtering happens in SQL, so a search materialises only the handful of
rows it is going to offer.

Rows leave this module keyed by CSV column name and carrying the CSV text
verbatim. The car card renders year and odometer as they came, and a parsed
number would change the caption under the photo, so the parsed columns used
for filtering never cross this boundary.
"""

import logging
from typing import Any, AsyncIterator, Final, Iterable, Sequence

from psycopg import AsyncConnection, sql

logger = logging.getLogger(__name__)

# Copart обрезает "Model Group" до 10 символов ("GRAND CHER" от GRAND CHEROKEE),
# поэтому у такой длины префикс сравнивается без границы слова.
TRUNCATED_MODEL_LENGTH: Final[int] = 10

# Модель, при которой марка показывается целиком.
ALL_MODELS: Final[str] = "ALL MODELS"

# Значение "Sale Date M/D/CY" у лота, который уже не продаётся.
SALE_DATE_ABSENT: Final[str] = "0"

# Колонки CSV, которые читает бот, и текстовые колонки таблицы под них.
# Порядок задаёт и COPY при загрузке, и SELECT при чтении.
COLUMN_MAP: Final[tuple[tuple[str, str], ...]] = (
    ("Make", "make"),
    ("Model Group", "model_group"),
    ("Model Detail", "model_detail"),
    ("Year", "year_text"),
    ("Odometer", "odometer_text"),
    ("Sale Date M/D/CY", "sale_date"),
    ("Buy-It-Now Price", "buy_now_text"),
    ("Lot number", "lot_number"),
    ("Color", "color"),
    ("Engine", "engine"),
    ("Drive", "drive"),
    ("Transmission", "transmission"),
    ("Fuel Type", "fuel_type"),
    ("Image URL", "image_url"),
    ("Damage Description", "damage_description"),
    ("Trim", "trim"),
    ("Body Style", "body_style"),
)

CSV_COLUMNS: Final[tuple[str, ...]] = tuple(csv_name for csv_name, _ in COLUMN_MAP)
TEXT_COLUMNS: Final[tuple[str, ...]] = tuple(db_name for _, db_name in COLUMN_MAP)

# Разобранные значения идут последними: сначала текст, потом числа.
PARSED_COLUMNS: Final[tuple[str, ...]] = ("year", "odometer", "buy_now_price")
COPY_COLUMNS: Final[tuple[str, ...]] = TEXT_COLUMNS + PARSED_COLUMNS

# Группы кузовов для случайной подборки в рассылке. Предикат повторяет то, что
# раньше делали лямбды над Body Style: сравнение идёт по верхнему регистру.
_BODY_STYLE_PREDICATES: Final[dict[str, str]] = {
    "suv": (
        "(position('SPORT UTILITY' in upper(coalesce(body_style, ''))) > 0"
        " OR starts_with(upper(coalesce(body_style, '')), 'SUV')"
        " OR starts_with(upper(coalesce(body_style, '')), '4DR SPOR'))"
    ),
    "sedan": "starts_with(upper(coalesce(body_style, '')), 'SEDAN')",
}

BODY_STYLE_GROUPS: Final[tuple[str, ...]] = tuple(_BODY_STYLE_PREDICATES)

_SELECT_TEXT = sql.SQL(", ").join(sql.Identifier(name) for name in TEXT_COLUMNS)


def _rows_to_dicts(records: Iterable[Sequence[Any]]) -> list[dict[str, Any]]:
    """Rebuild CSV-shaped rows from the selected text columns.

    Args:
        records: Tuples in TEXT_COLUMNS order, optionally with trailing extras.

    Returns:
        One dict per record, keyed by CSV column name.
    """
    width = len(CSV_COLUMNS)
    return [dict(zip(CSV_COLUMNS, record[:width])) for record in records]


async def replace_sales_lots(
    conn: AsyncConnection,
    batches: AsyncIterator[Sequence[Sequence[Any]]],
) -> int:
    """Replace the whole snapshot with the rows of these batches.

    TRUNCATE plus COPY in one transaction: readers wait for the swap instead of
    ever seeing a half-loaded snapshot. The lock is held for the duration of the
    load, which is a few seconds once an hour.

    Args:
        conn: Connection whose transaction the caller owns.
        batches: Yields groups of records in COPY_COLUMNS order. Batched and
            asynchronous so the producer can parse the CSV in a worker thread:
            neither the whole file nor a whole snapshot of tuples is ever held
            in memory at once.

    Returns:
        How many rows the snapshot now holds.
    """
    statement = sql.SQL("COPY sales_lot ({columns}) FROM STDIN").format(
        columns=sql.SQL(", ").join(sql.Identifier(name) for name in COPY_COLUMNS),
    )
    loaded = 0
    async with conn.cursor() as cursor:
        await cursor.execute("TRUNCATE sales_lot;")
        async with cursor.copy(statement) as copy:
            async for batch in batches:
                for record in batch:
                    await copy.write_row(record)
                loaded += len(batch)
    return loaded


async def count_sales_lots(conn: AsyncConnection) -> int:
    """Return how many rows the snapshot holds."""
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT count(*) FROM sales_lot;")
        row = await cursor.fetchone()
    return row[0] if row else 0


async def search_cars(
    conn: AsyncConnection,
    *,
    brand: str,
    model: str,
    year: tuple[int, int],
    odometer: tuple[float, float] | None,
    buy_now_only: bool,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Return a random sample of lots matching one search request.

    The sample is drawn in SQL: the caller offers at most ``limit`` of the
    matches anyway, and selecting them here is what keeps a popular make from
    pulling sixteen thousand rows into the process.

    Args:
        conn: Connection whose transaction the caller owns.
        brand: Make exactly as written on the button.
        model: Model as written on the button, or ALL_MODELS.
        year: Inclusive range of model years.
        odometer: Inclusive mileage range, or None to accept any mileage.
        buy_now_only: Keep only lots carrying a BUY NOW price.
        limit: How many rows to return at most.

    Returns:
        Tuple of the sampled rows and how many rows matched in total.
    """
    conditions = [
        sql.SQL("make = %(brand)s"),
        sql.SQL("year BETWEEN %(year_from)s AND %(year_to)s"),
        sql.SQL("coalesce(sale_date, '') <> %(sale_date_absent)s"),
    ]
    params: dict[str, Any] = {
        "brand": brand,
        "year_from": year[0],
        "year_to": year[1],
        "sale_date_absent": SALE_DATE_ABSENT,
        "limit": limit,
    }

    if model != ALL_MODELS:
        conditions.append(_model_condition(model))
        params["model"] = model
        params["model_prefix"] = f"{model} "

    if odometer is not None:
        conditions.append(sql.SQL("odometer BETWEEN %(odo_from)s AND %(odo_to)s"))
        params["odo_from"] = odometer[0]
        params["odo_to"] = odometer[1]

    if buy_now_only:
        conditions.append(sql.SQL("buy_now_price > 0"))

    statement = sql.SQL(
        "SELECT {columns}, count(*) OVER () AS matched"
        " FROM sales_lot WHERE {conditions}"
        " ORDER BY random() LIMIT %(limit)s"
    ).format(
        columns=_SELECT_TEXT,
        conditions=sql.SQL(" AND ").join(conditions),
    )

    async with conn.cursor() as cursor:
        await cursor.execute(statement, params)
        records = await cursor.fetchall()

    matched = records[0][-1] if records else 0
    return _rows_to_dicts(records), matched


def _model_condition(model: str) -> sql.Composed:
    """Build the predicate that mirrors how a model button matches a row.

    Exact equality is not enough: Copart splits one model across several
    "Model Group" values ("TAOS", "TAOS SE", "TAOS SEL") and dumps the rest
    into "ALL OTHER", keeping the real name in "Model Detail". Matching by word
    boundary keeps unrelated models apart: "M3" must not catch "M340I".

    Args:
        model: Model as written on the button.

    Returns:
        A predicate over model_group and model_detail.
    """
    alternatives = [
        sql.SQL("btrim(coalesce(model_group, '')) = %(model)s"),
        sql.SQL("starts_with(btrim(coalesce(model_group, '')), %(model_prefix)s)"),
        sql.SQL("btrim(coalesce(model_detail, '')) = %(model)s"),
        sql.SQL("starts_with(btrim(coalesce(model_detail, '')), %(model_prefix)s)"),
    ]
    if len(model) == TRUNCATED_MODEL_LENGTH:
        alternatives.append(
            sql.SQL("starts_with(btrim(coalesce(model_detail, '')), %(model)s)")
        )
    return sql.SQL("({alternatives})").format(
        alternatives=sql.SQL(" OR ").join(alternatives),
    )


async def random_top_cars(
    conn: AsyncConnection,
    *,
    body_group: str,
    min_year: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Return a random sample of fresh lots of one body group with a BUY NOW price.

    Args:
        conn: Connection whose transaction the caller owns.
        body_group: Key of BODY_STYLE_GROUPS.
        min_year: Oldest model year the newsletter may offer.
        limit: How many rows to return at most.

    Returns:
        Sampled rows, empty when the group is unknown or nothing matches.
    """
    predicate = _BODY_STYLE_PREDICATES.get(body_group)
    if predicate is None:
        logger.warning("Неизвестная группа кузовов: %s", body_group)
        return []

    statement = sql.SQL(
        "SELECT {columns} FROM sales_lot"
        " WHERE year >= %(min_year)s"
        " AND buy_now_price > 0"
        " AND coalesce(sale_date, '') <> %(sale_date_absent)s"
        " AND {predicate}"
        " ORDER BY random() LIMIT %(limit)s"
    ).format(
        columns=_SELECT_TEXT,
        predicate=sql.SQL(predicate),
    )

    async with conn.cursor() as cursor:
        await cursor.execute(
            statement,
            {
                "min_year": min_year,
                "sale_date_absent": SALE_DATE_ABSENT,
                "limit": limit,
            },
        )
        records = await cursor.fetchall()

    return _rows_to_dicts(records)
