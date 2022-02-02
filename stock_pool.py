# -*- coding: utf-8 -*-
from sqlalchemy import create_engine, Column, String, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
import dash
import dash_html_components as html
import dash_table
import pandas as pd


engine = create_engine('sqlite:///tmp.db', echo=True)
Base = declarative_base()


class Stock(Base):
    __tablename__ = 'stock_pool'
    code = Column(String, primary_key=True)
    name = Column(String)
    target_price = Column(Numeric)

    def __repr__(self):
        return f"code: {self.code}, name: {self.name}, target: {self.target_price}"


df = pd.read_sql_table(table_name='stock_pool', con=engine, index_col='code')
print(df)

exit(0)

session = Session(bind=engine)


external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

stock = Stock(code='601318', name=u'中国平安', target_price=float(80.1))
session.add(stock)
session.commit()
for stock in session.query(Stock):
    print(stock)