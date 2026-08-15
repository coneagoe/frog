from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from common.const import (
    COL_ANN_DATE,
    COL_DELISTING_DATE,
    COL_END_DATE,
    COL_FLOAT_HOLDER_NAME,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_LIST_STATUS,
    COL_STOCK_ID,
)
from monitor.forecast_ssf_monitor_sync import ForecastSSFMonitorSyncService, NoEligibleForecastSnapshotError


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


def _snapshot(
    *,
    snapshot_id: int = 42,
    report_end_date: date = date(2025, 12, 31),
    announcement_start_date: date = date(2026, 1, 1),
    announcement_end_date: date = date(2026, 1, 15),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=snapshot_id,
        report_end_date=report_end_date,
        announcement_start_date=announcement_start_date,
        announcement_end_date=announcement_end_date,
        completed_at=pd.Timestamp("2026-01-16T00:00:00+00:00").to_pydatetime(),
    )


def _records(*stock_codes: str, **overrides: object) -> pd.DataFrame:
    records = _forecasts(*stock_codes).assign(source_order=3)
    for column, value in overrides.items():
        records[column] = value
    return records


def _snapshot_evidence() -> dict:
    return {
        "id": 42,
        "report_end_date": "2025-12-31",
        "announcement_start_date": "2026-01-01",
        "announcement_end_date": "2026-01-15",
        "completed_at": "2026-01-16T00:00:00+00:00",
    }


def _holders(ann_date: date, *names: str) -> pd.DataFrame:
    return pd.DataFrame({COL_ANN_DATE: [ann_date] * len(names), COL_FLOAT_HOLDER_NAME: names})


def _blackroom(*, banned: bool = False) -> dict:
    return {"success": True, "code": "OK", "message": "ban status checked", "data": {"banned": banned}}


def _target(target_id: int = 1, enabled: bool = True, paused: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=target_id, enabled=enabled, paused=paused)


def _candidate(target_id: int = 17, state: str = "eligible") -> SimpleNamespace:
    return SimpleNamespace(
        stock_code="600001",
        report_end_date=date(2025, 12, 31),
        state=state,
        monitor_target_id=target_id,
        evidence={},
    )


def _storage(forecasts: pd.DataFrame) -> MagicMock:
    storage = MagicMock()
    storage.get_latest_completed_forecast_snapshot_run.return_value = _snapshot()
    storage.load_selected_forecast_snapshot_records.return_value = forecasts.assign(source_order=3)
    storage.list_forecast_ssf_candidates.return_value = []
    storage.find_workflow_monitor_target.return_value = None
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: forecasts[COL_STOCK_ID],
            COL_LIST_STATUS: ["L"] * len(forecasts),
            COL_DELISTING_DATE: [None] * len(forecasts),
            "股票名称": ["普通股份"] * len(forecasts),
        }
    )
    return storage


def test_sync_without_eligible_snapshot_raises_before_any_mutation() -> None:
    storage = MagicMock()
    storage.get_latest_completed_forecast_snapshot_run.return_value = None
    blackroom = MagicMock()

    with pytest.raises(NoEligibleForecastSnapshotError, match="no completed forecast snapshot"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    storage.load_selected_forecast_snapshot_records.assert_not_called()
    storage.list_forecast_ssf_candidates.assert_not_called()
    storage.load_a_stock_listing_status.assert_not_called()
    storage.upsert_forecast_ssf_candidate.assert_not_called()
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    blackroom.is_banned.assert_not_called()


def test_sync_qualifies_snapshot_record_and_persists_provenance() -> None:
    storage = _storage(_records("600001"))
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    storage.upsert_forecast_ssf_candidate_with_workflow_target.return_value = _target(17)

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )

    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert call["condition"] == {
        "type": "close_cross_ma",
        "direction": "above",
        "period": 20,
        "workflow": "forecast_ssf_ma20",
    }
    assert call["evidence"]["snapshot"] == {
        "id": 42,
        "report_end_date": "2025-12-31",
        "announcement_start_date": "2026-01-01",
        "announcement_end_date": "2026-01-15",
        "completed_at": "2026-01-16T00:00:00+00:00",
    }
    assert call["evidence"]["forecast"]["source_order"] == 3


