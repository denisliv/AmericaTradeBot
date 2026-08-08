"""Assisted selection branch must match the Miro diagram: type → budget → TOP picks."""

import json
from pathlib import Path

import pytest

from app.bot.keyboards.keyboards_inline import (
    create_assisted_results_keyboard,
    create_choose_a_car_keyboard,
)
from app.infrastructure.services.assisted_gallery import (
    ANY_BODY_KEY,
    BODY_DIR,
    BUDGET_DIR,
    AssistedGalleryPick,
    _load_manifest,
    get_gallery_page,
    make_ag_lead_callback,
    parse_ag_lead_callback,
)
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    _load_manifest.cache_clear()
    yield
    _load_manifest.cache_clear()


def _make_gallery(root: Path, layout: dict[str, dict[str, list[str]]], photos: int = 2):
    """Create a gallery whose priorities follow the order of the given titles."""
    manifest: dict[str, dict[str, list[dict]]] = {}
    for body_slug, budgets in layout.items():
        manifest[body_slug] = {}
        for budget_slug, titles in budgets.items():
            cars = []
            for priority, title in enumerate(titles, 1):
                folder = f"{priority:03d}_{title.lower().replace(' ', '_')}"
                car_dir = root / body_slug / budget_slug / folder
                car_dir.mkdir(parents=True, exist_ok=True)
                for i in range(photos):
                    (car_dir / f"{i:02d}.jpg").write_bytes(b"jpg")
                cars.append(
                    {
                        "priority": priority,
                        "title": title,
                        "folder": folder,
                        "photos": photos,
                    }
                )
            manifest[body_slug][budget_slug] = cars
    (root / "gallery.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_choose_a_car_screen_matches_diagram():
    assert LEXICON_RU["choose_a_car_text"] == (
        "Вы уже определились, какой автомобиль хотите?"
    )
    keyboard = create_choose_a_car_keyboard()
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == [
        "🚗 Да, указать марку и модель",
        "🙎‍♂️ Пока нужна помощь в выборе",
        "🔙 Назад",
    ]


def test_body_style_buttons_match_diagram():
    # Минивэн исключен из подбора осознанно
    assert LEXICON_FORM_BUTTONS_RU["body_style_buttons"] == [
        "🚙 Кроссовер/SUV",
        "🚗 Седан/Хэтчбек",
        "⚡Электромобиль",
        "Еще не решил/разные варианты",
    ]
    assert LEXICON_RU["choose_body_style_text"] == "Какой тип авто вам ближе?"


def test_assisted_results_keyboard_has_no_subscription():
    keyboard = create_assisted_results_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🚗 Изменить запрос", "change_request_assisted"),
        ("Подобрать еще", "else_car_button_assisted"),
        ("Оставить заявку на бесплатный подбор", "self_request_button"),
    ]


def test_assisted_results_keyboard_hides_else_car_when_exhausted():
    # Кнопка "Подобрать еще" не должна обещать вариантов, которых больше нет
    keyboard = create_assisted_results_keyboard(else_car=False)
    callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
    assert "else_car_button_assisted" not in callbacks


def test_budget_buttons_match_diagram():
    assert LEXICON_FORM_BUTTONS_RU["budget_buttons"] == [
        "до 12 000$",
        "12 000$ - 15 000$",
        "15 000$ - 20 000$",
        "20 000$ - 30 000$",
        "30 000$ - 50 000$",
        "50 000$ +",
    ]
    assert LEXICON_RU["choose_budget_text"] == "В какой бюджет планируете покупку?"


def test_gallery_mappings_cover_all_buttons():
    # Каждая кнопка типа/бюджета должна находить папку галереи (кроме "не решил")
    for body in LEXICON_FORM_BUTTONS_RU["body_style_buttons"]:
        if body != ANY_BODY_KEY:
            assert body in BODY_DIR, body
    for budget in LEXICON_FORM_BUTTONS_RU["budget_buttons"]:
        assert budget in BUDGET_DIR, budget


