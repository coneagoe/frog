from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
)

from .base import Base

tb_name_etf_net_flow = "etf_net_flow"


class ETFNetFlow(Base):
    __tablename__ = tb_name_etf_net_flow

    基金代码 = Column(COL_ETF_ID, String(6), primary_key=True, nullable=False, comment="ETF代码")
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    总份额 = Column(
        COL_ETF_TOTAL_SHARE,
        Float,
        nullable=False,
        comment="Tushare etf_share_size total_share，原始单位",
    )
    上一有效总份额 = Column(
        COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
        Float,
        nullable=False,
        comment="上一有效Tushare total_share，原始单位",
    )
    净份额变动 = Column(
        COL_ETF_NET_SHARE_CHANGE,
        Float,
        nullable=False,
        comment="当日总份额 - 上一有效总份额，原始单位",
    )
    估算成交均价 = Column(COL_ETF_ESTIMATED_TRADED_PRICE, Float, nullable=False, comment="ETF估算成交均价，元/份")
    净申赎金额 = Column(COL_ETF_NET_FLOW_AMOUNT, Float, nullable=False, comment="估算净申赎金额，元")
    指数代码 = Column(COL_INDEX_CODE, String(9), nullable=False, comment="映射指数Tushare代码")
    指数成交额 = Column(
        COL_INDEX_TURNOVER_AMOUNT,
        Float,
        nullable=True,
        comment="Tushare index_daily amount，成交额（千元）",
    )
    净申赎金额占指数成交额 = Column(
        COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
        Float,
        nullable=True,
        comment="净申赎金额 / 指数成交额（同为元）",
    )
