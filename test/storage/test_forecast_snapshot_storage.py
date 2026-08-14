from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from storage.domain_enums import ForecastSnapshotStatus
from storage.model import Base, ForecastSnapshotRecord, ForecastSnapshotRun


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
