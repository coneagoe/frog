from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from monitor.monitor_target_service import (
    MonitorTargetService,
    TargetNotFoundError,
    TargetValidationError,
    format_monitor_target_label,
)


def _make_target(**overrides):
    data = {
        "id": 1,
        "stock_code": "600519",
        "market": "A",
        "condition": {"type": "price_threshold", "direction": "below", "value": 1500},
        "note": "茅台提醒",
        "frequency": "daily",
        "reset_mode": "auto",
        "enabled": True,
        "paused": False,
        "last_state": False,
        "triggered_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_add_target_rejects_invalid_json_condition():
    service = MonitorTargetService(storage=MagicMock())

    result = service.add_target(
        stock_code="600519",
        market="A",
        condition="not-json",
    )

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "condition" in result["message"]
    assert result["data"] is None


def test_add_target_validates_condition_business_rules():
    service = MonitorTargetService(storage=MagicMock())

    result = service.add_target(
        stock_code="600519",
        market="A",
        condition={"type": "ma_cross", "fast": 10, "slow": 5, "direction": "golden"},
    )

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "slow" in result["message"]


def test_add_target_returns_stable_payload_and_serialized_data():
    storage = MagicMock()
    storage.create_monitor_target.return_value = _make_target()
    service = MonitorTargetService(storage=storage)

    result = service.add_target(
        stock_code="600519",
        market="A",
        condition='{"type": "price_threshold", "direction": "below", "value": 1500}',
    )

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["stock_code"] == "600519"
    assert result["data"]["condition"]["type"] == "price_threshold"
    storage.create_monitor_target.assert_called_once()


def test_get_target_returns_not_found_result():
    storage = MagicMock()
    storage.get_monitor_target.return_value = None
    service = MonitorTargetService(storage=storage)

    result = service.get_target(999)

    assert result == {
        "success": False,
        "code": "NOT_FOUND",
        "message": "monitor target not found: 999",
        "data": None,
    }


def test_get_target_serializes_missing_paused_attribute_as_false():
    target = MagicMock()
    target.id = 1
    target.stock_code = "600519"
    target.market = "A"
    target.condition = {"type": "price_threshold", "direction": "below", "value": 1500}
    target.note = None
    target.frequency = "daily"
    target.reset_mode = "auto"
    target.enabled = True
    target.last_state = False
    target.triggered_at = None
    target.created_at = None
    storage = MagicMock()
    storage.get_monitor_target.return_value = target

    result = MonitorTargetService(storage=storage).get_target(1)

    assert result["success"] is True
    assert result["data"]["paused"] is False
    assert type(result["data"]["paused"]) is bool


def test_list_targets_returns_serialized_targets():
    storage = MagicMock()
    storage.list_monitor_targets.return_value = [
        _make_target(),
        _make_target(id=2, stock_code="000001"),
    ]
    service = MonitorTargetService(storage=storage)

    result = service.list_targets(frequency="daily", enabled=True)

    assert result["success"] is True
    assert result["code"] == "OK"
    assert [item["id"] for item in result["data"]] == [1, 2]
    storage.list_monitor_targets.assert_called_once_with(frequency="daily", enabled=True)


def test_new_method_aliases_are_wired_to_existing_behaviors():
    storage = MagicMock()
    storage.get_monitor_target.return_value = _make_target(id=1)
    storage.list_monitor_targets.return_value = [_make_target(id=1)]
    storage.update_monitor_target.return_value = _make_target(id=1, note="新备注")
    storage.delete_monitor_target.return_value = True
    service = MonitorTargetService(storage=storage)

    assert service.get(1)["success"] is True
    assert service.list()["success"] is True
    assert service.update(1, note="新备注")["success"] is True
    assert service.remove(1)["success"] is True


def test_get_status_returns_aggregate_counts():
    storage = MagicMock()
    storage.list_monitor_targets.return_value = [
        _make_target(id=1, enabled=True, last_state=True, frequency="daily"),
        _make_target(id=2, enabled=True, last_state=False, frequency="intraday"),
        _make_target(id=3, enabled=False, last_state=False, frequency="daily"),
    ]
    service = MonitorTargetService(storage=storage)

    result = service.get_status()

    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"] == {
        "total": 3,
        "enabled": 2,
        "disabled": 1,
        "triggered": 1,
        "daily": 2,
        "intraday": 1,
    }
    storage.list_monitor_targets.assert_called_once_with(frequency=None, enabled=None)


def test_update_target_returns_updated_data():
    storage = MagicMock()
    storage.update_monitor_target.return_value = _make_target(note="新备注")
    service = MonitorTargetService(storage=storage)

    result = service.update_target(1, note="新备注")

    assert result["success"] is True
    assert result["data"]["note"] == "新备注"
    storage.update_monitor_target.assert_called_once_with(1, note="新备注")


def test_remove_target_handles_not_found_and_success():
    storage = MagicMock()
    storage.delete_monitor_target.side_effect = [False, True]
    service = MonitorTargetService(storage=storage)

    missing = service.remove_target(99)
    removed = service.remove_target(1)

    assert missing["success"] is False
    assert missing["code"] == "NOT_FOUND"
    assert removed["success"] is True
    assert removed["data"] == {"id": 1, "deleted": True}


