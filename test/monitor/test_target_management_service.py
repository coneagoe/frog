from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from storage.storage_db import StorageDb


def _build_db_with_session(mock_session: MagicMock) -> StorageDb:
    db = StorageDb.__new__(StorageDb)
    db.Session = MagicMock(return_value=mock_session)
    db.engine = MagicMock()
    return db


def test_list_monitor_targets_filters_and_orders_results():
    mock_session = MagicMock()
    query = mock_session.query.return_value
    query.filter_by.return_value = query
    query.order_by.return_value = query
    target = SimpleNamespace(id=1, stock_code="600519")
    query.all.return_value = [target]

    db = _build_db_with_session(mock_session)
    results = db.list_monitor_targets(frequency="daily", enabled=True)

    assert results == [target]
    mock_session.query.assert_called_once()
    query.filter_by.assert_has_calls([call(enabled=True), call(frequency="daily")])
    query.order_by.assert_called_once()
    mock_session.close.assert_called_once()


def test_get_monitor_target_returns_item_by_id():
    mock_session = MagicMock()
    target = SimpleNamespace(id=7, stock_code="000001")
    mock_session.query.return_value.filter_by.return_value.first.return_value = target

    db = _build_db_with_session(mock_session)
    result = db.get_monitor_target(7)

    assert result == target
    mock_session.query.return_value.filter_by.assert_called_once_with(id=7)
    mock_session.close.assert_called_once()


def test_create_monitor_target_persists_and_returns_target():
    mock_session = MagicMock()
    db = _build_db_with_session(mock_session)

    result = db.create_monitor_target(
        stock_code="600519",
        market="A",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note="茅台提醒",
        frequency="daily",
        reset_mode="auto",
        enabled=True,
    )

    assert result.stock_code == "600519"
    assert result.market == "A"
    assert result.condition["type"] == "price_threshold"
    mock_session.add.assert_called_once_with(result)
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once_with(result)
    mock_session.close.assert_called_once()


def test_update_monitor_target_updates_and_returns_target():
    mock_session = MagicMock()
    existing = SimpleNamespace(id=1, note="旧备注", enabled=True)
    mock_session.query.return_value.filter_by.return_value.first.return_value = existing

    db = _build_db_with_session(mock_session)
    result = db.update_monitor_target(1, note="新备注", enabled=False)

    assert result is existing
    assert existing.note == "新备注"
    assert existing.enabled is False
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once_with(existing)
    mock_session.close.assert_called_once()


def test_update_monitor_target_returns_none_when_missing():
    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    db = _build_db_with_session(mock_session)
    result = db.update_monitor_target(999, note="不会更新")

    assert result is None
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


def test_update_monitor_target_rejects_invalid_fields():
    mock_session = MagicMock()
    db = _build_db_with_session(mock_session)

    with pytest.raises(ValueError, match="不支持更新字段"):
        db.update_monitor_target(1, not_allowed="x")

    db.Session.assert_not_called()


def test_delete_monitor_target_deletes_when_found():
    mock_session = MagicMock()
    target = SimpleNamespace(id=1)
    mock_session.query.return_value.filter_by.return_value.first.return_value = target

    db = _build_db_with_session(mock_session)
    result = db.delete_monitor_target(1)

    assert result is True
    mock_session.delete.assert_called_once_with(target)
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_delete_monitor_target_returns_false_when_missing():
    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None

    db = _build_db_with_session(mock_session)
    result = db.delete_monitor_target(123)

    assert result is False
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()
