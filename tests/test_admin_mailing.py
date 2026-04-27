import pytest

from app.bot.handlers.admin_mailing import _mailing_payload_from_state
from app.infrastructure.services.admin_mailing_sender import AdminMailingSender


def test_mailing_payload_from_state_requires_chat_id():
    with pytest.raises(ValueError, match="chat_id"):
        _mailing_payload_from_state({"message_id": 10})


def test_mailing_payload_from_state_keeps_album_without_message_id():
    payload = _mailing_payload_from_state(
        {
            "chat_id": "123",
            "media_items": [{"type": "photo", "file_id": "abc"}],
            "is_album": True,
        }
    )

    assert payload["chat_id"] == 123
    assert payload["message_id"] is None
    assert payload["is_album"] is True


def test_build_media_list_rejects_unknown_media_type():
    with pytest.raises(ValueError, match="Unsupported media type"):
        AdminMailingSender._build_media_list(
            [{"type": "document", "file_id": "file-id"}]
        )
