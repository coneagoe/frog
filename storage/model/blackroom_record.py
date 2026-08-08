from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, text
from sqlalchemy.sql import func

from storage.domain_enums import BlackroomMarket, BlackroomSource

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_blackroom_record = "blackroom_records"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class BlackroomRecord(Base):
    __tablename__ = tb_name_blackroom_record

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    stock_code: Mapped[str] = mapped_column(String(10), nullable=False, comment="股票/ETF/港股代码")
    market: Mapped[str] = mapped_column(
        _value_enum(BlackroomMarket, "blackroom_market"),
        nullable=False,
        default="A",
        server_default="A",
        comment="市场: A / HK / ETF",
    )
    ban_days: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="禁买时长（天），NULL 表示未设定时长")
    remaining_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="剩余禁买天数；大于 0 表示仍处于倒计时封禁期",
    )
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="禁买开始时间，默认为创建时间",
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="到期时间，由 start_at + ban_days 计算；NULL 表示无有效到期时间（active 查询不含此类记录）",
    )
    source: Mapped[str] = mapped_column(
        _value_enum(BlackroomSource, "blackroom_source"),
        nullable=False,
        default="manual",
        server_default="manual",
        comment="来源: manual / shareholder_selling 等",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注或禁买原因")
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment="是否启用",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间",
    )
