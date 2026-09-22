import logging

import aiohttp
import pytest

from app.infrastructure.services.salesdata import (
    REQUIRED_SALESDATA_COLUMNS,
    _validate_sales_csv_file,
    download_csv,
    to_snapshot_record,
)


def _write(tmp_path, text: str):
    target = tmp_path / "salesdata.csv"
    target.write_text(text, encoding="utf-8")
    return target


def _full_header() -> str:
    return ",".join(REQUIRED_SALESDATA_COLUMNS)


def test_validate_rejects_missing_required_columns(tmp_path):
    target = _write(tmp_path, "Make,Year\nToyota,2020\n")

    with pytest.raises(ValueError, match="missing required columns"):
        _validate_sales_csv_file(target)


def test_validate_rejects_empty_file(tmp_path):
    target = _write(tmp_path, "")

    with pytest.raises(ValueError, match="empty"):
        _validate_sales_csv_file(target)


def test_validate_rejects_header_without_data_rows(tmp_path):
    target = _write(tmp_path, _full_header() + "\n")

    with pytest.raises(ValueError, match="no data rows"):
        _validate_sales_csv_file(target)


def test_validate_accepts_a_well_formed_feed(tmp_path):
    row = ",".join("x" for _ in REQUIRED_SALESDATA_COLUMNS)
    target = _write(tmp_path, _full_header() + "\n" + row + "\n")

    _validate_sales_csv_file(target)


def test_validate_reads_only_the_first_two_lines(tmp_path):
    # Проверка не должна разбирать весь файл: на 84 МБ это стоило 370 МБ памяти.
    # Битая строка в середине не мешает признать фид годным.
    row = ",".join("x" for _ in REQUIRED_SALESDATA_COLUMNS)
    target = _write(tmp_path, _full_header() + "\n" + row + "\n" + "мусор\n" * 100)

    _validate_sales_csv_file(target)


def test_validate_accepts_a_feed_with_byte_order_mark(tmp_path):
    row = ",".join("x" for _ in REQUIRED_SALESDATA_COLUMNS)
    target = tmp_path / "salesdata.csv"
    target.write_bytes(
        b"\xef\xbb\xbf" + (_full_header() + "\n" + row + "\n").encode("utf-8")
    )

    _validate_sales_csv_file(target)


def test_snapshot_record_keeps_the_text_and_adds_parsed_values():
    row = {name: "" for name in REQUIRED_SALESDATA_COLUMNS}
    row.update({"Year": "2022", "Odometer": "50000", "Buy-It-Now Price": "8500.0"})

    record = to_snapshot_record(row)

    # Текст уходит в базу дословно, разобранные значения дописываются в хвост
    assert record[3] == "2022"
    assert record[4] == "50000"
    assert record[-3:] == (2022, 50000.0, 8500)


def test_snapshot_record_survives_values_the_feed_cannot_write():
    row = {name: "" for name in REQUIRED_SALESDATA_COLUMNS}
    row.update({"Year": "", "Odometer": "N/A", "Buy-It-Now Price": ""})

    assert to_snapshot_record(row)[-3:] == (None, None, 0)


@pytest.mark.asyncio
async def test_failed_download_never_writes_the_feed_key_to_the_log(caplog):
    # В адресе фида едет партнёрский authKey Copart, а stdout контейнера
    # собирается и уезжает дальше. Порт 1 закрыт, поэтому соединение падает
    # сразу и мы видим именно ветку обработки ошибки.
    secret = "SUPERSECRETAUTHKEY"
    url = f"http://127.0.0.1:1/salesdata.cgi?authKey={secret}"

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(aiohttp.ClientError):
            await download_csv(url, db_pool=None)

    assert secret not in caplog.text
