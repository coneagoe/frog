import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from monitor.shareholder_reduction_blackroom_sync import (
    ShareholderReductionBlackroomSyncService,
)


def _install_tushare_stub(monkeypatch, pro_api):
    ts_stub = SimpleNamespace(pro_api=pro_api)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)


def test_sync_dedupes_per_stock_skips_existing_and_adds_new(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holder_reduce.return_value = pd.DataFrame(
        [
            {"ts_code": "600519.SH", "ann_date": "20250101", "holder_name": "股东A"},
            {"ts_code": "600519.SH", "ann_date": "20250102", "holder_name": "股东B"},
            {"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"},
        ]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.check.side_effect = [
        {"success": True, "code": "OK", "message": "", "data": {"banned": True}},
        {"success": True, "code": "OK", "message": "", "data": {"banned": False}},
    ]
    blackroom_service.add.return_value = {
        "success": True,
        "code": "OK",
        "message": "record created",
        "data": {"id": 11},
    }

    service = ShareholderReductionBlackroomSyncService(
        blackroom_service=blackroom_service
    )

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["fetched"] == 3
    assert result["data"]["unique_stocks"] == 2
    assert result["data"]["added"] == 1
    assert result["data"]["skipped"] == 1
    assert len(result["data"]["records"]) == 1
    assert result["data"]["records"][0]["stock_code"] == "000001"
    assert result["data"]["records"][0]["market"] == "A"

    pro_client.stk_holder_reduce.assert_called_once_with(
        start_date="20250101", end_date="20250131"
    )
    blackroom_service.check.assert_any_call("600519", "A")
    blackroom_service.check.assert_any_call("000001", "A")
    blackroom_service.add.assert_called_once_with(
        stock_code="000001",
        market="A",
        ban_days=30,
        source="shareholder_reduction",
        note="股东减持公告 20250103 / 股东C",
    )


def test_sync_rejects_invalid_date_range():
    service = ShareholderReductionBlackroomSyncService(blackroom_service=MagicMock())

    result = service.sync(start_date="20250131", end_date="20250101", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "start_date" in result["message"]


def test_sync_rejects_invalid_date_format():
    service = ShareholderReductionBlackroomSyncService(blackroom_service=MagicMock())

    result = service.sync(start_date="2025-01-01", end_date="20250131", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "YYYYMMDD" in result["message"]


def test_sync_returns_success_with_zero_counts_when_tushare_empty(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holder_reduce.return_value = pd.DataFrame([])
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    service = ShareholderReductionBlackroomSyncService(
        blackroom_service=blackroom_service
    )

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result == {
        "success": True,
        "code": "OK",
        "message": "sync completed",
        "data": {
            "fetched": 0,
            "unique_stocks": 0,
            "added": 0,
            "skipped": 0,
            "records": [],
        },
    }
    blackroom_service.check.assert_not_called()
    blackroom_service.add.assert_not_called()


def test_sync_returns_storage_error_when_tushare_client_creation_fails(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    _install_tushare_stub(monkeypatch, MagicMock(side_effect=RuntimeError("boom")))
    service = ShareholderReductionBlackroomSyncService(blackroom_service=MagicMock())

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "boom" in result["message"]
