from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Integer, String, Text, text
from sqlalchemy.sql import func

from monitor.domain_enums import MonitorFrequency, MonitorMarket, MonitorResetMode

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_stock_monitor_target = "stock_monitor_targets"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class StockMonitorTarget(Base):
    __tablename__ = tb_name_stock_monitor_target

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="股票/ETF/港股代码")
    market: Mapped[str] = mapped_column(
        _value_enum(MonitorMarket, "monitor_market"),
        nullable=False,
        default="A",
        server_default="A",
        comment="市场: A / HK / ETF",
    )
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="触发条件JSON")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用户备注")
    frequency: Mapped[str] = mapped_column(
        _value_enum(MonitorFrequency, "monitor_frequency"),
        nullable=False,
        default="daily",
        server_default="daily",
        comment="监控频率: daily / intraday",
    )
    workflow: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="工作流所有者；手工目标为空")
    reset_mode: Mapped[str] = mapped_column(
        _value_enum(MonitorResetMode, "monitor_reset_mode"),
        nullable=False,
        default="auto",
        server_default="auto",
        comment="重置模式: auto / manual",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="是否由操作员暂停自动启用",
    )
    last_state: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="上次条件是否成立（边沿触发用）",
    )
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近触发时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
