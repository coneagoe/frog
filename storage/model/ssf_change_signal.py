from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from storage.domain_enums import SSFChangeSignalStatus

from .base import Base

tb_name_ssf_change_signal = "ssf_change_signals"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class SSFChangeSignal(Base):
    __tablename__ = tb_name_ssf_change_signal
    __table_args__ = (UniqueConstraint("stock_id", "ann_date", name="uq_ssf_change_signal_stock_ann_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(6), nullable=False, comment="股票代码")
    ann_date = Column(Date, nullable=False, comment="最新公告日期")
    status: Any = Column(
        _value_enum(SSFChangeSignalStatus, "ssf_change_signal_status"),
        nullable=False,
        default="signal",
        server_default="signal",
        comment="处理状态: signal/no_signal",
    )
    prev_ann_date = Column(Date, nullable=False, comment="上期公告日期")
    event_types = Column(JSON, nullable=False, comment="股票级事件类型列表")
    score = Column(Float, nullable=False, comment="综合分")
    ssf_holder_count_now = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_holder_count_prev = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_holder_count_change = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_total_hold_ratio_now = Column(Float, nullable=False, default=0.0, server_default="0")
    ssf_total_hold_ratio_prev = Column(Float, nullable=False, default=0.0, server_default="0")
    ssf_total_hold_ratio_change = Column(Float, nullable=False, default=0.0, server_default="0")
    detail_json = Column(JSON, nullable=False, comment="股东级明细")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    alert_sent_at = Column(DateTime(timezone=True), nullable=True, comment="汇总邮件发送时间")
