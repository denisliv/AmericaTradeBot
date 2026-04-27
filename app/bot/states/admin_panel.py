from aiogram.fsm.state import State, StatesGroup


class FSMAdminPanel(StatesGroup):
    """Ввод цели для бана/разбана из reply-панели администратора."""

    waiting_ban_input = State()
    waiting_unban_input = State()
