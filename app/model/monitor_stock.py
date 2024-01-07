from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped
from stock import (
    COL_STOCK_ID,
    COL_STOCK_NAME,
    COL_MONITOR_PRICE,
    COL_COMMENT
)
from . import db


table_name_monitor_stock = 'monitor_stock'


class MonitorStock(db.Model):
    __tablename__ = table_name_monitor_stock

    id: Mapped[int] = Column(Integer, primary_key=True)
    stock_id: Mapped[str] = Column(String(6), name=COL_STOCK_ID, nullable=False)
    stock_name: Mapped[str] = Column(String(20), name=COL_STOCK_NAME, nullable=False)
    monitor_price: Mapped[str] = Column(String(10), name=COL_MONITOR_PRICE, nullable=False)
    comment: Mapped[str] = Column(String, name=COL_COMMENT)

    def __repr__(self):
        return f"<MonitorStock(stock_id={self.stock_id}, stock_name={self.stock_name}, " \
               f"monitor_price={self.monitor_price}, comment={self.comment})>"