def test_set_target_status_validates_and_updates_enabled_flag():
    storage = MagicMock()
    storage.update_monitor_target.return_value = _make_target(enabled=False)
    service = MonitorTargetService(storage=storage)

    invalid = service.set_target_status(1, enabled="no")  # type: ignore[arg-type]
    valid = service.set_target_status(1, enabled=False)

    assert invalid["success"] is False
    assert invalid["code"] == "VALIDATION_ERROR"
    assert valid["success"] is True
    assert valid["data"]["enabled"] is False
    storage.update_monitor_target.assert_called_once_with(1, enabled=False)


def test_pause_delegates_to_workflow_storage_and_serializes_state():
    storage = MagicMock()
    storage.set_workflow_monitor_target_paused.return_value = _make_target(enabled=False, paused=True)

    result = MonitorTargetService(storage=storage).pause(1)

    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["message"] == "target paused"
    assert result["data"]["paused"] is True
    storage.set_workflow_monitor_target_paused.assert_called_once_with(1, paused=True)


def test_resume_returns_enabled_false_and_paused_false():
    storage = MagicMock()
    storage.set_workflow_monitor_target_paused.return_value = _make_target(enabled=False, paused=False)

    result = MonitorTargetService(storage=storage).resume(1)

    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["message"] == "target resumed"
    assert result["data"]["enabled"] is False
    assert result["data"]["paused"] is False
    storage.set_workflow_monitor_target_paused.assert_called_once_with(1, paused=False)


def test_pause_maps_workflow_storage_validation_failure():
    storage = MagicMock()
    storage.set_workflow_monitor_target_paused.side_effect = ValueError("workflow targets only")

    result = MonitorTargetService(storage=storage).pause(1)

    assert result == {
        "success": False,
        "code": "VALIDATION_ERROR",
        "message": "workflow targets only",
        "data": None,
    }


def test_resume_maps_missing_workflow_target_to_not_found():
    storage = MagicMock()
    storage.set_workflow_monitor_target_paused.return_value = None

    result = MonitorTargetService(storage=storage).resume(99)

    assert result == {
        "success": False,
        "code": "NOT_FOUND",
        "message": "monitor target not found: 99",
        "data": None,
    }


def test_target_id_true_is_rejected_as_validation_error():
    service = MonitorTargetService(storage=MagicMock())

    result = service.get_target(True)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "target_id" in result["message"]


def test_bool_numeric_condition_value_is_rejected():
    service = MonitorTargetService(storage=MagicMock())

    result = service.add_target(
        stock_code="600519",
        market="A",
        condition={"type": "price_threshold", "direction": "below", "value": True},
    )

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "condition.value" in result["message"]


def test_add_target_rejects_untyped_workflow_condition():
    result = MonitorTargetService(storage=MagicMock()).add_target(
        stock_code="600519", market="A", condition={"workflow": "forecast_ssf_ma20"}
    )

    assert result["code"] == "VALIDATION_ERROR"
    assert "condition.type" in result["message"]


def test_add_target_rejects_price_vs_ma_condition():
    storage = MagicMock()

    result = MonitorTargetService(storage=storage).add_target(
        stock_code="600519",
        market="A",
        condition={"type": "price_vs_ma", "direction": "above", "period": 20},
    )

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "condition.type" in result["message"]
    storage.create_monitor_target.assert_not_called()


def test_add_target_rejects_close_cross_ma_outside_a_share_daily_scope():
    storage = MagicMock()
    service = MonitorTargetService(storage=storage)
    condition = {"type": "close_cross_ma", "direction": "above", "period": 20}

    non_a = service.add_target(stock_code="600519", market="HK", condition=condition)
    intraday = service.add_target(stock_code="600519", market="A", condition=condition, frequency="intraday")

    assert non_a["code"] == "VALIDATION_ERROR"
    assert intraday["code"] == "VALIDATION_ERROR"
    storage.create_monitor_target.assert_not_called()


def test_update_target_rejects_close_cross_ma_scope_changes():
    storage = MagicMock()
    storage.get_monitor_target.return_value = _make_target(
        condition={"type": "close_cross_ma", "direction": "above", "period": 20}
    )
    service = MonitorTargetService(storage=storage)

    market_result = service.update_target(1, market="HK")
    frequency_result = service.update_target(1, frequency="intraday")

    assert market_result["code"] == "VALIDATION_ERROR"
    assert frequency_result["code"] == "VALIDATION_ERROR"
    storage.update_monitor_target.assert_not_called()


def test_empty_note_close_cross_ma_target_uses_final_close_label():
    assert (
        format_monitor_target_label(
            stock_code=None,
            stock_name=None,
            condition={"type": "close_cross_ma", "direction": "above", "period": 20},
            note="",
        )
        == "收盘价上穿20日均线"
    )


def test_custom_errors_are_exposed_for_validation_and_not_found_paths():
    assert issubclass(TargetValidationError, ValueError)
    assert issubclass(TargetNotFoundError, LookupError)


def test_service_uses_default_storage_when_not_provided():
    fake_storage = MagicMock()
    with patch("monitor.monitor_target_service.get_storage", return_value=fake_storage):
        service = MonitorTargetService()

    assert service.storage is fake_storage
