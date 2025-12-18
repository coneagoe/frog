from sqlalchemy import Column, String

from common.const import COL_STOCK_ID, COL_STOCK_NAME

from .base import Base

tb_name_general_info_ggt = "general_info_hk_ggt"


class GeneralInfoGGT(Base):
    __tablename__ = tb_name_general_info_ggt

    股票代码 = Column(
        COL_STOCK_ID, String(5), primary_key=True, nullable=False, comment="股票代码"
    )
    股票名称 = Column(COL_STOCK_NAME, String(20), nullable=False, comment="股票名称")
