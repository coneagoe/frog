from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from common.const import (
    COL_ANN_DATE,
    COL_END_DATE,
    COL_FLOAT_HOLDER_NAME,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_STOCK_ID,
)
from monitor.forecast_ssf_monitor_sync import ForecastSSFMonitorSyncService


def _forecasts(*stock_codes: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_STOCK_ID: stock_codes,
            COL_END_DATE: [date(2025, 12, 31)] * len(stock_codes),
            COL_ANN_DATE: [date(2026, 1, 15)] * len(stock_codes),
            COL_FORECAST_TYPE: ["预增"] * len(stock_codes),
            COL_FORECAST_CHANGE_MIN: [50.0] * len(stock_codes),
        }
    )


def _holders(ann_date: date, *names: str) -> pd.DataFrame:
    return pd.DataFrame({COL_ANN_DATE: [ann_date] * len(names), COL_FLOAT_HOLDER_NAME: names})


def _blackroom(*, banned: bool = False) -> dict:
    return {"success": True, "code": "OK", "message": "ban status checked", "data": {"banned": banned}}


def _target(target_id: int = 1, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(id=target_id, enabled=enabled)


def _storage(forecasts: pd.DataFrame) -> MagicMock:
    storage = MagicMock()
    storage.load_active_forecast_candidates.return_value = forecasts
    storage.list_forecast_ssf_candidates.return_value = []
    storage.find_workflow_monitor_target.return_value = None
    return storage


def test_sync_creates_target_and_persists_matching_evidence():
    storage = _storage(_forecasts("600001", "600002"))
    storage.load_latest_top10_floatholders.side_effect = [
        _holders(date(2026, 1, 10), "全国社保基金一一八组合"),
        _holders(date(2026, 1, 10), "普通股东"),
    ]
    storage.upsert_workflow_monitor_target.return_value = _target(17)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["success"] is True
    assert result["data"] == {
        "forecast_candidates": 2,
        "blackroom_excluded": 0,
        "ssf_matched": 1,
        "deferred": 0,
        "created": 1,
        "updated": 0,
        "disabled": 0,
        "unchanged": 0,
        "errors": 0,
    }
    storage.upsert_workflow_monitor_target.assert_called_once_with(
        stock_code="600001",
        market="A",
        frequency="daily",
        workflow="forecast_ssf_ma20",
        condition={"type": "price_vs_ma", "direction": "above", "period": 20, "workflow": "forecast_ssf_ma20"},
        note="业绩预增+社保基金+MA20",
        enabled=True,
        reset_last_state=True,
    )
    assert storage.upsert_forecast_ssf_candidate.call_args_list[0].kwargs == {
        "stock_code": "600001",
        "market": "A",
        "report_end_date": date(2025, 12, 31),
        "state": "eligible",
        "state_reason": "ssf_holder_match",
        "evidence": {
            "forecast": {
                "report_end_date": "2025-12-31",
                "ann_date": "2026-01-15",
                "type": "预增",
                "p_change_min": 50.0,
            },
            "shareholder": {"ann_date": "2026-01-10", "matched_holder": "全国社保基金一一八组合"},
            "blackroom": {"banned": False},
        },
        "monitor_target_id": 17,
    }
    assert storage.upsert_forecast_ssf_candidate.call_args_list[1].kwargs["state"] == "ineligible"
    assert storage.upsert_forecast_ssf_candidate.call_args_list[1].kwargs["monitor_target_id"] is None


def test_sync_blackroom_disables_only_existing_marked_target():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.upsert_workflow_monitor_target.return_value = _target(17, enabled=False)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom(banned=True)

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["blackroom_excluded"] == 1
    assert result["data"]["disabled"] == 1
    assert storage.upsert_workflow_monitor_target.call_args.kwargs["enabled"] is False
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["state"] == "blackroom"
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] == 17


@pytest.mark.parametrize("holders", [pd.DataFrame(), _holders(date(2025, 11, 19), "全国社保基金一一八组合")])
def test_sync_defers_absent_or_stale_disclosure_without_disabling_target(holders):
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = holders
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["deferred"] == 1
    storage.upsert_workflow_monitor_target.assert_not_called()
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["state"] == "deferred"
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] == 17


def test_sync_fresh_non_ssf_disables_existing_marked_target():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")
    storage.upsert_workflow_monitor_target.return_value = _target(17, enabled=False)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["state"] == "ineligible"


def test_sync_never_mutates_manual_target():
    storage = _storage(_forecasts("600001"))
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    storage.find_workflow_monitor_target.assert_called_once_with("600001", "A", "daily", "forecast_ssf_ma20")
    storage.upsert_workflow_monitor_target.assert_not_called()


def test_sync_never_mutates_intraday_workflow_target():
    storage = _storage(_forecasts("600001"))
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    storage.find_workflow_monitor_target.assert_called_once_with("600001", "A", "daily", "forecast_ssf_ma20")
    storage.upsert_workflow_monitor_target.assert_not_called()


def test_sync_repeated_eligible_target_is_unchanged_without_reset():
    storage = _storage(_forecasts("600001"))
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.upsert_workflow_monitor_target.return_value = _target(17)
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(state="eligible", monitor_target_id=17, stock_code="600001")
    ]
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["unchanged"] == 1
    assert storage.upsert_workflow_monitor_target.call_args.kwargs["reset_last_state"] is False
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] == 17


def test_sync_forecast_load_failure_mutates_nothing():
    storage = MagicMock()
    storage.load_active_forecast_candidates.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.upsert_workflow_monitor_target.assert_not_called()
    storage.upsert_forecast_ssf_candidate.assert_not_called()


@pytest.mark.parametrize(
    "blackroom_result",
    [
        {"success": False, "code": "STORAGE_ERROR", "message": "blackroom unavailable", "data": None},
        RuntimeError("blackroom unavailable"),
    ],
)
def test_sync_blackroom_failure_mutates_nothing(blackroom_result):
    storage = _storage(_forecasts("600001"))
    blackroom = MagicMock()
    if isinstance(blackroom_result, Exception):
        blackroom.is_banned.side_effect = blackroom_result
    else:
        blackroom.is_banned.return_value = blackroom_result

    with pytest.raises(RuntimeError, match="blackroom unavailable"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    storage.find_workflow_monitor_target.assert_not_called()
    storage.upsert_workflow_monitor_target.assert_not_called()
    storage.upsert_forecast_ssf_candidate.assert_not_called()


def test_sync_holder_failure_defers_one_stock_and_enables_another():
    storage = _storage(_forecasts("600001", "600002"))
    storage.load_latest_top10_floatholders.side_effect = [
        RuntimeError("holder query failed"),
        _holders(date(2026, 1, 10), "全国社保基金一一八组合"),
    ]
    storage.upsert_workflow_monitor_target.return_value = _target(18)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["deferred"] == 1
    assert result["data"]["ssf_matched"] == 1
    assert result["data"]["errors"] == 1
    assert storage.upsert_forecast_ssf_candidate.call_args_list[0].kwargs["state"] == "deferred"
    assert storage.upsert_forecast_ssf_candidate.call_args_list[1].kwargs["state"] == "eligible"
