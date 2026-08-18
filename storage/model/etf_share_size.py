from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_CLOSE,
    COL_DATE,
    COL_ETF_ID,
    COL_ETF_TOTAL_SHARE,
    COL_ETF_TOTAL_SIZE,
    COL_NAV,
)

from .base import Base

tb_name_etf_share_size = "etf_share_size"


class ETFShareSize(Base):
    __tablename__ = tb_name_etf_share_size

    基金代码 = Column(COL_ETF_ID, String(6), primary_key=True, nullable=False, comment="ETF代码")
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    收盘价 = Column(COL_CLOSE, Float, nullable=True, comment="Tushare etf_share_size close，原始单位")
    单位净值 = Column(COL_NAV, Float, nullable=True, comment="Tushare etf_share_size nav，原始单位")
    总份额 = Column(
        COL_ETF_TOTAL_SHARE,
        Float,
        nullable=True,
        comment="Tushare etf_share_size total_share，原始单位",
    )
    总规模 = Column(
        COL_ETF_TOTAL_SIZE,
        Float,
        nullable=True,
        comment="Tushare etf_share_size total_size，原始单位",
    )
