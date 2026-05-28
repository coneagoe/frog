from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, text
from sqlalchemy.sql import func

from .base import Base

tb_name_blackroom_record = "blackroom_records"


class BlackroomRecord(Base):
    __tablename__ = tb_name_blackroom_record

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    stock_code = Column(String(10), nullable=False, comment="股票/ETF/港股代码")
    market = Column(
        String(5),
        nullable=False,
        default="A",
        server_default="A",
        comment="市场: A / HK / ETF",
    )
    ban_days = Column(
        Integer, nullable=True, comment="禁买时长（天），NULL 表示未设定时长"
    )
    start_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="禁买开始时间，默认为创建时间",
    )
    expire_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="到期时间，由 start_at + ban_days 计算；NULL 表示无有效到期时间（active 查询不含此类记录）",
    )
    source = Column(
        String(50),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="来源: manual / shareholder_reduction 等",
    )
    note = Column(Text, nullable=True, comment="备注或禁买原因")
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间",
    )