@pytest.mark.parametrize(
    ("stock_code", "listing_status", "stock_name", "forecast_type", "growth_min"),
    [
        ("430001", "L", "普通股份", "预增", 50.0),
        ("600001", "D", "普通股份", "预增", 50.0),
        ("600001", "L", "ST普通股份", "预增", 50.0),
        ("600001", "L", "普通股份", "略增", 50.0),
        ("600001", "L", "普通股份", "预增", "not numeric"),
        ("600001", "L", "普通股份", "预增", float("nan")),
        ("600001", "L", "普通股份", "预增", 49.9),
    ],
    ids=["unsupported", "unlisted", "st", "wrong_type", "non_numeric", "non_finite", "below_threshold"],
)
def test_sync_nonqualifying_snapshot_rows_cannot_create_target(
    stock_code, listing_status, stock_name, forecast_type, growth_min
) -> None:
    storage = _storage(_records(stock_code, **{COL_FORECAST_TYPE: forecast_type, COL_FORECAST_CHANGE_MIN: growth_min}))
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: [stock_code],
            COL_LIST_STATUS: [listing_status],
            COL_DELISTING_DATE: [None],
            "股票名称": [stock_name],
        }
    )

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()


def test_sync_later_nonqualifying_snapshot_revision_does_not_preserve_older_qualifying_record() -> None:
    records = _records("600001", **{COL_FORECAST_CHANGE_MIN: 40.0})
    storage = _storage(records)

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()


def test_sync_nonqualifying_snapshot_row_disables_previous_candidate_with_provenance() -> None:
    storage = _storage(_records("600001", **{COL_FORECAST_CHANGE_MIN: 40.0}))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17)

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    evidence = storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args[3]
    assert evidence["snapshot"]["id"] == 42
    assert evidence["forecast"]["source_order"] == 3
    assert evidence["forecast"]["p_change_min"] == 40.0


def test_sync_nonnumeric_snapshot_row_disables_existing_target_and_persists_evidence() -> None:
    storage = _storage(_records("600001", **{COL_FORECAST_CHANGE_MIN: "not numeric"}))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17)

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    call = storage.disable_forecast_ssf_target_with_candidate_transition.call_args
    assert call.args[:3] == (17, "ineligible", "forecast_no_longer_qualified")
    assert call.args[3]["forecast"] == {
        "report_end_date": "2025-12-31",
        "ann_date": "2026-01-15",
        "type": "预增",
        "p_change_min": "not numeric",
        "source_order": 3,
    }


def test_sync_absent_selected_row_marks_current_forecast_provenance_absent() -> None:
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="eligible",
            monitor_target_id=17,
            evidence={
                "forecast": {
                    "ann_date": "2026-01-15",
                    "source_order": 3,
                }
            },
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(17)
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {COL_STOCK_ID: ["600001"], COL_LIST_STATUS: ["L"], COL_DELISTING_DATE: [None]}
    )

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    evidence = storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args[3]
    assert evidence["snapshot"] == _snapshot_evidence()
    assert evidence["forecast"] == {"selected": False, "ann_date": None, "source_order": None}
    assert evidence["lifecycle"]["reason"] == "forecast_no_longer_qualified"


def test_sync_creates_target_and_persists_matching_evidence():
    storage = _storage(_forecasts("600001", "600002"))
    storage.load_latest_top10_floatholders.side_effect = [
        _holders(date(2026, 1, 10), "全国社保基金一一八组合"),
        _holders(date(2026, 1, 10), "普通股东"),
    ]
    storage.upsert_forecast_ssf_candidate_with_workflow_target.return_value = _target(17)
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
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_called_once_with(
        stock_code="600001",
        market="A",
        frequency="daily",
        workflow="forecast_ssf_ma20",
        condition={"type": "close_cross_ma", "direction": "above", "period": 20, "workflow": "forecast_ssf_ma20"},
        note="业绩预增+社保基金+MA20",
        report_end_date=date(2025, 12, 31),
        state="eligible",
        state_reason="ssf_holder_match",
        evidence={
            "snapshot": {
                "id": 42,
                "report_end_date": "2025-12-31",
                "announcement_start_date": "2026-01-01",
                "announcement_end_date": "2026-01-15",
                "completed_at": "2026-01-16T00:00:00+00:00",
            },
            "forecast": {
                "report_end_date": "2025-12-31",
                "ann_date": "2026-01-15",
                "type": "预增",
                "p_change_min": 50.0,
                "source_order": 3,
            },
            "shareholder": {"ann_date": "2026-01-10", "matched_holder": "全国社保基金一一八组合"},
            "blackroom": {"banned": False},
            "lifecycle": {"as_of_date": "2026-01-20", "state": "eligible", "reason": "ssf_holder_match"},
        },
        target_enabled=True,
        reset_last_state=True,
    )
    assert storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs["state"] == "eligible"
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["state"] == "ineligible"
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] is None


