from unittest.mock import MagicMock

from monitor.blackroom_countdown import BlackroomCountdownService


def test_run_returns_stable_payload():
    storage = MagicMock()
    storage.countdown_blackroom_records.return_value = {"decremented": 12, "deleted": 3}

    result = BlackroomCountdownService(storage=storage).run()

    assert result == {
        "success": True,
        "code": "OK",
        "message": "countdown completed",
        "data": {"decremented": 12, "deleted": 3},
    }


def test_run_maps_storage_exception_to_storage_error():
    storage = MagicMock()
    storage.countdown_blackroom_records.side_effect = RuntimeError("db down")

    result = BlackroomCountdownService(storage=storage).run()

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "db down" in result["message"]
