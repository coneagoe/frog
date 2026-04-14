from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base

tb_name_stock_monitor_target = "stock_monitor_targets"


class StockMonitorTarget(Base):
    __tablename__ = tb_name_stock_monitor_target

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    stock_code = Column(String(10), nullable=False, comment="股票/ETF/港股代码")
    market = Column(
        String(5),
        nullable=False,
        default="A",
        server_default="A",
        comment="市场: A / HK / ETF",
    )
    condition = Column(JSONB, nullable=False, comment="触发条件JSON")
    note = Column(Text, nullable=True, comment="用户备注")
    frequency = Column(
        String(10),
        nullable=False,
        default="daily",
        server_default="daily",
        comment="监控频率: daily / intraday",
    )
    reset_mode = Column(
        String(10),
        nullable=False,
        default="auto",
        server_default="auto",
        comment="重置模式: auto / manual",
    )
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    last_state = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="上次条件是否成立（边沿触发用）",
    )
    triggered_at = Column(
        DateTime(timezone=True), nullable=True, comment="最近触发时间"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
