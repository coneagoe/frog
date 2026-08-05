from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_ANN_DATE,
    COL_END_DATE,
    COL_FORECAST_CHANGE_MAX,
    COL_FORECAST_CHANGE_MIN,
    COL_FORECAST_TYPE,
    COL_STOCK_ID,
)

from .base import Base

tb_name_forecast = "forecasts"


class Forecast(Base):
    __tablename__ = tb_name_forecast

    股票代码 = Column(COL_STOCK_ID, String(6), primary_key=True, nullable=False)
    公告日期 = Column(COL_ANN_DATE, Date, primary_key=True, nullable=False)
    截止日期 = Column(COL_END_DATE, Date, primary_key=True, nullable=False)
    预告类型 = Column(COL_FORECAST_TYPE, String(20), nullable=False)
    增长下限 = Column(COL_FORECAST_CHANGE_MIN, Float, nullable=True)
    增长上限 = Column(COL_FORECAST_CHANGE_MAX, Float, nullable=True)