def test_page_follows_customer_priority(tmp_path):
    # Порядок задан нумерацией папок в Google Drive, а не случайной выборкой
    _make_gallery(
        tmp_path,
        {"sedan": {"0-12k": ["Honda Accord", "Toyota Camry", "Mazda 6", "Kia K5"]}},
    )

    picks, next_offset = get_gallery_page(
        "🚗 Седан/Хэтчбек", "до 12 000$", root=tmp_path
    )

    assert [p.display_title for p in picks] == [
        "Honda Accord",
        "Toyota Camry",
        "Mazda 6",
    ]
    assert next_offset == 3


def test_next_page_never_repeats_previous_cars(tmp_path):
    # "Подобрать еще" обязан показывать новые авто, а не те же самые
    _make_gallery(
        tmp_path,
        {"sedan": {"0-12k": ["Honda Accord", "Toyota Camry", "Mazda 6", "Kia K5"]}},
    )

    first, next_offset = get_gallery_page(
        "🚗 Седан/Хэтчбек", "до 12 000$", root=tmp_path
    )
    second, _ = get_gallery_page(
        "🚗 Седан/Хэтчбек", "до 12 000$", offset=next_offset, root=tmp_path
    )

    assert [p.display_title for p in second] == ["Kia K5"]
    assert not {p.car_folder for p in first} & {p.car_folder for p in second}


def test_page_is_empty_when_category_exhausted(tmp_path):
    _make_gallery(tmp_path, {"sedan": {"0-12k": ["Honda Accord"]}})

    picks, _ = get_gallery_page(
        "🚗 Седан/Хэтчбек", "до 12 000$", offset=1, root=tmp_path
    )

    assert picks == []


def test_any_body_alternates_categories(tmp_path):
    # Иначе первая страница "не определился" была бы из одних кроссоверов
    _make_gallery(
        tmp_path,
        {
            "sedan": {"0-12k": ["Honda Accord", "Toyota Camry"]},
            "suv": {"0-12k": ["Toyota RAV4", "Honda CR-V"]},
            "electric": {"0-12k": ["Nissan Leaf"]},
        },
    )

    picks, _ = get_gallery_page(ANY_BODY_KEY, "до 12 000$", root=tmp_path)

    assert {p.body_style_key for p in picks} == {
        "🚗 Седан/Хэтчбек",
        "🚙 Кроссовер/SUV",
        "⚡Электромобиль",
    }


def test_page_skips_car_folder_without_photos(tmp_path):
    _make_gallery(tmp_path, {"sedan": {"0-12k": ["Honda Accord", "Toyota Camry"]}})
    for photo in (tmp_path / "sedan" / "0-12k" / "002_toyota_camry").iterdir():
        photo.unlink()

    picks, next_offset = get_gallery_page(
        "🚗 Седан/Хэтчбек", "до 12 000$", root=tmp_path
    )

    assert [p.display_title for p in picks] == ["Honda Accord"]
    # Пропущенное авто уже просмотрено: иначе следующая страница вернулась бы к нему
    assert next_offset == 2


def test_page_returns_empty_for_unknown_keys(tmp_path):
    _make_gallery(tmp_path, {"sedan": {"0-12k": ["Honda Accord"]}})

    assert get_gallery_page("Фургон", "до 12 000$", root=tmp_path) == ([], 0)
    assert get_gallery_page("🚗 Седан/Хэтчбек", "миллион", root=tmp_path) == ([], 0)


def test_ag_lead_callback_roundtrip(tmp_path):
    # Название берется из манифеста как есть: ".title()" ломал "EQE" и "CR-V"
    _make_gallery(tmp_path, {"sedan": {"0-12k": ["Mercedes-Benz EQE"]}})
    pick = AssistedGalleryPick(
        car_folder="001_mercedes-benz_eqe",
        display_title="Mercedes-Benz EQE",
        image_paths=[],
        body_style_key="🚗 Седан/Хэтчбек",
        budget_key="до 12 000$",
    )
    callback_data = make_ag_lead_callback(pick)
    assert len(callback_data.encode("utf-8")) <= 64

    parsed = parse_ag_lead_callback(callback_data, root=tmp_path)
    assert parsed == (
        "001_mercedes-benz_eqe",
        "🚗 Седан/Хэтчбек",
        "до 12 000$",
        "Mercedes-Benz EQE",
    )
