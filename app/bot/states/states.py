from aiogram.fsm.state import State, StatesGroup


class FSMFillSelfSelectionForm(StatesGroup):
    get_brand = State()
    get_model = State()
    get_year = State()
    get_odometer = State()
    get_auction_status = State()


class FSMFillAssistedSelectionForm(StatesGroup):
    get_body_style = State()
    get_budget = State()


class FSMFillConsultationRequestForm(StatesGroup):
    get_name = State()
    get_phone = State()


class FSMFillPhoneForm(StatesGroup):
    get_phone = State()
