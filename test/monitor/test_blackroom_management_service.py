from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from monitor.blackroom_management_service import (
    BlackroomManagementService,
    BlackroomNotFoundError,
    BlackroomValidationError,
)


def _make_record(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = {
        "id": 1,
        "stock_code": "600519",
        "market": "A",
        "ban_days": 30,
        "start_at": now,
        "expire_at": now + timedelta(days=30),
        "source": "manual",
        "note": "减持预警",
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


# ---------------------------------------------------------------------------
# Error type contracts
# ---------------------------------------------------------------------------


def test_custom_errors_are_exposed_for_validation_and_not_found_paths():
    assert issubclass(BlackroomValidationError, ValueError)
    assert issubclass(BlackroomNotFoundError, LookupError)


# ---------------------------------------------------------------------------
# add_record
# ---------------------------------------------------------------------------


def test_add_record_returns_stable_payload_and_serialized_data():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record()
    service = BlackroomManagementService(storage=storage)

    result = service.add_record(stock_code="600519", market="A", ban_days=30)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["stock_code"] == "600519"
    assert result["data"]["market"] == "A"
    storage.create_blackroom_record.assert_called_once()


def test_add_record_rejects_invalid_market():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.add_record(stock_code="600519", market="US", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "market" in result["message"]
    assert result["data"] is None


def test_add_record_rejects_invalid_source():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.add_record(stock_code="600519", market="A", ban_days=30, source="unknown_source")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "source" in result["message"]


def test_add_record_rejects_non_positive_ban_days():
    service = BlackroomManagementService(storage=MagicMock())

    result_zero = service.add_record(stock_code="600519", market="A", ban_days=0)
    result_neg = service.add_record(stock_code="600519", market="A", ban_days=-5)

    assert result_zero["success"] is False
    assert result_zero["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result_zero["message"]
    assert result_neg["success"] is False
    assert result_neg["code"] == "VALIDATION_ERROR"


def test_add_record_rejects_empty_stock_code():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.add_record(stock_code="  ", market="A", ban_days=10)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "stock_code" in result["message"]


def test_add_record_defaults_source_to_manual():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record(source="manual")
    service = BlackroomManagementService(storage=storage)

    service.add_record(stock_code="600519", market="A", ban_days=10)

    _, kwargs = storage.create_blackroom_record.call_args
    assert kwargs.get("source", "manual") == "manual"


def test_add_record_passes_start_at_to_storage():
    storage = MagicMock()
    fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    storage.create_blackroom_record.return_value = _make_record(start_at=fixed)
    service = BlackroomManagementService(storage=storage)

    service.add_record(stock_code="600519", market="A", ban_days=10, start_at=fixed)

    _, kwargs = storage.create_blackroom_record.call_args
    assert kwargs.get("start_at") == fixed


def test_add_record_uses_current_time_as_default_start_at():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record()
    service = BlackroomManagementService(storage=storage)

    before = datetime.now(timezone.utc)
    service.add_record(stock_code="600519", market="A", ban_days=10)
    after = datetime.now(timezone.utc)

    _, kwargs = storage.create_blackroom_record.call_args
    start = kwargs.get("start_at")
    assert start is not None
    assert before <= start <= after


def test_add_record_serializes_datetimes_to_iso():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record()
    service = BlackroomManagementService(storage=storage)

    result = service.add_record(stock_code="600519", market="A", ban_days=30)

    assert isinstance(result["data"]["start_at"], str)
    assert isinstance(result["data"]["expire_at"], str)
    assert isinstance(result["data"]["created_at"], str)


def test_add_record_accepts_hk_and_etf_markets():
    for market in ("HK", "ETF"):
        storage = MagicMock()
        storage.create_blackroom_record.return_value = _make_record(market=market)
        service = BlackroomManagementService(storage=storage)

        result = service.add_record(stock_code="00700", market=market, ban_days=7)

        assert result["success"] is True, f"Expected success for market={market}"


def test_add_record_accepts_shareholder_selling_source():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record(source="shareholder_selling")
    service = BlackroomManagementService(storage=storage)

    result = service.add_record(stock_code="600519", market="A", ban_days=90, source="shareholder_selling")

    assert result["success"] is True


def test_add_record_rejects_non_datetime_start_at():
    service = BlackroomManagementService(storage=MagicMock())

    for bad in ("2026-01-01", 20260101, 0):
        result = service.add_record(
            stock_code="600519",
            market="A",
            ban_days=10,
            start_at=bad,  # type: ignore[arg-type]
        )
        assert result["success"] is False, f"Expected failure for start_at={bad!r}"
        assert result["code"] == "VALIDATION_ERROR"
        assert "start_at" in result["message"]


# ---------------------------------------------------------------------------
# get_record
# ---------------------------------------------------------------------------


def test_get_record_returns_not_found_result():
    storage = MagicMock()
    storage.get_blackroom_record.return_value = None
    service = BlackroomManagementService(storage=storage)

    result = service.get_record(999)

    assert result == {
        "success": False,
        "code": "NOT_FOUND",
        "message": "blackroom record not found: 999",
        "data": None,
    }


def test_get_record_returns_serialized_record():
    storage = MagicMock()
    storage.get_blackroom_record.return_value = _make_record(id=5)
    service = BlackroomManagementService(storage=storage)

    result = service.get_record(5)

    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["id"] == 5
    storage.get_blackroom_record.assert_called_once_with(5)


def test_get_record_rejects_invalid_id():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.get_record(True)  # bool is a subtype of int; runtime validator rejects it

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "record_id" in result["message"]


# ---------------------------------------------------------------------------
# list_records
# ---------------------------------------------------------------------------


def test_list_records_returns_serialized_list():
    storage = MagicMock()
    storage.list_blackroom_records.return_value = [
        _make_record(id=1, stock_code="600519"),
        _make_record(id=2, stock_code="000001"),
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.list_records(market="A", enabled=True)

    assert result["success"] is True
    assert result["code"] == "OK"
    assert [item["id"] for item in result["data"]] == [1, 2]
    storage.list_blackroom_records.assert_called_once_with(market="A", enabled=True)


def test_list_records_validates_market_filter():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.list_records(market="INVALID")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "market" in result["message"]


# ---------------------------------------------------------------------------
# update_record
# ---------------------------------------------------------------------------


def test_update_record_returns_updated_data():
    storage = MagicMock()
    storage.update_blackroom_record.return_value = _make_record(note="新备注")
    service = BlackroomManagementService(storage=storage)

    result = service.update_record(1, note="新备注")

    assert result["success"] is True
    assert result["data"]["note"] == "新备注"
    storage.update_blackroom_record.assert_called_once_with(1, note="新备注")


def test_update_record_returns_not_found():
    storage = MagicMock()
    storage.update_blackroom_record.return_value = None
    service = BlackroomManagementService(storage=storage)

    result = service.update_record(999, note="x")

    assert result["success"] is False
    assert result["code"] == "NOT_FOUND"
    assert "999" in result["message"]


def test_update_record_rejects_unsupported_fields():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update_record(1, ghost_field="bad")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ghost_field" in result["message"]


def test_update_record_requires_at_least_one_field():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update_record(1)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"


def test_update_record_validates_market_when_present():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update_record(1, market="INVALID")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "market" in result["message"]


def test_update_record_validates_ban_days_when_present():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update_record(1, ban_days=-1)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result["message"]


def test_update_record_rejects_non_datetime_start_at():
    service = BlackroomManagementService(storage=MagicMock())

    for bad in ("2026-01-01", 20260101, 0):
        result = service.update_record(1, start_at=bad)  # runtime rejects non-datetime
        assert result["success"] is False, f"Expected failure for start_at={bad!r}"
        assert result["code"] == "VALIDATION_ERROR"
        assert "start_at" in result["message"]


def test_update_record_rejects_non_datetime_expire_at():
    service = BlackroomManagementService(storage=MagicMock())

    for bad in ("2026-12-31", 99999, 0.5):
        result = service.update_record(1, expire_at=bad)  # runtime rejects non-datetime
        assert result["success"] is False, f"Expected failure for expire_at={bad!r}"
        assert result["code"] == "VALIDATION_ERROR"
        assert "expire_at" in result["message"]


def test_update_record_accepts_none_start_at_and_expire_at():
    storage = MagicMock()
    storage.update_blackroom_record.return_value = _make_record(start_at=None, expire_at=None)
    service = BlackroomManagementService(storage=storage)

    result = service.update_record(1, start_at=None, expire_at=None)

    assert result["success"] is True


def test_update_record_accepts_valid_datetime_start_at_and_expire_at():
    fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    storage = MagicMock()
    storage.update_blackroom_record.return_value = _make_record(start_at=fixed, expire_at=fixed)
    service = BlackroomManagementService(storage=storage)

    result = service.update_record(1, start_at=fixed, expire_at=fixed)

    assert result["success"] is True


# ---------------------------------------------------------------------------
# remove_record
# ---------------------------------------------------------------------------


def test_remove_record_success():
    storage = MagicMock()
    storage.delete_blackroom_record.return_value = True
    service = BlackroomManagementService(storage=storage)

    result = service.remove_record(1)

    assert result["success"] is True
    assert result["data"] == {"id": 1, "deleted": True}


def test_remove_record_not_found():
    storage = MagicMock()
    storage.delete_blackroom_record.return_value = False
    service = BlackroomManagementService(storage=storage)

    result = service.remove_record(99)

    assert result["success"] is False
    assert result["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# filter_buy_candidates
# ---------------------------------------------------------------------------


def test_filter_buy_candidates_removes_banned_stocks():
    now = datetime.now(timezone.utc)
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [
        _make_record(stock_code="600519", market="A", expire_at=now + timedelta(days=5)),
        _make_record(
            id=2,
            stock_code="000001",
            market="A",
            expire_at=now + timedelta(days=1),
        ),
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.filter_buy_candidates(candidates=["600519", "600036", "000001"], market="A")

    assert result["success"] is True
    assert result["data"]["allowed"] == ["600036"]
    assert set(result["data"]["banned"]) == {"600519", "000001"}
    storage.list_active_blackroom_records.assert_called_once_with(market="A")


def test_filter_buy_candidates_returns_all_when_no_active_ban():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = []
    service = BlackroomManagementService(storage=storage)

    result = service.filter_buy_candidates(candidates=["600519", "600036"], market="A")

    assert result["success"] is True
    assert result["data"]["allowed"] == ["600519", "600036"]
    assert result["data"]["banned"] == []


def test_filter_buy_candidates_validates_market():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.filter_buy_candidates(candidates=["600519"], market="INVALID")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "market" in result["message"]


def test_filter_buy_candidates_requires_list_of_candidates():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.filter_buy_candidates(candidates="600519", market="A")  # type: ignore[arg-type]

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# is_buy_banned
# ---------------------------------------------------------------------------


def test_is_buy_banned_returns_true_for_active_ban():
    now = datetime.now(timezone.utc)
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [
        _make_record(stock_code="600519", market="A", expire_at=now + timedelta(days=1))
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.is_buy_banned(stock_code="600519", market="A")

    assert result["success"] is True
    assert result["data"]["banned"] is True
    assert result["data"]["stock_code"] == "600519"
    assert result["data"]["market"] == "A"


def test_is_buy_banned_returns_false_when_not_banned():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = []
    service = BlackroomManagementService(storage=storage)

    result = service.is_buy_banned(stock_code="600519", market="A")

    assert result["success"] is True
    assert result["data"]["banned"] is False


def test_is_buy_banned_validates_market():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.is_buy_banned(stock_code="600519", market="BAD")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "market" in result["message"]


def test_is_buy_banned_validates_stock_code():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.is_buy_banned(stock_code="  ", market="A")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "stock_code" in result["message"]


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


def test_get_status_returns_aggregate_counts():
    now = datetime.now(timezone.utc)
    storage = MagicMock()
    storage.list_blackroom_records.return_value = [
        _make_record(id=1, market="A", enabled=True, expire_at=now + timedelta(days=5)),
        _make_record(id=2, market="HK", enabled=True, expire_at=now - timedelta(days=1)),
        _make_record(id=3, market="A", enabled=False, expire_at=now + timedelta(days=2)),
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.get_status()

    assert result["success"] is True
    assert result["code"] == "OK"
    data = result["data"]
    assert data["total"] == 3
    assert data["enabled"] == 2
    assert data["disabled"] == 1
    storage.list_blackroom_records.assert_called_once_with(market=None, enabled=None)


# ---------------------------------------------------------------------------
# Default storage injection
# ---------------------------------------------------------------------------


def test_service_uses_default_storage_when_not_provided():
    fake_storage = MagicMock()
    with patch("monitor.blackroom_management_service.get_storage", return_value=fake_storage):
        service = BlackroomManagementService()

    assert service.storage is fake_storage


# ---------------------------------------------------------------------------
# Public short aliases
# ---------------------------------------------------------------------------


def test_alias_add_delegates_to_add_record():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _make_record()
    service = BlackroomManagementService(storage=storage)

    result = service.add(stock_code="600519", market="A", ban_days=30)

    assert result["success"] is True
    assert result["code"] == "OK"
    storage.create_blackroom_record.assert_called_once()


def test_alias_get_delegates_to_get_record():
    storage = MagicMock()
    storage.get_blackroom_record.return_value = _make_record(id=7)
    service = BlackroomManagementService(storage=storage)

    result = service.get(7)

    assert result["success"] is True
    assert result["data"]["id"] == 7
    storage.get_blackroom_record.assert_called_once_with(7)


def test_alias_list_delegates_to_list_records():
    storage = MagicMock()
    storage.list_blackroom_records.return_value = [_make_record(id=1)]
    service = BlackroomManagementService(storage=storage)

    result = service.list(market="A", enabled=True)

    assert result["success"] is True
    assert len(result["data"]) == 1
    storage.list_blackroom_records.assert_called_once_with(market="A", enabled=True)


def test_alias_update_delegates_to_update_record():
    storage = MagicMock()
    storage.update_blackroom_record.return_value = _make_record(note="aliased")
    service = BlackroomManagementService(storage=storage)

    result = service.update(1, note="aliased")

    assert result["success"] is True
    assert result["data"]["note"] == "aliased"
    storage.update_blackroom_record.assert_called_once_with(1, note="aliased")


def test_alias_remove_delegates_to_remove_record():
    storage = MagicMock()
    storage.delete_blackroom_record.return_value = True
    service = BlackroomManagementService(storage=storage)

    result = service.remove(3)

    assert result["success"] is True
    assert result["data"] == {"id": 3, "deleted": True}
    storage.delete_blackroom_record.assert_called_once_with(3)


def test_alias_filter_delegates_to_filter_buy_candidates():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_make_record(stock_code="600519")]
    service = BlackroomManagementService(storage=storage)

    result = service.filter(candidates=["600519", "600036"], market="A")

    assert result["success"] is True
    assert result["data"]["allowed"] == ["600036"]
    assert result["data"]["banned"] == ["600519"]
    storage.list_active_blackroom_records.assert_called_once_with(market="A")


# ---------------------------------------------------------------------------
# filter_buy_candidates – element type validation
# ---------------------------------------------------------------------------


def test_filter_buy_candidates_rejects_non_string_elements():
    service = BlackroomManagementService(storage=MagicMock())

    for bad_candidates in (
        [123, "600519"],
        [None, "600519"],
        [["600519"]],
        [True],
    ):
        result = service.filter_buy_candidates(candidates=bad_candidates, market="A")  # type: ignore[arg-type]
        assert result["success"] is False, f"Expected failure for candidates={bad_candidates!r}"
        assert result["code"] == "VALIDATION_ERROR"


def test_filter_buy_candidates_accepts_all_string_elements():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = []
    service = BlackroomManagementService(storage=storage)

    result = service.filter_buy_candidates(candidates=["600519", "000001"], market="A")

    assert result["success"] is True
    assert result["data"]["allowed"] == ["600519", "000001"]


def test_filter_buy_candidates_accepts_empty_list():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = []
    service = BlackroomManagementService(storage=storage)

    result = service.filter_buy_candidates(candidates=[], market="A")

    assert result["success"] is True
    assert result["data"]["allowed"] == []
    assert result["data"]["banned"] == []


# ---------------------------------------------------------------------------
# Regression: ban_days=None must be rejected (issue 1)
# ---------------------------------------------------------------------------


def test_add_record_rejects_none_ban_days():
    """ban_days must be a positive integer; None must not create records that never expire."""
    service = BlackroomManagementService(storage=MagicMock())

    result = service.add_record(stock_code="600519", market="A", ban_days=None)  # type: ignore[arg-type]

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result["message"]


def test_add_alias_rejects_none_ban_days():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.add(stock_code="600519", market="A", ban_days=None)  # type: ignore[arg-type]

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result["message"]


def test_update_record_rejects_none_ban_days():
    """Explicitly setting ban_days=None in an update must be rejected."""
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update_record(1, ban_days=None)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result["message"]


def test_update_alias_rejects_none_ban_days():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.update(1, ban_days=None)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ban_days" in result["message"]


# ---------------------------------------------------------------------------
# Regression: get_status must return stable payload on storage error (issue 2)
# ---------------------------------------------------------------------------


def test_get_status_returns_error_payload_when_storage_raises():
    """Storage exceptions must not propagate; a stable error dict must be returned."""
    storage = MagicMock()
    storage.list_blackroom_records.side_effect = RuntimeError("DB connection lost")
    service = BlackroomManagementService(storage=storage)

    result = service.get_status()

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "DB connection lost" in result["message"]
    assert result["data"] is None


def test_get_status_error_payload_does_not_raise():
    """get_status must never raise, regardless of the underlying exception type."""
    for exc_cls in (Exception, ValueError, OSError, KeyError):
        storage = MagicMock()
        storage.list_blackroom_records.side_effect = exc_cls("boom")
        service = BlackroomManagementService(storage=storage)

        result = service.get_status()  # must not raise

        assert result["success"] is False, f"Expected failure for exc_cls={exc_cls}"
        assert result["code"] == "STORAGE_ERROR"


# ---------------------------------------------------------------------------
# Regression: storage failures must return stable payload (not leak exceptions)
# ---------------------------------------------------------------------------


def test_add_record_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.create_blackroom_record.side_effect = RuntimeError("DB unavailable")
    service = BlackroomManagementService(storage=storage)

    result = service.add_record(stock_code="600519", market="A", ban_days=30)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "DB unavailable" in result["message"]
    assert result["data"] is None


def test_get_record_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.get_blackroom_record.side_effect = OSError("connection reset")
    service = BlackroomManagementService(storage=storage)

    result = service.get_record(1)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


def test_list_records_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.list_blackroom_records.side_effect = RuntimeError("timeout")
    service = BlackroomManagementService(storage=storage)

    result = service.list_records()

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


def test_update_record_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.update_blackroom_record.side_effect = RuntimeError("write failed")
    service = BlackroomManagementService(storage=storage)

    result = service.update_record(1, note="x")

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


def test_remove_record_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.delete_blackroom_record.side_effect = RuntimeError("lock timeout")
    service = BlackroomManagementService(storage=storage)

    result = service.remove_record(1)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


def test_filter_buy_candidates_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.list_active_blackroom_records.side_effect = RuntimeError("index error")
    service = BlackroomManagementService(storage=storage)

    result = service.filter_buy_candidates(candidates=["600519"], market="A")

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


def test_is_buy_banned_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.list_active_blackroom_records.side_effect = ConnectionError("lost")
    service = BlackroomManagementService(storage=storage)

    result = service.is_buy_banned(stock_code="600519", market="A")

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert result["data"] is None


# ---------------------------------------------------------------------------
# check() alias for is_buy_banned()
# ---------------------------------------------------------------------------


def test_check_alias_delegates_to_is_buy_banned_banned():
    now = datetime.now(timezone.utc)
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [
        _make_record(stock_code="600519", market="A", expire_at=now + timedelta(days=1))
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.check(stock_code="600519", market="A")

    assert result["success"] is True
    assert result["data"]["banned"] is True
    storage.list_active_blackroom_records.assert_called_once_with(market="A")


def test_check_alias_delegates_to_is_buy_banned_not_banned():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = []
    service = BlackroomManagementService(storage=storage)

    result = service.check(stock_code="000001", market="A")

    assert result["success"] is True
    assert result["data"]["banned"] is False


def test_check_alias_returns_validation_error_on_bad_market():
    service = BlackroomManagementService(storage=MagicMock())

    result = service.check(stock_code="600519", market="INVALID")

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"


def test_check_alias_returns_storage_error_on_storage_failure():
    storage = MagicMock()
    storage.list_active_blackroom_records.side_effect = RuntimeError("down")
    service = BlackroomManagementService(storage=storage)

    result = service.check(stock_code="600519", market="A")

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"


# ---------------------------------------------------------------------------
# status() alias for get_status()
# ---------------------------------------------------------------------------


def test_status_alias_delegates_to_get_status():
    now = datetime.now(timezone.utc)
    storage = MagicMock()
    storage.list_blackroom_records.return_value = [
        _make_record(id=1, enabled=True, expire_at=now + timedelta(days=1)),
        _make_record(id=2, enabled=False, expire_at=now + timedelta(days=1)),
    ]
    service = BlackroomManagementService(storage=storage)

    result = service.status()

    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["total"] == 2
    assert result["data"]["enabled"] == 1
    assert result["data"]["disabled"] == 1
    storage.list_blackroom_records.assert_called_once_with(market=None, enabled=None)


def test_status_alias_returns_storage_error_on_failure():
    storage = MagicMock()
    storage.list_blackroom_records.side_effect = RuntimeError("DB gone")
    service = BlackroomManagementService(storage=storage)

    result = service.status()

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "DB gone" in result["message"]


# ---------------------------------------------------------------------------
# ban_days is required in add/add_record (no default)
# ---------------------------------------------------------------------------


def test_add_record_ban_days_is_required_parameter():
    """ban_days has no default – omitting it must raise TypeError at call time."""
    import inspect

    sig = inspect.signature(BlackroomManagementService.add_record)
    param = sig.parameters["ban_days"]
    assert param.default is inspect.Parameter.empty, (
        "ban_days must be a required parameter with no default in add_record"
    )


def test_add_alias_ban_days_is_required_parameter():
    import inspect

    sig = inspect.signature(BlackroomManagementService.add)
    param = sig.parameters["ban_days"]
    assert param.default is inspect.Parameter.empty, "ban_days must be a required parameter with no default in add"
