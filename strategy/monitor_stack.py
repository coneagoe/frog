from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Mapped
from stock import monitor_stock_table_name, col_stock_id, col_stock_name, \
    col_monitor_price, col_comment
from db import db


class MonitorStock(db.Model):
    __tablename__ = monitor_stock_table_name

    id: Mapped[int] = Column(Integer, primary_key=True)
    stock_id: Mapped[str] = Column(String(6), name=col_stock_id, nullable=False)
    stock_name: Mapped[str] = Column(String(20), name=col_stock_name, nullable=False)
    monitor_price: Mapped[str] = Column(String(10), name=col_monitor_price, nullable=False)
    comment: Mapped[str] = Column(String, name=col_comment)

    def __repr__(self):
        return f"<MonitorStock(stock_id={self.stock_id}, stock_name={self.stock_name}, " \
               f"monitor_price={self.monitor_price}, comment={self.comment})>"

