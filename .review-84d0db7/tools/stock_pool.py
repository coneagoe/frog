# -*- coding: utf-8 -*-
import dash
import pandas as pd
from sqlalchemy import Column, Numeric, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

engine = create_engine("sqlite:///tmp.db", echo=True)
Base = declarative_base()


class Stock(Base):  # type: ignore[misc, valid-type]
    __tablename__ = "stock_pool"
    code = Column(String, primary_key=True)
    name = Column(String)
    target_price = Column(Numeric)

    def __repr__(self):
        return f"code: {self.code}, name: {self.name}, target: {self.target_price}"


stocks_general_info = pd.read_sql_table(
    table_name="stock_pool", con=engine, index_col="code"
)
print(stocks_general_info)

exit(0)

session = Session(bind=engine)


external_stylesheets = ["https://codepen.io/chriddyp/pen/bWLwgP.css"]
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

stock = Stock(code="601318", name="中国平安", target_price=float(80.1))
session.add(stock)
session.commit()
for stock in session.query(Stock):
    print(stock)
