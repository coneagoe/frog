from sqlalchemy import Column, Integer, String, Boolean


class MonitorStock:
    __tablename__ = 'monitor_stock'

    id = Column(Integer, primary_key=True)
    stock_id = Column(String(6), nullable=False)
    stock_name = Column(String(20), nullable=False)
    current_price = Column(String(10), nullable=True)
    monitor_price = Column(String(10), nullable=False)
    email = Column(Boolean, nullable=False)
    mobile = Column(Boolean, nullable=False)
    pc = Column(Boolean, nullable=False)
    comment = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<MonitorStock(stock_id={self.stock_id}, " \"monitor_price={self.monitor_price}, " \
               f"email={self.email}, mobile={self.mobile}, pc={self.pc}, comment={self.comment})>"