def test_sync_blackroom_deletes_only_existing_marked_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom(banned=True)

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["blackroom_excluded"] == 1
    assert result["data"]["disabled"] == 1
    storage.disable_forecast_ssf_target_with_candidate_transition.assert_called_once()


@pytest.mark.parametrize("holders", [pd.DataFrame(), _holders(date(2025, 11, 19), "全国社保基金一一八组合")])
def test_sync_defers_absent_or_stale_disclosure_without_disabling_target(holders):
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = holders
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["deferred"] == 1
    storage.upsert_workflow_monitor_target.assert_not_called()
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["state"] == "deferred"
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] == 17


def test_sync_current_unlisted_candidate_deletes_linked_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {COL_STOCK_ID: ["600001"], COL_LIST_STATUS: ["D"], COL_DELISTING_DATE: [date(2026, 1, 19)]}
    )
    blackroom = MagicMock(is_banned=lambda *_: _blackroom())

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args[:3] == (
        17,
        "delisted_or_unlisted",
        "delisted_or_unlisted",
    )


def test_sync_current_candidate_with_stale_target_link_does_not_mutate_or_relink_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="eligible",
            monitor_target_id=17,
            evidence={},
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(18, enabled=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    call = storage.upsert_forecast_ssf_candidate.call_args.kwargs
    assert call["monitor_target_id"] is None
    assert call["state"] == "ineligible"


def test_sync_current_eligible_candidate_with_stale_target_link_does_not_create_or_enable_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="eligible",
            monitor_target_id=17,
            evidence={},
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(18, enabled=False)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs["monitor_target_id"] is None


def test_sync_fresh_ssf_match_with_orphan_target_persists_candidate_without_target_mutation():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))

    assert result["data"]["created"] == 0
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    call = storage.upsert_forecast_ssf_candidate.call_args.kwargs
    assert (call["state"], call["state_reason"], call["monitor_target_id"]) == (
        "eligible",
        "ssf_holder_match",
        None,
    )


def test_sync_unlinked_candidate_non_ssf_result_does_not_disable_or_relink_orphan_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="eligible",
            monitor_target_id=None,
            evidence={},
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 0
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    call = storage.upsert_forecast_ssf_candidate.call_args.kwargs
    assert (call["state"], call["state_reason"], call["monitor_target_id"]) == (
        "ineligible",
        "ssf_holder_not_found",
        None,
    )


@pytest.mark.parametrize(
    ("holders", "reason"),
    [
        (RuntimeError("holder query failed"), "holder_query_failed"),
        (pd.DataFrame(), "holder_disclosure_missing"),
        (_holders(date(2025, 11, 19), "全国社保基金一一八组合"), "holder_disclosure_stale"),
    ],
    ids=["query_failed", "missing", "stale"],
)
def test_sync_current_deferred_candidate_with_stale_target_link_does_not_relink_candidate(holders, reason):
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="deferred",
            monitor_target_id=17,
            evidence={},
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(18, enabled=True)
    if isinstance(holders, Exception):
        storage.load_latest_top10_floatholders.side_effect = holders
    else:
        storage.load_latest_top10_floatholders.return_value = holders

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )

    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    call = storage.upsert_forecast_ssf_candidate.call_args.kwargs
    assert (call["state"], call["state_reason"], call["monitor_target_id"]) == ("deferred", reason, None)


def test_sync_non_ssf_deletes_existing_owned_target():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate()]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    assert storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args[:3] == (
        17,
        "ineligible",
        "ssf_holder_not_found",
    )


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
    storage.upsert_forecast_ssf_candidate_with_workflow_target.return_value = _target(17)
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(state="eligible", monitor_target_id=17, stock_code="600001")
    ]
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["unchanged"] == 1
    assert storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs["reset_last_state"] is False


