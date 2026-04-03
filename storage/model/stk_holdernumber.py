from sqlalchemy import Column, Date, Integer, String

from common.const import COL_ANN_DATE, COL_END_DATE, COL_HOLDER_NUM, COL_STOCK_ID

from .base import Base

tb_name_stk_holdernumber = "stk_holdernumber"


class StkHoldernumber(Base):
    __tablename__ = tb_name_stk_holdernumber

    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )
    # YYYY-MM-DD
    公告日期 = Column(
        COL_ANN_DATE, Date, primary_key=True, nullable=False, comment="公告日期"
    )
    截止日期 = Column(COL_END_DATE, Date, nullable=True, comment="截止日期（报告期）")
    股东人数 = Column(COL_HOLDER_NUM, Integer, nullable=True, comment="股东人数（户）")
