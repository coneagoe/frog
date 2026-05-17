from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_ANN_DATE,
    COL_END_DATE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
    COL_STOCK_ID,
)

from .base import Base

tb_name_top10_floatholders = "top10_floatholders"


class Top10Floatholders(Base):
    __tablename__ = tb_name_top10_floatholders

    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )
    公告日期 = Column(
        COL_ANN_DATE, Date, primary_key=True, nullable=False, comment="公告日期"
    )
    股东名称 = Column(
        COL_FLOAT_HOLDER_NAME,
        String(255),
        primary_key=True,
        nullable=False,
        comment="股东名称",
    )
    截止日期 = Column(COL_END_DATE, Date, nullable=True, comment="截止日期（报告期）")
    持有数量 = Column(
        COL_FLOAT_HOLDER_HOLD_AMOUNT, Float, nullable=True, comment="持有数量（万股）"
    )
    持股比例 = Column(
        COL_FLOAT_HOLDER_HOLD_RATIO,
        Float,
        nullable=True,
        comment="占总流通股本持股比例",
    )
