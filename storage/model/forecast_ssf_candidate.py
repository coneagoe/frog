from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, Integer, String
from sqlalchemy.sql import func

from monitor.domain_enums import ForecastSSFCandidateState, MonitorMarket

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_forecast_ssf_candidate = "forecast_ssf_candidates"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class ForecastSSFCandidate(Base):
    __tablename__ = tb_name_forecast_ssf_candidate

    stock_code: Mapped[str] = mapped_column(String(6), primary_key=True, comment="股票代码")
    market: Mapped[str] = mapped_column(
        _value_enum(MonitorMarket, "monitor_market"), nullable=False, default="A", server_default="A"
    )
    report_end_date: Mapped[date] = mapped_column(Date, nullable=False, comment="业绩预告报告期")
    state: Mapped[str] = mapped_column(
        _value_enum(ForecastSSFCandidateState, "forecast_ssf_candidate_state"), nullable=False, comment="候选状态"
    )
    state_reason: Mapped[str] = mapped_column(String(128), nullable=False, comment="状态原因")
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="审计证据")
    monitor_target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="监控目标ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
