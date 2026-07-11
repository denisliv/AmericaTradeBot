"""Nurture chain schedule and content must match the Miro diagram."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.infrastructure.services.nurture import (
    FIRST_STEP_DELAY,
    STEP_OFFSET_DAYS,
    due_at,
    resolve_step,
)
from app.infrastructure.services.salesdata import BODY_STYLE_GROUPS
from app.lexicon.lexicon_ru import LEXICON_NURTURE_RU

_TZ = ZoneInfo("Europe/Minsk")
_START = datetime(2026, 7, 1, 9, 30, tzinfo=_TZ)


def test_step_offsets_are_daily():
    # После поста через 60 минут - по посту каждый день начиная от регистрации
    assert STEP_OFFSET_DAYS == {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}


def test_first_step_is_60_minutes_after_start():
    assert FIRST_STEP_DELAY == timedelta(minutes=60)
    assert due_at(_START, 0, 1, _TZ) == _START + timedelta(minutes=60)


def test_daily_steps_sent_at_noon():
    due = due_at(_START, 0, 2, _TZ)
    assert due == datetime(2026, 7, 2, 12, 0, tzinfo=_TZ)

    due = due_at(_START, 0, 8, _TZ)
    assert due == datetime(2026, 7, 8, 12, 0, tzinfo=_TZ)


def test_application_shifts_remaining_steps_by_three_days():
    without_shift = due_at(_START, 0, 3, _TZ)
    with_shift = due_at(_START, 3, 3, _TZ)
    assert with_shift - without_shift == timedelta(days=3)

    # Первый шаг тоже смещается
    assert due_at(_START, 3, 1, _TZ) == _START + timedelta(days=3, minutes=60)


def test_social_steps_repeat_monthly():
    # После шага 8 цепочка продолжается повторами шагов 6-8 каждые 30 дней
    assert resolve_step(8) == (9, 6)
    assert resolve_step(9) == (10, 7)
    assert resolve_step(10) == (11, 8)
    assert resolve_step(11) == (12, 6)
    assert resolve_step(14) == (15, 6)

    telegram_first = due_at(_START, 0, 6, _TZ)
    telegram_repeat_1 = due_at(_START, 0, 9, _TZ)
    telegram_repeat_2 = due_at(_START, 0, 12, _TZ)
    assert telegram_repeat_1 - telegram_first == timedelta(days=30)
    assert telegram_repeat_2 - telegram_repeat_1 == timedelta(days=30)


def test_base_steps_resolve_in_order():
    assert resolve_step(0) == (1, 1)
    assert resolve_step(1) == (2, 2)
    assert resolve_step(7) == (8, 8)


def test_nurture_texts_match_diagram_headers():
    assert LEXICON_NURTURE_RU["myths_text"].startswith(
        "<b>🤔  ТОП 3 мифа об авто из США</b>"
    )
    assert LEXICON_NURTURE_RU["client_story_text"].startswith(
        "<b>🙋 XXX за X $ - реальная история нашего клиента</b>"
    )
    assert LEXICON_NURTURE_RU["thinking_text"].startswith(
        "<b>🔥 Пока вы думаете - аукционы проходят каждый день</b>"
    )
    assert LEXICON_NURTURE_RU["telegram_text"].startswith(
        "<b>Присоединяйтесь к нашему Telegram каналу</b>"
    )
    assert LEXICON_NURTURE_RU["go_telegram_button"] == "Перейти в Telegram-канал"
    assert LEXICON_NURTURE_RU["go_instagram_button"] == "Перейти в Instagram"
    assert LEXICON_NURTURE_RU["go_tiktok_button"] == "Перейти в TikTok"


def test_body_style_groups_classify_csv_values():
    suv = BODY_STYLE_GROUPS["suv"]
    sedan = BODY_STYLE_GROUPS["sedan"]

    for style in ("SPORT UTILITY VEHICLE", "4DR SPORT UTILITY", "SUV", "4DR SPOR"):
        assert suv(style), style
        assert not sedan(style), style

    for style in ("SEDAN", "SEDAN 4DR", "SEDAN 4D"):
        assert sedan(style), style
        assert not suv(style), style

    for style in ("PICKUP", "WAGON", ""):
        assert not suv(style) and not sedan(style), style
