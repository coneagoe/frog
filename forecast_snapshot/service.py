from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Any, Callable, Protocol, TypedDict

import pandas as pd

from download.dl.downloader_tushare import forecast_fields, get_pro, require_pro_client
from storage import StorageDb, get_storage


class ForecastSnapshotStorage(Protocol):
    def acquire_forecast_snapshot_run(
        self, report_end_date: date, announcement_start_date: date, announcement_end_date: date
    ) -> Any: ...

    def save_forecast_snapshot_records(
        self, run_id: int, records: list[dict[str, object]], counts: dict[str, int]
    ) -> None: ...

    def complete_forecast_snapshot_run(self, run_id: int, counts: dict[str, int]) -> Any: ...

    def fail_forecast_snapshot_run(self, run_id: int, failure_detail: str) -> Any: ...


class ForecastSnapshotRecord(TypedDict):
    ts_code: object
    announcement_date: date
    report_end_date: date
    forecast_type: object
    growth_min: float | None
    growth_max: float | None
    source_order: int


@dataclass(frozen=True)
class ForecastSnapshotRequest:
    report_end_date: date
    announcement_start_date: date
    announcement_end_date: date

    def __post_init__(self) -> None:
        if self.announcement_end_date < self.announcement_start_date:
            raise ValueError("announcement end date must not be before announcement start date")


@dataclass(frozen=True)
class ForecastSnapshotSummary:
    run_id: int
    attempt: int
    status: str
    requested_date_count: int
    covered_date_count: int
    source_row_count: int
    record_count: int
    duplicate_record_count: int
    same_day_conflict_count: int
    failure_detail: str | None

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "run_id": self.run_id,
            "attempt": self.attempt,
            "status": self.status,
            "requested_date_count": self.requested_date_count,
            "covered_date_count": self.covered_date_count,
            "source_row_count": self.source_row_count,
            "record_count": self.record_count,
            "duplicate_record_count": self.duplicate_record_count,
            "same_day_conflict_count": self.same_day_conflict_count,
            "failure_detail": self.failure_detail,
        }


@get_pro
def fetch_forecast_from_tushare(announcement_date: str, pro: Any | None = None) -> pd.DataFrame:
    client = require_pro_client(pro)
    response = client.forecast(ann_date=announcement_date, fields=forecast_fields)
    if not isinstance(response, pd.DataFrame):
        raise TypeError(f"Expected DataFrame, got {type(response)}")
    return response


class ForecastSnapshotService:
    def __init__(self, storage: ForecastSnapshotStorage, fetch_forecast: Callable[[str], pd.DataFrame]) -> None:
        self._storage = storage
        self._fetch_forecast = fetch_forecast

    def create_snapshot(self, request: ForecastSnapshotRequest) -> ForecastSnapshotSummary:
        run = self._storage.acquire_forecast_snapshot_run(
            request.report_end_date,
            request.announcement_start_date,
            request.announcement_end_date,
        )
        if run.status == "completed":
            return self._summary_from_run(run)

        counts = {
            "covered_date_count": 0,
            "source_row_count": 0,
            "record_count": 0,
            "duplicate_record_count": 0,
            "same_day_conflict_count": 0,
        }
        normalized_records: set[tuple[object, ...]] = set()
        same_day_codes: set[tuple[str, date]] = set()

        announcement_date = request.announcement_start_date
        try:
            while announcement_date <= request.announcement_end_date:
                frame = self._fetch_forecast(announcement_date.strftime("%Y%m%d"))
                records = self._normalize_records(frame, announcement_date)
                counts["covered_date_count"] += 1
                counts["source_row_count"] += len(records)
                counts["record_count"] += len(records)
                for record in records:
                    record_tuple = (
                        record["ts_code"],
                        record["announcement_date"],
                        record["report_end_date"],
                        record["forecast_type"],
                        record["growth_min"],
                        record["growth_max"],
                    )
                    if record_tuple in normalized_records:
                        counts["duplicate_record_count"] += 1
                    normalized_records.add(record_tuple)
                    conflict_key = (str(record["ts_code"]), record["announcement_date"])
                    if conflict_key in same_day_codes:
                        counts["same_day_conflict_count"] += 1
                    same_day_codes.add(conflict_key)
                self._storage.save_forecast_snapshot_records(run.id, [dict(record) for record in records], counts)
                announcement_date += timedelta(days=1)
            return self._summary_from_run(self._storage.complete_forecast_snapshot_run(run.id, counts))
        except Exception as exc:
            detail = f"{announcement_date.isoformat()}: {type(exc).__name__}: {exc}"
            return self._summary_from_run(self._storage.fail_forecast_snapshot_run(run.id, detail))

    @staticmethod
    def _normalize_records(frame: pd.DataFrame, requested_announcement_date: date) -> list[ForecastSnapshotRecord]:
        missing = set(forecast_fields) - set(frame.columns)
        if missing:
            raise ValueError(f"forecast response is missing fields: {sorted(missing)}")

        records: list[ForecastSnapshotRecord] = []
        for source_order, row in enumerate(frame.loc[:, forecast_fields].to_dict("records")):
            announcement_date = pd.to_datetime(row["ann_date"], format="%Y%m%d", errors="raise").date()
            if announcement_date != requested_announcement_date:
                raise ValueError(
                    f"forecast announcement date {announcement_date.isoformat()} does not match requested "
                    f"date {requested_announcement_date.isoformat()}"
                )
            report_end_date = pd.to_datetime(row["end_date"], format="%Y%m%d", errors="raise").date()
            records.append(
                {
                    "ts_code": row["ts_code"],
                    "announcement_date": announcement_date,
                    "report_end_date": report_end_date,
                    "forecast_type": row["type"],
                    "growth_min": ForecastSnapshotService._optional_numeric(row["p_change_min"]),
                    "growth_max": ForecastSnapshotService._optional_numeric(row["p_change_max"]),
                    "source_order": source_order,
                }
            )
        return records

    @staticmethod
    def _optional_numeric(value: object) -> float | None:
        values = pd.Series([value])
        if bool(pd.isna(values).iloc[0]):
            return None
        numeric_value = float(pd.to_numeric(values, errors="raise").iloc[0])
        if not isfinite(numeric_value):
            raise ValueError("forecast numeric value must be finite")
        return numeric_value

    @staticmethod
    def _summary_from_run(run: Any) -> ForecastSnapshotSummary:
        return ForecastSnapshotSummary(
            run_id=run.id,
            attempt=run.attempt,
            status=run.status,
            requested_date_count=run.requested_date_count,
            covered_date_count=run.covered_date_count,
            source_row_count=run.source_row_count,
            record_count=run.record_count,
            duplicate_record_count=run.duplicate_record_count,
            same_day_conflict_count=run.same_day_conflict_count,
            failure_detail=run.failure_detail,
        )


def create_forecast_snapshot_service(storage: StorageDb | None = None) -> ForecastSnapshotService:
    return ForecastSnapshotService(storage or get_storage(), fetch_forecast_from_tushare)
