from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from monitor.blackroom_management_service import BlackroomManagementService
from monitor.blackroom_service import BlackroomService


def _record(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = {
        "id": 1,
        "stock_code": "600519",
        "market": "A",
        "ban_days": 30,
        "remaining_days": 30,
        "start_at": now,
        "expire_at": now + timedelta(days=30),
        "source": "manual",
        "note": "note",
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_ban_creates_record_with_remaining_days():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _record()
    service = BlackroomService(storage=storage)

    result = service.ban("600519", "A", 30, note="note")

    assert result["success"] is True
    assert result["data"]["remaining_days"] == 30
    _, kwargs = storage.create_blackroom_record.call_args
    assert kwargs["ban_days"] == 30
    assert kwargs["remaining_days"] == 30


def test_unban_deletes_by_record_id():
    storage = MagicMock()
    storage.delete_blackroom_record.return_value = True

    result = BlackroomService(storage=storage).unban(7)

    assert result == {
        "success": True,
        "code": "OK",
        "message": "record unbanned",
        "data": {"id": 7, "deleted": True},
    }


def test_unban_stock_deletes_by_stock_and_market():
    storage = MagicMock()
    storage.delete_blackroom_records_by_stock.return_value = 2

    result = BlackroomService(storage=storage).unban_stock("600519", "A")

    assert result["success"] is True
    assert result["data"] == {"stock_code": "600519", "market": "A", "deleted": 2}


def test_is_banned_uses_active_records():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="600519")]

    result = BlackroomService(storage=storage).is_banned("600519", "A")

    assert result["data"]["banned"] is True


def test_filter_buy_candidates_splits_allowed_and_banned():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="600519")]

    result = BlackroomService(storage=storage).filter_buy_candidates(
        ["600519", "000001"], "A"
    )

    assert result["data"] == {"allowed": ["000001"], "banned": ["600519"]}


def test_list_active_only_uses_active_storage_query():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="600519")]

    result = BlackroomService(storage=storage).list(active_only=True, market="A")

    assert result["success"] is True
    assert result["data"][0]["stock_code"] == "600519"
    storage.list_active_blackroom_records.assert_called_once_with(market="A")
    storage.list_blackroom_records.assert_not_called()


def test_compatibility_class_still_exposes_old_add_name():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _record()
    service = BlackroomManagementService(storage=storage)

    result = service.add_record("600519", "A", 30)

    assert result["success"] is True
