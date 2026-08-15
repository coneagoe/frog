from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, call

import pandas as pd
import pytest

FORECAST_FIELDS = ["ts_code", "ann_date", "end_date", "type", "p_change_min", "p_change_max"]


class FakeStorage:
    def __init__(self, run: SimpleNamespace | None = None) -> None:
        self.run = run or SimpleNamespace(
            id=1,
            attempt=1,
            status="running",
            requested_date_count=2,
            covered_date_count=0,
            source_row_count=0,
            record_count=0,
            duplicate_record_count=0,
            same_day_conflict_count=0,
            failure_detail=None,
        )
        self.saved_records: list[dict[str, object]] = []
        self.failed_run_ids: list[int] = []

    def acquire_forecast_snapshot_run(self, *args: object) -> SimpleNamespace:
        return self.run

    def save_forecast_snapshot_records(
        self, run_id: int, records: list[dict[str, object]], counts: dict[str, int]
    ) -> None:
        assert run_id == self.run.id
        self.saved_records.extend(records)
        for name, value in counts.items():
            setattr(self.run, name, value)

    def complete_forecast_snapshot_run(self, run_id: int, counts: dict[str, int]) -> SimpleNamespace:
        assert run_id == self.run.id
        for name, value in counts.items():
            setattr(self.run, name, value)
        self.run.status = "completed"
        return self.run

    def fail_forecast_snapshot_run(self, run_id: int, failure_detail: str) -> SimpleNamespace:
        assert run_id == self.run.id
        self.failed_run_ids.append(run_id)
        self.run.status = "failed"
        self.run.failure_detail = failure_detail
        return self.run


def test_create_snapshot_persists_all_provider_rows_in_source_order() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    provider = Mock(
        side_effect=[
            pd.DataFrame(
                [
                    ["600001.SH", "20260701", "20260630", "预增", "10.5", None],
                    ["00700.HK", "20260701", "20260630", "预减", None, "-3.0"],
                ],
                columns=FORECAST_FIELDS,
            ),
            pd.DataFrame(columns=FORECAST_FIELDS),
        ]
    )
    service = ForecastSnapshotService(storage, provider)

    summary = service.create_snapshot(ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)))

    assert provider.call_args_list == [call("20260701"), call("20260702")]
    assert summary.to_dict() == {
        "run_id": 1,
        "attempt": 1,
        "status": "completed",
        "requested_date_count": 2,
        "covered_date_count": 2,
        "source_row_count": 2,
        "record_count": 2,
        "duplicate_record_count": 0,
        "same_day_conflict_count": 0,
        "failure_detail": None,
    }
    assert storage.saved_records[0]["source_order"] == 0
    assert storage.saved_records[1]["source_order"] == 1
    assert storage.saved_records[0]["ts_code"] == "600001.SH"


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame({"ts_code": ["600001.SH"]})])
def test_missing_required_schema_marks_running_run_failed(frame: pd.DataFrame) -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    summary = ForecastSnapshotService(storage, Mock(return_value=frame)).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.status == "failed"
    assert storage.failed_run_ids == [1]
    assert "2026-07-01" in summary.failure_detail
    assert "ValueError" in summary.failure_detail


def test_mismatched_returned_announcement_date_marks_run_failed() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    frame = pd.DataFrame([["600001.SH", "20260702", "20260630", "预增", 10, 20]], columns=FORECAST_FIELDS)
    summary = ForecastSnapshotService(storage, Mock(return_value=frame)).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.status == "failed"
    assert "2026-07-01" in summary.failure_detail
    assert "ValueError" in summary.failure_detail


def test_invalid_numeric_value_marks_run_failed() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    frame = pd.DataFrame([["600001.SH", "20260701", "20260630", "预增", "not-a-number", 20]], columns=FORECAST_FIELDS)
    summary = ForecastSnapshotService(storage, Mock(return_value=frame)).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.status == "failed"
    assert "2026-07-01" in summary.failure_detail
    assert "ValueError" in summary.failure_detail


def test_provider_exception_marks_run_failed_without_processing_later_dates() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    provider = Mock(side_effect=ConnectionError("unavailable"))
    summary = ForecastSnapshotService(storage, provider).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2))
    )

    assert summary.status == "failed"
    assert provider.call_args_list == [call("20260701")]
    assert "2026-07-01" in summary.failure_detail
    assert "ConnectionError" in summary.failure_detail


def test_completed_acquisition_returns_stored_summary_without_provider_call() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    run = SimpleNamespace(
        id=5,
        attempt=2,
        status="completed",
        requested_date_count=1,
        covered_date_count=1,
        source_row_count=3,
        record_count=3,
        duplicate_record_count=1,
        same_day_conflict_count=2,
        failure_detail=None,
    )
    provider = Mock()
    summary = ForecastSnapshotService(FakeStorage(run), provider).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.to_dict()["run_id"] == 5
    assert summary.to_dict()["status"] == "completed"
    provider.assert_not_called()


def test_failed_acquisition_creates_later_attempt() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    storage.run.attempt = 2
    provider = Mock(return_value=pd.DataFrame(columns=FORECAST_FIELDS))
    summary = ForecastSnapshotService(storage, provider).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.attempt == 2
    assert summary.status == "completed"


def test_create_snapshot_counts_duplicate_records_and_same_day_conflicts() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest, ForecastSnapshotService

    storage = FakeStorage()
    frame = pd.DataFrame(
        [
            ["600001.SH", "20260701", "20260630", "预增", 10, 20],
            ["600001.SH", "20260701", "20260630", "预增", 10, 20],
            ["600001.SH", "20260701", "20260630", "预减", 5, 15],
        ],
        columns=FORECAST_FIELDS,
    )
    summary = ForecastSnapshotService(storage, Mock(return_value=frame)).create_snapshot(
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))
    )

    assert summary.duplicate_record_count == 1
    assert summary.same_day_conflict_count == 2
    assert len(storage.saved_records) == 3


def test_snapshot_request_rejects_reversed_announcement_range() -> None:
    from forecast_snapshot.service import ForecastSnapshotRequest

    with pytest.raises(ValueError, match="announcement end date"):
        ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 2), date(2026, 7, 1))
