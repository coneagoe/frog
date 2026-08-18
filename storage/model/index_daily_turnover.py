from sqlalchemy import Column, Date, Float, String

from common.const import COL_AMOUNT, COL_CLOSE, COL_DATE, COL_INDEX_CODE

from .base import Base

tb_name_index_daily_turnover = "index_daily_turnover"


class IndexDailyTurnover(Base):
    __tablename__ = tb_name_index_daily_turnover

    指数代码 = Column(COL_INDEX_CODE, String(9), primary_key=True, nullable=False, comment="Tushare指数代码")
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="Tushare index_daily close，收盘点位")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="Tushare index_daily amount，成交额（千元）")
