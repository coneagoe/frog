from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.sql import func

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_stock_monitor_target = "stock_monitor_targets"


class StockMonitorTarget(Base):
    __tablename__ = tb_name_stock_monitor_target

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="股票/ETF/港股代码")
    market: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        default="A",
        server_default="A",
        comment="市场: A / HK / ETF",
    )
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="触发条件JSON")
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="用户备注")
    frequency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="daily",
        server_default="daily",
        comment="监控频率: daily / intraday",
    )
    workflow: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="工作流所有者；手工目标为空")
    reset_mode: Mapped[str] = mapped_column(
        String(10),
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
