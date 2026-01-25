from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_DATE,
    COL_DOWN_LIMIT,
    COL_PRE_CLOSE,
    COL_TS_CODE,
    COL_UP_LIMIT,
)

from .base import Base

tb_name_stk_limit_a_stock = "stk_limit_a_stock"


class StkLimitAStock(Base):
    __tablename__ = tb_name_stk_limit_a_stock

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_TS_CODE, String(10), primary_key=True, nullable=False, comment="TS股票代码"
    )

    昨日收盘价 = Column(COL_PRE_CLOSE, Float, nullable=True, comment="昨日收盘价")
    涨停价 = Column(COL_UP_LIMIT, Float, nullable=True, comment="涨停价")
    跌停价 = Column(COL_DOWN_LIMIT, Float, nullable=True, comment="跌停价")
