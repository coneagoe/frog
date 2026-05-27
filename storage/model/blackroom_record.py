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
    reason = Column(Text, nullable=True, comment="禁止买入原因")
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    expire_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="到期时间（NULL 表示永不过期）",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
