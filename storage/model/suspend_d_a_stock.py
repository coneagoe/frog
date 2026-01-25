from sqlalchemy import Column, Date, String

from common.const import (
    COL_DATE,
    COL_SUSPEND_TIMING,
    COL_SUSPEND_TYPE,
    COL_TS_CODE,
)

from .base import Base

tb_name_suspend_d_a_stock = "suspend_d_a_stock"


class SuspendDAStock(Base):
    __tablename__ = tb_name_suspend_d_a_stock

    股票代码 = Column(
        COL_TS_CODE, String(10), primary_key=True, nullable=False, comment="TS股票代码"
    )
    停复牌日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="停复牌日期")
    停牌时间段 = Column(COL_SUSPEND_TIMING, String(20), nullable=True, comment="日内停牌时间段")
    停复牌类型 = Column(COL_SUSPEND_TYPE, String(1), nullable=True, comment="停复牌类型：S-停牌，R-复牌")
