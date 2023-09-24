from sqlalchemy import Column, Integer, String
from . const import col_stock_id, col_stock_name, col_monitor_price


class MonitorStock(db.Model):
    __tablename__ = 'monitor_stock'

    id = Column(Integer, primary_key=True)
    stock_id = Column(String(6), name=col_stock_id, nullable=False)
    stock_name = Column(String(20), name=col_stock_name, nullable=False)
    monitor_price = Column(String(10), name=col_monitor_price, nullable=False)
    comment = Column(String(50))

    def __repr__(self):
        return f"<MonitorStock(stock_id={self.stock_id}, stock_name={self.stock_name}, " \
               f"monitor_price={self.monitor_price}, comment={self.comment})>"
