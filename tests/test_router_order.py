"""Кнопка "Назад" обязана перехватываться раньше шагов подбора.

Хэндлеры шагов стоят на StateFilter и принимают ЛЮБОЙ callback в своём
состоянии: при неверном порядке роутеров бот принял бы "Назад" за выбранную
марку или тип кузова и ушёл бы вперёд вместо возврата.
"""

from app.bot.bot import ROUTERS
from app.bot.handlers.assisted_selection import assisted_selection_router
from app.bot.handlers.self_selection import self_selection_router
from app.bot.handlers.step_back import step_back_router


def test_step_back_is_connected_before_the_step_handlers():
    names = [router.name for router in ROUTERS]
    back = names.index(step_back_router.name)

    assert back < names.index(self_selection_router.name), names
    assert back < names.index(assisted_selection_router.name), names
