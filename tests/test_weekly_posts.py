"""Еженедельные посты: лимит подписи к фото и наличие картинок."""

import pytest

from app.infrastructure.paths import WEEKLY_POSTS_IMG_DIR
from app.infrastructure.services.daily_posts_broadcast import list_post_files


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _post_files():
    files = list_post_files()
    if not files:
        pytest.skip("data/posts пуст (runtime-данные не в git)")
    return files


def test_post_texts_fit_photo_caption_limit():
    # Пост уходит подписью к фото: лимит Telegram 1024 UTF-16 единицы
    for path in _post_files():
        text = path.read_text(encoding="utf-8").strip()
        assert _utf16_units(text) <= 1024, f"{path.name} длиннее лимита подписи"
        assert text, f"{path.name} пуст"


def test_every_post_has_matching_image():
    for path in _post_files():
        image = WEEKLY_POSTS_IMG_DIR / f"{path.stem}.png"
        assert image.exists(), f"нет картинки для {path.name}"