def test_sync_snapshot_record_load_failure_mutates_nothing():
    storage = MagicMock()
    storage.get_latest_completed_forecast_snapshot_run.return_value = _snapshot()
    storage.load_selected_forecast_snapshot_records.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.list_forecast_ssf_candidates.assert_not_called()
    storage.find_workflow_monitor_target.assert_not_called()
    storage.upsert_workflow_monitor_target.assert_not_called()
    storage.upsert_forecast_ssf_candidate.assert_not_called()
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()


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
    storage.upsert_forecast_ssf_candidate_with_workflow_target.return_value = _target(18)
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["deferred"] == 1
    assert result["data"]["ssf_matched"] == 1
    assert result["data"]["errors"] == 1
    assert storage.upsert_forecast_ssf_candidate.call_args_list[0].kwargs["state"] == "deferred"
    assert storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs["state"] == "eligible"


def test_sync_retires_absent_daily_workflow_candidate_with_lifecycle_evidence():
    storage = _storage(_forecasts("600002"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            monitor_target_id=17,
            evidence={"forecast": {"ann_date": "2026-01-15"}},
        )
    ]
    storage.find_workflow_monitor_target.side_effect = [None, _target(17, enabled=True)]
    storage.load_latest_top10_floatholders.return_value = pd.DataFrame()
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: ["600001", "600002"],
            COL_LIST_STATUS: ["L", "L"],
            COL_DELISTING_DATE: [None, None],
        }
    )
    blackroom = MagicMock()
    blackroom.is_banned.return_value = _blackroom()

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    assert storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args == (
        17,
        "ineligible",
        "forecast_no_longer_qualified",
        {
            "forecast": {"selected": False, "ann_date": None, "source_order": None},
            "snapshot": _snapshot_evidence(),
            "lifecycle": {
                "as_of_date": "2026-01-20",
                "state": "ineligible",
                "reason": "forecast_no_longer_qualified",
            },
        },
    )


def test_sync_empty_universe_retires_only_matching_daily_workflow_targets():
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(stock_code="600001", report_end_date=date(2025, 12, 31), monitor_target_id=17, evidence={}),
        SimpleNamespace(stock_code="600002", report_end_date=date(2025, 12, 31), monitor_target_id=18, evidence={}),
        SimpleNamespace(stock_code="600003", report_end_date=date(2025, 12, 31), monitor_target_id=19, evidence={}),
    ]
    storage.find_workflow_monitor_target.side_effect = [_target(17, enabled=True), None, None]

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    assert storage.disable_forecast_ssf_target_with_candidate_transition.call_count == 1
    assert storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args[0] == 17
    assert [call.kwargs["stock_code"] for call in storage.upsert_forecast_ssf_candidate.call_args_list] == [
        "600002",
        "600003",
    ]
    assert all(
        call.kwargs["monitor_target_id"] is None for call in storage.upsert_forecast_ssf_candidate.call_args_list
    )


def test_sync_retires_unlinked_absent_candidate_without_creating_target():
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            monitor_target_id=None,
            evidence={"shareholder": {"matched_holder": "全国社保基金一一八组合"}},
        )
    ]
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: ["600001"],
            COL_LIST_STATUS: ["L"],
            COL_DELISTING_DATE: [None],
        }
    )

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    storage.find_workflow_monitor_target.assert_not_called()
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs == {
        "stock_code": "600001",
        "market": "A",
        "report_end_date": date(2025, 12, 31),
        "state": "ineligible",
        "state_reason": "forecast_no_longer_qualified",
        "evidence": {
            "shareholder": {"matched_holder": "全国社保基金一一八组合"},
            "snapshot": _snapshot_evidence(),
            "forecast": {"selected": False, "ann_date": None, "source_order": None},
            "lifecycle": {
                "as_of_date": "2026-01-20",
                "state": "ineligible",
                "reason": "forecast_no_longer_qualified",
            },
        },
        "monitor_target_id": None,
    }


