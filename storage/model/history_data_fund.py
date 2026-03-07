from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_AMOUNT,
    COL_CHANGE,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_PRE_CLOSE,
    COL_VOLUME,
)

from .base import Base

tb_name_history_data_daily_fund = "history_data_daily_fund"


class HistoryDataDailyFund(Base):
    """Tushare fund_daily 接口的 ETF/基金日线行情数据"""

    __tablename__ = tb_name_history_data_daily_fund

    # YYYY-MM-DD
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    基金代码 = Column(
        COL_ETF_ID, String(10), primary_key=True, nullable=False, comment="基金代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价(元)")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价(元)")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价(元)")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价(元)")
    昨收盘 = Column(COL_PRE_CLOSE, Float, nullable=True, comment="昨收盘价(元)")
    涨跌额 = Column(COL_CHANGE, Float, nullable=True, comment="涨跌额(元)")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅(%)")
    成交量 = Column(COL_VOLUME, Float, nullable=True, comment="成交量(手)")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="成交额(千元)")
