from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.sql import func

from storage.domain_enums import ForecastSnapshotStatus

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_forecast_snapshot_run = "forecast_snapshot_runs"
tb_name_forecast_snapshot_record = "forecast_snapshot_records"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class ForecastSnapshotRun(Base):
    __tablename__ = tb_name_forecast_snapshot_run
    __table_args__ = (
        UniqueConstraint(
            "report_end_date",
            "announcement_start_date",
            "announcement_end_date",
            "attempt",
            name="uq_forecast_snapshot_attempt",
        ),
        Index(
            "uq_forecast_snapshot_running_range",
            "report_end_date",
            "announcement_start_date",
            "announcement_end_date",
            unique=True,
            sqlite_where=text("status = 'running'"),
            postgresql_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    announcement_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    announcement_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(_value_enum(ForecastSnapshotStatus, "forecast_snapshot_status"), nullable=False)
    requested_date_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    covered_date_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duplicate_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    same_day_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ForecastSnapshotRecord(Base):
    __tablename__ = tb_name_forecast_snapshot_record
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "announcement_date",
            "source_order",
            name="uq_forecast_snapshot_record_source_order",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_snapshot_runs.id"), nullable=False)
    ts_code: Mapped[str] = mapped_column(String(32), nullable=False)
    announcement_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_type: Mapped[str] = mapped_column(String(20), nullable=False)
    growth_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
