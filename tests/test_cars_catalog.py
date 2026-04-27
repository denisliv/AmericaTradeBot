"""Unit tests for cars.md parser and search."""

from pathlib import Path

import pytest

from app.infrastructure.services.ai_manager.cars_catalog import (
    find_catalog_price_benchmark,
    load_cars_catalog,
    recommend_catalog_examples_by_budget,
    search_catalog_examples,
)


@pytest.fixture
def cars_md_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "ai_manager" / "cars.md"


def test_budget_14k_finds_12_15_band(cars_md_path: Path) -> None:
    cat = load_cars_catalog(cars_md_path)
    text, entries = search_catalog_examples(
        catalog=cat, body_or_category="электро", budget_usd=14_000, mode="full_section"
    )
    assert "12" in text and "15" in text
    assert any("Nissan Leaf" in e.model for e in entries)
    assert len(entries) == 3


def test_electric_one_per_band(cars_md_path: Path) -> None:
    cat = load_cars_catalog(cars_md_path)
    _text, entries = search_catalog_examples(
        catalog=cat, body_or_category="электромобиль", mode="one_per_price_band"
    )
    # Six price bands in electric section
    assert len(entries) == 6


def test_sedan_budget_section(cars_md_path: Path) -> None:
    cat = load_cars_catalog(cars_md_path)
    text, _entries = search_catalog_examples(
        catalog=cat, body_or_category="седан", budget_usd=18_000, mode="full_section"
    )
    assert "15" in text
    assert "BMW" in text or "Ауди" in text or "Audi" in text


def test_budget_only_recommendations_returns_three_or_four_diverse_examples(
    cars_md_path: Path,
) -> None:
    cat = load_cars_catalog(cars_md_path)

    text, entries = recommend_catalog_examples_by_budget(
        catalog=cat,
        budget_usd=25_000,
        limit=4,
    )

    assert 3 <= len(entries) <= 4
    assert "справочные примеры" in text.lower()
    assert "реальные варианты на аукционе" in text.lower()
    assert len({entry.category_title for entry in entries}) >= 2


def test_find_catalog_price_benchmark_prefers_electric_model_match(
    cars_md_path: Path,
) -> None:
    cat = load_cars_catalog(cars_md_path)

    benchmark = find_catalog_price_benchmark(
        catalog=cat,
        make="CHEVROLET",
        model="EQUINOX",
        year=2025,
        fuel_type="ELECTRIC",
        body_style="SPORT UTILITY VEHICLE",
    )

    assert benchmark is not None
    assert benchmark.entry.model == "Chevrolet Equinox EV"
    assert benchmark.lo_usd == 20_000
    assert benchmark.hi_usd == 30_000
    assert benchmark.match_type == "model"
