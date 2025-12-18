from sqlalchemy import Column, String

from common.const import COL_STOCK_ID, COL_STOCK_NAME

from .base import Base

tb_name_ingredient_300 = "ingredient_300"
tb_name_ingredient_500 = "ingredient_500"


class Ingredient300(Base):
    __tablename__ = tb_name_ingredient_300

    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )
    股票名称 = Column(COL_STOCK_NAME, String(10), nullable=False, comment="股票名称")


class Ingredient500(Base):
    __tablename__ = tb_name_ingredient_500

    股票代码 = Column(
        COL_STOCK_ID, String(6), primary_key=True, nullable=False, comment="股票代码"
    )
    股票名称 = Column(COL_STOCK_NAME, String(10), nullable=False, comment="股票名称")
