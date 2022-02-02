# -*- coding: utf-8 -*-
import pandas as pd
import dash
#from dash.dependencies import Input, Output
import dash_html_components as html
#import dash_core_components as dcc
import dash_table
from sqlalchemy import create_engine, Column, String, Float, Table, MetaData, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

account_table_name = 'account'

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

engine = create_engine('sqlite:///tmp.db', echo=True)
if not engine.dialect.has_table(engine, account_table_name):
    meta = MetaData()

    account_table = Table(
        account_table_name, meta,
        Column('id', Integer, primary_key=True),
        Column(u'账户', String),
        Column(u'资金', Float)
    )
    meta.create_all(engine)

exit()

df = pd.read_csv('account.csv',encoding='GBK')

app.layout = html.Div([
    html.H1(u'账户'),
    dash_table.DataTable(
        id='account_table',
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.to_dict('records'),
    ),
])


if __name__ == '__main__':
    app.run_server(debug=True)