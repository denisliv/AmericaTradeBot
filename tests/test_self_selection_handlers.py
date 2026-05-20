import inspect

from app.bot.handlers.self_selection import flow as self_selection_flow


def test_self_selection_handlers_do_not_use_callback_conf():
    source = inspect.getsource(self_selection_flow)

    assert ".conf" not in source


def test_new_search_handler_accepts_injected_connection():
    signature = inspect.signature(self_selection_flow.process_new_search_button_press)

    assert "conn" in signature.parameters
