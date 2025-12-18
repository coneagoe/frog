from sqlalchemy import BigInteger, Column, Date, Float, Integer, String

from common.const import (
    COL_AMOUNT,
    COL_CHANGE_RATE,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_IS_ST,
    COL_LOW,
    COL_OPEN,
    COL_PB_MRQ,
    COL_PCF_NCF_TTM,
    COL_PE_TTM,
    COL_PS_TTM,
    COL_STOCK_ID,
    COL_TURNOVER_RATE,
    COL_VOLUME,
)

from .base import Base

tb_name_history_data_daily_a_stock_qfq = "history_data_daily_a_stock_qfq"
tb_name_history_data_daily_a_stock_hfq = "history_data_daily_a_stock_hfq"
tb_name_history_data_weekly_a_stock_qfq = "history_data_weekly_a_stock_qfq"
tb_name_history_data_weekly_a_stock_hfq = "history_data_weekly_a_stock_hfq"

tb_name_history_data_daily_etf_qfq = "history_data_daily_etf_qfq"
tb_name_history_data_daily_etf_hfq = "history_data_daily_etf_hfq"
tb_name_history_data_weekly_etf_qfq = "history_data_weekly_etf_qfq"
tb_name_history_data_weekly_etf_hfq = "history_data_weekly_etf_hfq"


class HistoryDataDailyAStockQFQ(Base):
    __tablename__ = tb_name_history_data_daily_a_stock_qfq

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
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    市盈率_TTM = Column(COL_PE_TTM, Float, nullable=True, comment="市盈率(TTM)")
    市净率_MRQ = Column(COL_PB_MRQ, Float, nullable=True, comment="市净率(MRQ)")
    市销率_TTM = Column(COL_PS_TTM, Float, nullable=True, comment="市销率(TTM)")
    市现率_TTM = Column(COL_PCF_NCF_TTM, Float, nullable=True, comment="市现率(TTM)")
    是否ST = Column(COL_IS_ST, Integer, nullable=True, comment="是否ST股")


class HistoryDataDailyAStockHFQ(Base):
    __tablename__ = tb_name_history_data_daily_a_stock_hfq

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
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    市盈率_TTM = Column(COL_PE_TTM, Float, nullable=True, comment="市盈率(TTM)")
    市净率_MRQ = Column(COL_PB_MRQ, Float, nullable=True, comment="市净率(MRQ)")
    市销率_TTM = Column(COL_PS_TTM, Float, nullable=True, comment="市销率(TTM)")
    市现率_TTM = Column(COL_PCF_NCF_TTM, Float, nullable=True, comment="市现率(TTM)")
    是否ST = Column(COL_IS_ST, Integer, nullable=True, comment="是否ST股")


class HistoryDataWeeklyAStockQFQ(Base):
    __tablename__ = tb_name_history_data_weekly_a_stock_qfq

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
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")


class HistoryDataWeeklyAStockHFQ(Base):
    __tablename__ = tb_name_history_data_weekly_a_stock_hfq

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
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")


class HistoryDataDailyEtfQFQ(Base):
    __tablename__ = tb_name_history_data_daily_etf_qfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")


class HistoryDataDailyEtfHFQ(Base):
    __tablename__ = tb_name_history_data_daily_etf_hfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")


class HistoryDataWeeklyEtfQFQ(Base):
    __tablename__ = tb_name_history_data_weekly_etf_qfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")


class HistoryDataWeeklyEtfHFQ(Base):
    __tablename__ = tb_name_history_data_weekly_etf_hfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码"
    )
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")
