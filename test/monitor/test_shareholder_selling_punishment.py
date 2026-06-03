import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import monitor.shareholder_selling_punishment as punishment_module

from monitor.shareholder_selling_punishment import (
    ShareholderSellingPunishmentService,
)


def test_only_new_sync_service_name_is_exported():
    bsvc = MagicMock()
    old_name = "ShareholderSelling" + "BlackroomSyncService"

    service = ShareholderSellingPunishmentService(blackroom_service=bsvc)

    assert service.blackroom_service is bsvc
    assert not hasattr(punishment_module, old_name)


def _install_tushare_stub(monkeypatch, pro_api):
    ts_stub = SimpleNamespace(pro_api=pro_api)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)


def test_sync_dedupes_per_stock_skips_existing_and_adds_new(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock(spec_set=["stk_holdertrade"])
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [
            {"ts_code": "600519.SH", "ann_date": "20250101", "holder_name": "股东A"},
            {"ts_code": "600519.SH", "ann_date": "20250102", "holder_name": "股东B"},
            {"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"},
        ]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.is_banned.side_effect = [
        {"success": True, "code": "OK", "message": "", "data": {"banned": True}},
        {"success": True, "code": "OK", "message": "", "data": {"banned": False}},
    ]
    blackroom_service.ban.return_value = {
        "success": True,
        "code": "OK",
        "message": "record created",
        "data": {"id": 11},
    }

    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

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

    pro_client.stk_holdertrade.assert_called_once_with(
        start_date="20250101", end_date="20250131", in_de="DE"
    )
    blackroom_service.is_banned.assert_any_call("600519", "A")
    blackroom_service.is_banned.assert_any_call("000001", "A")
    blackroom_service.ban.assert_called_once_with(
        stock_code="000001",
        market="A",
        ban_days=30,
        source="shareholder_selling",
        note="股东减持公告 20250103 / 股东C",
    )


def test_sync_rejects_invalid_date_range():
    service = ShareholderSellingPunishmentService(blackroom_service=MagicMock())

    result = service.sync(start_date="20250131", end_date="20250101", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "start_date" in result["message"]


def test_sync_rejects_invalid_date_format():
    service = ShareholderSellingPunishmentService(blackroom_service=MagicMock())

    result = service.sync(start_date="2025-01-01", end_date="20250131", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "YYYYMMDD" in result["message"]


def test_sync_returns_success_with_zero_counts_when_tushare_empty(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holdertrade.return_value = pd.DataFrame([])
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

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
    blackroom_service.is_banned.assert_not_called()
    blackroom_service.ban.assert_not_called()


def test_sync_returns_storage_error_when_tushare_client_creation_fails(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    _install_tushare_stub(monkeypatch, MagicMock(side_effect=RuntimeError("boom")))
    service = ShareholderSellingPunishmentService(blackroom_service=MagicMock())

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "boom" in result["message"]


def test_sync_stops_and_propagates_when_check_fails(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [{"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"}]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.is_banned.return_value = {
        "success": False,
        "code": "BLACKROOM_CHECK_FAILED",
        "message": "check failed",
        "data": None,
    }
    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result == {
        "success": False,
        "code": "BLACKROOM_CHECK_FAILED",
        "message": "check failed",
        "data": None,
    }
    blackroom_service.is_banned.assert_called_once_with("000001", "A")
    blackroom_service.ban.assert_not_called()


def test_sync_stops_and_propagates_when_add_fails(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [{"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"}]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.is_banned.return_value = {
        "success": True,
        "code": "OK",
        "message": "",
        "data": {"banned": False},
    }
    blackroom_service.ban.return_value = {
        "success": False,
        "code": "BLACKROOM_ADD_FAILED",
        "message": "add failed",
        "data": None,
    }
    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result == {
        "success": False,
        "code": "BLACKROOM_ADD_FAILED",
        "message": "add failed",
        "data": None,
    }
    blackroom_service.is_banned.assert_called_once_with("000001", "A")
    blackroom_service.ban.assert_called_once_with(
        stock_code="000001",
        market="A",
        ban_days=30,
        source="shareholder_selling",
        note="股东减持公告 20250103 / 股东C",
    )
