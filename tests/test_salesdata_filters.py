import pytest

from app.infrastructure.services.salesdata import filter_by_make_and_model, match_car


def _model_row(group: str, detail: str) -> dict:
    return {
        "Make": "VOLKSWAGEN",
        "Model Group": group,
        "Model Detail": detail,
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }


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
def test_model_button_finds_all_copart_spellings(group, detail):
    row = _model_row(group, detail)
    assert filter_by_make_and_model(row, "VOLKSWAGEN", "TAOS", (2021, 2023)) is True


def test_truncated_model_group_finds_full_name():
    # Copart обрезает Model Group до 10 символов: GRAND CHEROKEE -> "GRAND CHER"
    row = {
        "Make": "JEEP",
        "Model Group": "CHEROKEE",
        "Model Detail": "GRAND CHEROKEE",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }
    assert filter_by_make_and_model(row, "JEEP", "GRAND CHER", (2021, 2023)) is True


def test_prefix_match_does_not_merge_different_models():
    # "M3" не должен притягивать M340i: это разные автомобили
    row = {
        "Make": "BMW",
        "Model Group": "M340I",
        "Model Detail": "M340I",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }
    assert filter_by_make_and_model(row, "BMW", "M3", (2021, 2023)) is False


def test_prefix_match_keeps_model_variants():
    row = {
        "Make": "AUDI",
        "Model Group": "A4",
        "Model Detail": "A4 ALLROAD",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }
    assert filter_by_make_and_model(row, "AUDI", "A4", (2021, 2023)) is True


def test_other_model_of_same_brand_is_not_matched():
    row = _model_row("TIGUAN", "TIGUAN")
    assert filter_by_make_and_model(row, "VOLKSWAGEN", "TAOS", (2021, 2023)) is False


def test_filter_by_make_and_model_all_models_matches_any_model_of_brand():
    row = {
        "Make": "BMW",
        "Model Group": "X5",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }
    assert filter_by_make_and_model(row, "BMW", "ALL MODELS", (2021, 2023)) is True


def test_filter_by_make_and_model_all_models_still_checks_brand_and_year():
    wrong_brand_row = {
        "Make": "AUDI",
        "Model Group": "Q5",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
    }
    assert (
        filter_by_make_and_model(
            wrong_brand_row,
            "BMW",
            "ALL MODELS",
            (2021, 2023),
        )
        is False
    )


def _base_row(buy_now_price: str = "12500") -> dict:
    return {
        "Make": "BMW",
        "Model Group": "X5",
        "Year": "2022",
        "Sale Date M/D/CY": "20260101",
        "Buy-It-Now Price": buy_now_price,
    }


def test_match_car_buy_now_only_keeps_row_with_positive_price():
    assert match_car(
        _base_row(buy_now_price="12500"),
        "BMW",
        "ALL MODELS",
        (2021, 2023),
        auction_status=True,
    )


def test_match_car_buy_now_only_drops_zero_string_price():
    assert not match_car(
        _base_row(buy_now_price="0"),
        "BMW",
        "ALL MODELS",
        (2021, 2023),
        auction_status=True,
    )


def test_match_car_buy_now_only_drops_empty_price():
    assert not match_car(
        _base_row(buy_now_price=""),
        "BMW",
        "ALL MODELS",
        (2021, 2023),
        auction_status=True,
    )


def test_match_car_buy_now_only_drops_non_numeric_price():
    assert not match_car(
        _base_row(buy_now_price="N/A"),
        "BMW",
        "ALL MODELS",
        (2021, 2023),
        auction_status=True,
    )


def test_match_car_all_variants_keeps_zero_price():
    assert match_car(
        _base_row(buy_now_price="0"),
        "BMW",
        "ALL MODELS",
        (2021, 2023),
        auction_status=None,
    )
