from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_CIRC_MV,
    COL_CLOSE,
    COL_DATE,
    COL_DV_RATIO,
    COL_DV_TTM,
    COL_FLOAT_SHARE,
    COL_FREE_SHARE,
    COL_PB,
    COL_PE,
    COL_PE_TTM,
    COL_PS,
    COL_PS_TTM,
    COL_STOCK_ID,
    COL_TOTAL_MV,
    COL_TOTAL_SHARE,
    COL_TURNOVER_RATE,
    COL_TURNOVER_RATE_F,
    COL_VOLUME_RATIO,
)

from .base import Base

tb_name_daily_basic_a_stock = "daily_basic_a_stock"


class DailyBasicAStock(Base):
    __tablename__ = tb_name_daily_basic_a_stock

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )

    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="当日收盘价")
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率(%)")
    自由流通换手率 = Column(
        COL_TURNOVER_RATE_F, Float, nullable=True, comment="自由流通换手率(%)"
    )
    量比 = Column(COL_VOLUME_RATIO, Float, nullable=True, comment="量比")

    市盈率 = Column(COL_PE, Float, nullable=True, comment="市盈率")
    市盈率_TTM = Column(COL_PE_TTM, Float, nullable=True, comment="市盈率(TTM)")

    市净率 = Column(COL_PB, Float, nullable=True, comment="市净率")

    市销率 = Column(COL_PS, Float, nullable=True, comment="市销率")
    市销率_TTM = Column(COL_PS_TTM, Float, nullable=True, comment="市销率(TTM)")

    股息率 = Column(COL_DV_RATIO, Float, nullable=True, comment="股息率(%)")
    股息率_TTM = Column(COL_DV_TTM, Float, nullable=True, comment="股息率(TTM)")

    总股本 = Column(COL_TOTAL_SHARE, Float, nullable=True, comment="总股本")
    流通股本 = Column(COL_FLOAT_SHARE, Float, nullable=True, comment="流通股本")
    自由流通股本 = Column(COL_FREE_SHARE, Float, nullable=True, comment="自由流通股本")

    总市值 = Column(COL_TOTAL_MV, Float, nullable=True, comment="总市值")
    流通市值 = Column(COL_CIRC_MV, Float, nullable=True, comment="流通市值")
