from aiogram.fsm.state import State, StatesGroup


class FSMAdminMailing(StatesGroup):
    get_message = State()
    get_button = State()
    get_button_text = State()
    get_button_url = State()
    get_button_message_text = State()
    confirm_send = State()
