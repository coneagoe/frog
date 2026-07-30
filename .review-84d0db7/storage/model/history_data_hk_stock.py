from sqlalchemy import BigInteger, Column, Date, Float, String

from common.const import (
    COL_AMOUNT,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_TURNOVER_RATE,
    COL_VOLUME,
)

from .base import Base

tb_name_history_data_daily_hk_stock_hfq = "history_data_daily_hk_stock_hfq"
tb_name_history_data_weekly_hk_stock_hfq = "history_data_weekly_hk_stock_hfq"
tb_name_history_data_monthly_hk_stock_hfq = "history_data_monthly_hk_stock_hfq"


class HistoryDataDailyHkStockHFQ(Base):
    __tablename__ = tb_name_history_data_daily_hk_stock_hfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="成交额")
    振幅 = Column("振幅", Float, nullable=True, comment="振幅百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    涨跌额 = Column("涨跌额", Float, nullable=True, comment="涨跌额")
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")


class HistoryDataWeeklyHkStockHFQ(Base):
    __tablename__ = tb_name_history_data_weekly_hk_stock_hfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="成交额")
    振幅 = Column("振幅", Float, nullable=True, comment="振幅百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    涨跌额 = Column("涨跌额", Float, nullable=True, comment="涨跌额")
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")


class HistoryDataMonthlyHkStockHFQ(Base):
    __tablename__ = tb_name_history_data_monthly_hk_stock_hfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="成交额")
    振幅 = Column("振幅", Float, nullable=True, comment="振幅百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    涨跌额 = Column("涨跌额", Float, nullable=True, comment="涨跌额")
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