@pytest.mark.parametrize("daily_target", [None, _target(18, enabled=True)], ids=["missing", "mismatched"])
def test_sync_retires_absent_candidate_with_stale_target_link(daily_target):
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            monitor_target_id=17,
            evidence={"forecast": {"ann_date": "2026-01-15"}},
        )
    ]
    storage.find_workflow_monitor_target.return_value = daily_target
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: ["600001"],
            COL_LIST_STATUS: ["L"],
            COL_DELISTING_DATE: [None],
        }
    )

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 0
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()
    assert storage.upsert_forecast_ssf_candidate.call_args.kwargs == {
        "stock_code": "600001",
        "market": "A",
        "report_end_date": date(2025, 12, 31),
        "state": "ineligible",
        "state_reason": "forecast_no_longer_qualified",
        "evidence": {
            "forecast": {"selected": False, "ann_date": None, "source_order": None},
            "snapshot": _snapshot_evidence(),
            "lifecycle": {
                "as_of_date": "2026-01-20",
                "state": "ineligible",
                "reason": "forecast_no_longer_qualified",
            },
        },
        "monitor_target_id": None,
    }


def test_sync_repeated_retirement_deletes_linked_target():
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(stock_code="600001", report_end_date=date(2025, 12, 31), monitor_target_id=17, evidence={})
    ]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False)

    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    storage.disable_forecast_ssf_target_with_candidate_transition.assert_called_once()


def test_sync_paused_eligible_candidate_keeps_target_disabled_and_records_evaluated_outcome():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(state="paused")]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False, paused=True)
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")
    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )
    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert (call["state"], call["target_enabled"]) == ("paused", False)
    assert call["evidence"]["evaluation"]["state"] == "eligible"


def test_sync_deferral_does_not_change_enabled_target():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    storage.load_latest_top10_floatholders.return_value = pd.DataFrame()
    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())).sync(
        date(2026, 1, 20)
    )
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()


def test_sync_listing_preflight_failure_mutates_nothing():
    storage = _storage(_forecasts("600001"))
    storage.load_a_stock_listing_status.side_effect = RuntimeError("listing unavailable")
    with pytest.raises(RuntimeError, match="listing unavailable"):
        ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))
    storage.upsert_forecast_ssf_candidate.assert_not_called()
    storage.upsert_forecast_ssf_candidate_with_workflow_target.assert_not_called()


def test_sync_reporting_period_promotion_deletes_without_evaluating_new_period():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001", report_end_date=date(2025, 9, 30), state="eligible", monitor_target_id=17, evidence={}
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))
    call = storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args
    assert result["data"]["disabled"] == 1
    assert call[:3] == (
        17,
        "ineligible",
        "reporting_period_superseded",
    )
    assert call[3]["lifecycle"]["new_report_end_date"] == "2025-12-31"
    storage.load_latest_top10_floatholders.assert_not_called()


def test_sync_absent_listing_retires_candidate_with_delisted_reason():
    storage = _storage(_forecasts())
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(stock_code="600001", report_end_date=date(2025, 12, 31), state="eligible", evidence={})
    ]
    result = ForecastSSFMonitorSyncService(storage=storage, blackroom_service=MagicMock()).sync(date(2026, 1, 20))
    call = storage.upsert_forecast_ssf_candidate.call_args.kwargs
    assert result["data"]["disabled"] == 0
    assert (call["state"], call["state_reason"]) == ("delisted_or_unlisted", "delisted_or_unlisted")
    assert call["evidence"]["lifecycle"]["state"] == "delisted_or_unlisted"


def test_sync_blackroom_recovery_reenables_eligible_target_after_expiry():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False)
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="blackroom",
            monitor_target_id=17,
            evidence={"blackroom": {"banned": True}},
        )
    ]
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom(banned=False))
    ).sync(date(2026, 1, 20))

    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert result["data"]["updated"] == 1
    assert (call["state"], call["target_enabled"]) == ("eligible", True)
    assert call["evidence"]["lifecycle"]["previous_state"] == "blackroom"


def test_sync_repeated_ineligible_lifecycle_deletes_linked_target():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False)
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="ineligible",
            monitor_target_id=17,
            evidence={},
        )
    ]
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "普通股东")

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))

    assert result["data"]["disabled"] == 1
    assert result["data"]["updated"] == 0
    assert result["data"]["created"] == 0


