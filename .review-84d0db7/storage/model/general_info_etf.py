from sqlalchemy import Column, String

from common.const import COL_ETF_ID, COL_ETF_NAME

from .base import Base

tb_name_general_info_etf = "general_info_etf"


class GeneralInfoETF(Base):
    __tablename__ = tb_name_general_info_etf

    基金代码 = Column(
        COL_ETF_ID, String(6), primary_key=True, nullable=False, comment="ETF代码"
    )
    拼音缩写 = Column(String(20), nullable=False, comment="拼音缩写")
    基金简称 = Column(COL_ETF_NAME, String(20), nullable=False, comment="ETF简称")
    基金类型 = Column(String(20), nullable=False, comment="基金类型")
    拼音全称 = Column(String(50), nullable=False, comment="拼音全称")
