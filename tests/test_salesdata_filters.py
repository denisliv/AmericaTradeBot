from app.infrastructure.services.salesdata import filter_by_make_and_model, match_car


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
