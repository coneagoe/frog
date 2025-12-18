from sqlalchemy import Column, String

from common.const import COL_STOCK_ID, COL_STOCK_NAME

from .base import Base

tb_name_general_info_stock = "general_info_stock"


class GeneralInfoStock(Base):
    __tablename__ = tb_name_general_info_stock

    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )
    股票名称 = Column(COL_STOCK_NAME, String(10), nullable=False, comment="股票名称")
