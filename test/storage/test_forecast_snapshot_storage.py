from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from storage.domain_enums import ForecastSnapshotStatus
from storage.model import Base, ForecastSnapshotRecord, ForecastSnapshotRun
from storage.storage_db import StorageDb, StorageError


@pytest.fixture()
def db(tmp_path):
    storage = StorageDb.__new__(StorageDb)
    storage.engine = create_engine(f"sqlite:///{tmp_path}/forecast_snapshot.db")
    storage.Session = sessionmaker(bind=storage.engine)
    return storage


def test_snapshot_record_source_order_is_unique_within_a_provider_response() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        run_id = connection.execute(
            ForecastSnapshotRun.__table__.insert().values(
                report_end_date=date(2026, 6, 30),
                announcement_start_date=date(2026, 7, 1),
                announcement_end_date=date(2026, 7, 1),
                attempt=1,
                status=ForecastSnapshotStatus.RUNNING.value,
            )
        ).inserted_primary_key[0]
        row = {
            "run_id": run_id,
            "source_order": 0,
            "ts_code": "600001.SH",
            "announcement_date": date(2026, 7, 1),
            "report_end_date": date(2026, 6, 30),
            "forecast_type": "预增",
        }
        connection.execute(ForecastSnapshotRecord.__table__.insert().values(row))
        with pytest.raises(IntegrityError):
            connection.execute(ForecastSnapshotRecord.__table__.insert().values(row))


def test_snapshot_run_attempt_is_unique_within_a_range() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        row = {
            "report_end_date": date(2026, 6, 30),
            "announcement_start_date": date(2026, 7, 1),
            "announcement_end_date": date(2026, 7, 1),
            "attempt": 1,
            "status": ForecastSnapshotStatus.RUNNING.value,
        }
        connection.execute(ForecastSnapshotRun.__table__.insert().values(row))
        with pytest.raises(IntegrityError):
            connection.execute(ForecastSnapshotRun.__table__.insert().values(row))


def test_snapshot_run_allows_only_one_running_range() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        range_values = {
            "report_end_date": date(2026, 6, 30),
            "announcement_start_date": date(2026, 7, 1),
            "announcement_end_date": date(2026, 7, 1),
        }
        connection.execute(
            ForecastSnapshotRun.__table__.insert().values(
                **range_values,
                attempt=1,
                status=ForecastSnapshotStatus.RUNNING.value,
            )
        )
        connection.execute(
            ForecastSnapshotRun.__table__.insert().values(
                **range_values,
                attempt=2,
                status=ForecastSnapshotStatus.COMPLETED.value,
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                ForecastSnapshotRun.__table__.insert().values(
                    **range_values,
                    attempt=3,
                    status=ForecastSnapshotStatus.RUNNING.value,
                )
            )


def test_snapshot_acquisition_reuses_completed_run_and_retries_failed_run(db) -> None:
    first = db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2))
    assert first.attempt == 1
    assert first.status == "running"

    db.complete_forecast_snapshot_run(
        first.id,
        {
            "covered_date_count": 2,
            "source_row_count": 0,
            "record_count": 0,
            "duplicate_record_count": 0,
            "same_day_conflict_count": 0,
        },
    )
    assert db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)).id == first.id

    failed = db.acquire_forecast_snapshot_run(date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 1))
    db.fail_forecast_snapshot_run(failed.id, "provider unavailable")
    retry = db.acquire_forecast_snapshot_run(date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 1))
    assert (retry.attempt, retry.status) == (2, "running")


def test_snapshot_acquisition_rejects_an_active_range(db) -> None:
    db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))

    with pytest.raises(StorageError, match="forecast snapshot is already running for requested range"):
        db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 1))


def test_snapshot_records_list_by_announcement_date_then_source_order(db) -> None:
    run = db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2))
    db.save_forecast_snapshot_records(
        run.id,
        [
            {
                "ts_code": "600003.SH",
                "announcement_date": date(2026, 7, 2),
                "report_end_date": date(2026, 6, 30),
                "forecast_type": "increase",
                "source_order": 0,
            },
            {
                "ts_code": "600002.SH",
                "announcement_date": date(2026, 7, 1),
                "report_end_date": date(2026, 6, 30),
                "forecast_type": "increase",
                "source_order": 1,
            },
            {
                "ts_code": "600001.SH",
                "announcement_date": date(2026, 7, 1),
                "report_end_date": date(2026, 6, 30),
                "forecast_type": "increase",
                "source_order": 0,
            },
        ],
        {"source_row_count": 3, "record_count": 3, "duplicate_record_count": 0, "same_day_conflict_count": 0},
    )

    assert [record.ts_code for record in db.list_forecast_snapshot_records(run.id)] == [
        "600001.SH",
        "600002.SH",
        "600003.SH",
    ]


def test_get_completed_snapshot_run_excludes_running_and_failed_runs(db) -> None:
    report_end_date = date(2026, 6, 30)
    running = db.acquire_forecast_snapshot_run(report_end_date, date(2026, 7, 1), date(2026, 7, 1))
    assert db.get_completed_forecast_snapshot_run(report_end_date, date(2026, 7, 1), date(2026, 7, 1)) is None

    db.fail_forecast_snapshot_run(running.id, "provider unavailable")
    assert db.get_completed_forecast_snapshot_run(report_end_date, date(2026, 7, 1), date(2026, 7, 1)) is None
