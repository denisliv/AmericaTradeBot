import inspect

from app.bot.handlers import self_selection


def test_self_selection_handlers_do_not_use_callback_conf():
    source = inspect.getsource(self_selection)

    assert ".conf" not in source


def test_new_search_handler_accepts_injected_connection():
    signature = inspect.signature(self_selection.process_new_search_button_press)

    assert "conn" in signature.parameters
