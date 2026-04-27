import pytest

from app.infrastructure.services.utils import (
    REQUIRED_SALESDATA_COLUMNS,
    _validate_sales_csv_bytes,
    _write_sales_csv_atomically,
)


def test_validate_sales_csv_bytes_rejects_missing_required_columns():
    csv_bytes = b"Make,Year\nToyota,2020\n"

    with pytest.raises(ValueError, match="missing required columns"):
        _validate_sales_csv_bytes(csv_bytes)


def test_validate_sales_csv_bytes_rejects_empty_file():
    with pytest.raises(ValueError, match="empty"):
        _validate_sales_csv_bytes(b"")


@pytest.mark.asyncio
async def test_write_sales_csv_atomically_replaces_existing_file(tmp_path):
    target = tmp_path / "salesdata.csv"
    target.write_text("old,data\n", encoding="utf-8")
    csv_text = ",".join(REQUIRED_SALESDATA_COLUMNS) + "\n" + ",".join("x" for _ in REQUIRED_SALESDATA_COLUMNS) + "\n"

    await _write_sales_csv_atomically(target, csv_text.encode("utf-8"))

    assert target.read_text(encoding="utf-8") == csv_text
    assert not list(tmp_path.glob("*.tmp"))
