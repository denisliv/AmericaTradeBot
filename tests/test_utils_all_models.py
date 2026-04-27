from app.infrastructure.services.utils import filter_by_make_and_model


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
