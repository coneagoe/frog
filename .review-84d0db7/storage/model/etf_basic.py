from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_CUSTOD_NAME,
    COL_ETF_ID,
    COL_ETF_NAME,
    COL_ETF_TYPE,
    COL_EXCHANGE,
    COL_FULLNAME,
    COL_INDEX_CODE,
    COL_INDEX_NAME,
    COL_IPO_DATE,
    COL_LIST_STATUS,
    COL_MGR_NAME,
    COL_MGT_FEE,
    COL_SETUP_DATE,
)

from .base import Base

tb_name_etf_basic = "etf_basic"


class ETFBasic(Base):
    __tablename__ = tb_name_etf_basic

    基金代码 = Column(
        COL_ETF_ID,
        String(6),
        primary_key=True,
        nullable=False,
        comment="ETF代码",
    )
    中文简称 = Column(COL_ETF_NAME, String(40), nullable=False, comment="ETF中文简称")
    扩位简称 = Column(String(40), nullable=True, comment="ETF扩位简称")
    中文全称 = Column(COL_FULLNAME, String(100), nullable=True, comment="基金中文全称")

    指数代码 = Column(
        COL_INDEX_CODE, String(10), nullable=True, comment="ETF基准指数代码"
    )
    指数名称 = Column(
        COL_INDEX_NAME, String(20), nullable=True, comment="ETF基准指数中文全称"
    )

    设立日期 = Column(COL_SETUP_DATE, Date, nullable=True, comment="设立日期")
    上市日期 = Column(COL_IPO_DATE, Date, nullable=True, comment="上市日期")
    存续状态 = Column(COL_LIST_STATUS, String(2), nullable=True, comment="存续状态")

    交易所 = Column(COL_EXCHANGE, String(10), nullable=True, comment="交易所")

    基金管理人 = Column(
        COL_MGR_NAME, String(40), nullable=True, comment="基金管理人简称"
    )
    基金托管人 = Column(
        COL_CUSTOD_NAME, String(40), nullable=True, comment="基金托管人名称"
    )

    管理费 = Column(COL_MGT_FEE, Float, nullable=True, comment="基金管理人收取的费用")
    ETF类型 = Column(
        COL_ETF_TYPE, String(20), nullable=True, comment="基金投资通道类型"
    )
