"""Assisted selection branch must match the Miro diagram: type → budget → TOP picks."""

from pathlib import Path

from app.bot.keyboards.keyboards_inline import (
    create_assisted_results_keyboard,
    create_choice_keyboard,
)
from app.infrastructure.services.assisted_gallery import (
    ANY_BODY_KEY,
    BODY_DIR,
    BUDGET_DIR,
    AssistedGalleryPick,
    make_ag_lead_callback,
    parse_ag_lead_callback,
    pick_top_assisted_gallery,
)
from app.lexicon.lexicon_ru import LEXICON_FORM_BUTTONS_RU, LEXICON_RU


def _make_car(root: Path, body_slug: str, budget_slug: str, car: str, photos: int = 2):
    car_dir = root / body_slug / budget_slug / car
    car_dir.mkdir(parents=True, exist_ok=True)
    for i in range(photos):
        (car_dir / f"{i:02d}.jpg").write_bytes(b"jpg")


def test_choose_a_car_screen_matches_diagram():
    assert LEXICON_RU["choose_a_car_text"] == (
        "Вы уже определились, какой автомобиль хотите?"
    )
    keyboard = create_choice_keyboard("knowing_button", "advice_button", width=1)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == [
        "🚗 Да, указать марку и модель",
        "🙎‍♂️ Пока нужна помощь в выборе",
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


def test_pick_top_returns_distinct_cars(tmp_path):
    for car in ("honda_accord", "toyota_camry", "mazda_6", "kia_k5"):
        _make_car(tmp_path, "sedan", "0-12k", car)

    picks = pick_top_assisted_gallery("🚗 Седан/Хэтчбек", "до 12 000$", root=tmp_path)

    assert len(picks) == 3
    assert len({p.car_folder for p in picks}) == 3
    assert all(p.image_paths for p in picks)


def test_pick_top_any_body_mixes_categories(tmp_path):
    _make_car(tmp_path, "sedan", "0-12k", "honda_accord")
    _make_car(tmp_path, "suv", "0-12k", "toyota_rav4")
    _make_car(tmp_path, "electric", "0-12k", "nissan_leaf")

    picks = pick_top_assisted_gallery(ANY_BODY_KEY, "до 12 000$", root=tmp_path)

    assert len(picks) == 3
    assert {p.body_style_key for p in picks} == {
        "🚗 Седан/Хэтчбек",
        "🚙 Кроссовер/SUV",
        "⚡Электромобиль",
    }


def test_pick_top_skips_empty_car_folders(tmp_path):
    _make_car(tmp_path, "sedan", "0-12k", "honda_accord")
    (tmp_path / "sedan" / "0-12k" / "empty_car").mkdir(parents=True)

    picks = pick_top_assisted_gallery("🚗 Седан/Хэтчбек", "до 12 000$", root=tmp_path)

    assert [p.car_folder for p in picks] == ["honda_accord"]


def test_pick_top_returns_empty_for_unknown_keys(tmp_path):
    assert pick_top_assisted_gallery("Фургон", "до 12 000$", root=tmp_path) == []
    assert pick_top_assisted_gallery("🚗 Седан/Хэтчбек", "миллион", root=tmp_path) == []


def test_ag_lead_callback_roundtrip():
    pick = AssistedGalleryPick(
        car_folder="honda_accord",
        display_title="Honda Accord",
        image_paths=[],
        body_style_key="🚗 Седан/Хэтчбек",
        budget_key="до 12 000$",
    )
    callback_data = make_ag_lead_callback(pick)
    assert len(callback_data.encode("utf-8")) <= 64

    parsed = parse_ag_lead_callback(callback_data)
    assert parsed == ("honda_accord", "🚗 Седан/Хэтчбек", "до 12 000$", "Honda Accord")