def test_sync_repeated_paused_eligible_candidate_does_not_increment_updated_counter():
    storage = _storage(_forecasts("600001"))
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False, paused=True)
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001",
            report_end_date=date(2025, 12, 31),
            state="paused",
            monitor_target_id=17,
            evidence={},
        )
    ]
    storage.load_latest_top10_floatholders.return_value = _holders(date(2026, 1, 10), "全国社保基金一一八组合")

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))

    assert result["data"]["updated"] == 0
    assert result["data"]["created"] == 0


@pytest.mark.parametrize(
    ("listed", "banned", "holders", "automatic_state", "automatic_reason"),
    [
        (False, False, pd.DataFrame(), "delisted_or_unlisted", "delisted_or_unlisted"),
        (True, True, pd.DataFrame(), "blackroom", "active_blackroom"),
        (True, False, _holders(date(2026, 1, 10), "普通股东"), "ineligible", "ssf_holder_not_found"),
    ],
    ids=["listing", "blackroom", "ineligible"],
)
def test_sync_paused_conclusive_outcomes_delete_linked_target(
    listed, banned, holders, automatic_state, automatic_reason
):
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(state="paused")]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True, paused=True)
    storage.load_a_stock_listing_status.return_value = pd.DataFrame(
        {
            COL_STOCK_ID: ["600001"] if listed else [],
            COL_LIST_STATUS: ["L"] if listed else [],
            COL_DELISTING_DATE: [None] if listed else [],
        }
    )
    storage.load_latest_top10_floatholders.return_value = holders
    blackroom = MagicMock(is_banned=lambda *_: _blackroom(banned=banned))

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    call = storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args
    assert call[:3] == (17, automatic_state, automatic_reason)
    assert call[3]["lifecycle"] == {
        "as_of_date": "2026-01-20",
        "state": automatic_state,
        "reason": automatic_reason,
        "previous_state": "paused",
    }


@pytest.mark.parametrize(
    ("holders", "reason"),
    [
        (RuntimeError("holder query failed"), "holder_query_failed"),
        (pd.DataFrame(), "holder_disclosure_missing"),
        (_holders(date(2025, 11, 19), "全国社保基金一一八组合"), "holder_disclosure_stale"),
    ],
    ids=["query_failed", "missing", "stale"],
)
def test_sync_paused_deferred_outcome_preserves_pause_and_records_evaluation(holders, reason):
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [_candidate(state="paused")]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=False, paused=True)
    if isinstance(holders, Exception):
        storage.load_latest_top10_floatholders.side_effect = holders
    else:
        storage.load_latest_top10_floatholders.return_value = holders

    result = ForecastSSFMonitorSyncService(
        storage=storage, blackroom_service=MagicMock(is_banned=lambda *_: _blackroom())
    ).sync(date(2026, 1, 20))

    call = storage.upsert_forecast_ssf_candidate_with_workflow_target.call_args.kwargs
    assert (call["state"], call["state_reason"], call["target_enabled"]) == ("paused", "manual_pause", False)
    assert call["evidence"]["lifecycle"] == {
        "as_of_date": "2026-01-20",
        "state": "paused",
        "reason": "manual_pause",
    }
    assert call["evidence"]["evaluation"] == {"state": "deferred", "reason": reason}
    assert storage.upsert_workflow_monitor_target.call_count == 0
    assert result["data"]["disabled"] == 0


def test_sync_active_blackroom_deletes_before_newer_reporting_period_supersession():
    storage = _storage(_forecasts("600001"))
    storage.list_forecast_ssf_candidates.return_value = [
        SimpleNamespace(
            stock_code="600001", report_end_date=date(2025, 9, 30), state="eligible", monitor_target_id=17, evidence={}
        )
    ]
    storage.find_workflow_monitor_target.return_value = _target(17, enabled=True)
    blackroom = MagicMock(is_banned=lambda *_: _blackroom(banned=True))

    ForecastSSFMonitorSyncService(storage=storage, blackroom_service=blackroom).sync(date(2026, 1, 20))

    call = storage.disable_forecast_ssf_target_with_candidate_transition.call_args.args
    assert call[:3] == (
        17,
        "blackroom",
        "active_blackroom",
    )
    assert "new_report_end_date" not in call[3]["lifecycle"]
