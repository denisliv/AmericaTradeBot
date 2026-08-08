"""Карточка подборки не должна приходить без фото и описания.

Заказчик прислал скриншот с двумя кнопками "✅ Пример № N" подряд и без единого
альбома над ними: результат отправки альбома не проверялся.
"""

import pytest

from app.bot.handlers import assisted_selection
from app.infrastructure.services.assisted_gallery import AssistedGalleryPick

BODY = "🚗 Седан/Хэтчбек"
BUDGET = "до 12 000$"


class FakeMessage:
    def __init__(self):
        self.sent = []

    async def answer(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))


class FakeUser:
    first_name = "Антон"


class FakeCallback:
    def __init__(self):
        self.message = FakeMessage()
        self.from_user = FakeUser()


class FakeState:
    def __init__(self, data=None):
        self._data = data or {}

    async def get_data(self):
        return dict(self._data)

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def set_state(self, state):
        self._data["_state"] = state


def _pick(name: str) -> AssistedGalleryPick:
    return AssistedGalleryPick(
        car_folder=f"001_{name}",
        display_title=name,
        image_paths=[],
        body_style_key=BODY,
        budget_key=BUDGET,
    )


@pytest.fixture
def gallery(monkeypatch):
    """Подменяет галерею и отправку альбомов; возвращает переключатель успеха."""
    state = {"page": [], "delivered": []}

    def fake_page(body_style, budget, *, offset=0, limit=3, root=None):
        page = state["page"][offset : offset + limit]
        return page, offset + len(page)

    async def fake_send(callback, media_group):
        return state["send_ok"]

    monkeypatch.setattr(assisted_selection, "get_gallery_page", fake_page)
    monkeypatch.setattr(
        assisted_selection, "safe_send_assisted_gallery_media_group", fake_send
    )
    monkeypatch.setattr(
        assisted_selection, "build_top_media_group", lambda name, pick: []
    )
    state["send_ok"] = True
    return state


@pytest.mark.asyncio
async def test_button_is_not_sent_when_the_album_fails(gallery):
    gallery["page"] = [_pick("porsche_taycan"), _pick("mercedes_eqe")]
    gallery["send_ok"] = False
    callback, state = FakeCallback(), FakeState({"gallery_offset": 0})

    await assisted_selection._send_top_picks(
        callback, state, body_style=BODY, budget=BUDGET
    )

    texts = [text for text, _ in callback.message.sent]
    assert not any("Нажмите кнопку" in text for text in texts)


@pytest.mark.asyncio
async def test_total_failure_explains_itself_and_offers_a_manager(gallery):
    gallery["page"] = [_pick("porsche_taycan")]
    gallery["send_ok"] = False
    callback, state = FakeCallback(), FakeState({"gallery_offset": 0})

    await assisted_selection._send_top_picks(
        callback, state, body_style=BODY, budget=BUDGET
    )

    texts = [text for text, _ in callback.message.sent]
    assert any("технической неполадки" in text for text in texts)


@pytest.mark.asyncio
async def test_rejected_card_does_not_come_back_on_the_next_page(gallery):
    # Битый файл Telegram отвергнет и во второй раз: если не сдвинуть смещение,
    # клиент будет получать одну и ту же сбойную карточку бесконечно
    gallery["page"] = [_pick("porsche_taycan"), _pick("mercedes_eqe")]
    gallery["send_ok"] = False
    callback, state = FakeCallback(), FakeState({"gallery_offset": 0})

    await assisted_selection._send_top_picks(
        callback, state, body_style=BODY, budget=BUDGET
    )

    assert (await state.get_data())["gallery_offset"] == 2


@pytest.mark.asyncio
async def test_successful_page_advances_the_offset(gallery):
    gallery["page"] = [_pick("porsche_taycan"), _pick("mercedes_eqe")]
    callback, state = FakeCallback(), FakeState({"gallery_offset": 0})

    await assisted_selection._send_top_picks(
        callback, state, body_style=BODY, budget=BUDGET
    )

    assert (await state.get_data())["gallery_offset"] == 2
    assert (await state.get_data())["gallery_shown"] == 2
    buttons = [
        markup.inline_keyboard[0][0].text
        for text, markup in callback.message.sent
        if "Нажмите кнопку" in text
    ]
    assert buttons == [
        "✅ Пример № 1: porsche_taycan",
        "✅ Пример № 2: mercedes_eqe",
    ]


@pytest.mark.asyncio
async def test_second_page_continues_the_numbering(gallery):
    gallery["page"] = [_pick("a"), _pick("b"), _pick("c"), _pick("d")]
    callback, state = FakeCallback(), FakeState(
        {"gallery_offset": 3, "gallery_shown": 3}
    )

    await assisted_selection._send_top_picks(
        callback, state, body_style=BODY, budget=BUDGET
    )

    buttons = [
        markup.inline_keyboard[0][0].text
        for text, markup in callback.message.sent
        if "Нажмите кнопку" in text
    ]
    assert buttons == ["✅ Пример № 4: d"]
