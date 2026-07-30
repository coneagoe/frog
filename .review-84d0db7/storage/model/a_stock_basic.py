from sqlalchemy import Column, Date, String

from common.const import (
    COL_ACT_ENT_TYPE,
    COL_ACT_NAME,
    COL_AREA,
    COL_CN_SPELL,
    COL_CURR_TYPE,
    COL_DELISTING_DATE,
    COL_ENNAME,
    COL_EXCHANGE,
    COL_FULLNAME,
    COL_INDUSTRY,
    COL_IPO_DATE,
    COL_IS_HS,
    COL_LIST_STATUS,
    COL_MARKET,
    COL_STOCK_ID,
    COL_STOCK_NAME,
)

from .base import Base

tb_name_a_stock_basic = "a_stock_basic"


class AStockBasic(Base):
    __tablename__ = tb_name_a_stock_basic

    股票代码 = Column(
        COL_STOCK_ID,
        String(6),
        primary_key=True,
        nullable=False,
        comment="股票代码",
    )
    股票名称 = Column(COL_STOCK_NAME, String(40), nullable=False, comment="股票名称")

    地域 = Column(COL_AREA, String(20), nullable=True, comment="地域")
    所属行业 = Column(COL_INDUSTRY, String(40), nullable=True, comment="所属行业")
    股票全称 = Column(COL_FULLNAME, String(100), nullable=True, comment="股票全称")
    英文全称 = Column(COL_ENNAME, String(100), nullable=True, comment="英文全称")
    拼音缩写 = Column(COL_CN_SPELL, String(20), nullable=True, comment="拼音缩写")

    市场类型 = Column(COL_MARKET, String(20), nullable=True, comment="市场类型")
    交易所 = Column(COL_EXCHANGE, String(10), nullable=True, comment="交易所")
    交易货币 = Column(COL_CURR_TYPE, String(10), nullable=True, comment="交易货币")

    上市状态 = Column(COL_LIST_STATUS, String(2), nullable=True, comment="上市状态")
    # YYYY-MM-DD
    上市日期 = Column(COL_IPO_DATE, Date, nullable=True, comment="上市日期")
    退市日期 = Column(COL_DELISTING_DATE, Date, nullable=True, comment="退市日期")

    是否沪深港通 = Column(COL_IS_HS, String(2), nullable=True, comment="是否沪深港通")
    实控人姓名 = Column(COL_ACT_NAME, String(40), nullable=True, comment="实控人姓名")
    实控人企业性质 = Column(
        COL_ACT_ENT_TYPE, String(20), nullable=True, comment="实控人企业性质"
    )
