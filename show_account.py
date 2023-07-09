# -*- coding: utf-8 -*-
import os.path
from datetime import date
import argparse
import pandas as pd
import plotly.express as px
import conf


col_date = u'日期'


conf.config = conf.parse_config()
account_path = conf.config['account']['data_path']
account_path = os.path.join(account_path, u'账户.csv')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int, default=360, help='how many days ago to show, default is 120')
    parser.add_argument('-s', type=str, help='start date, format: YYYY-M-D')
    parser.add_argument('-e', type=str, help='end date, format: YYYY-M-D')
    args = parser.parse_args()

    start_date = args.s
    end_date = args.e
    n = args.n

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')

    df = pd.read_csv(account_path)
    df[col_date] = pd.to_datetime(df[col_date])
    df = df[(df[col_date] >= start_date) & (df[col_date] <= end_date)]

    fig = px.line(df, x=col_date, y=df.columns[1:], title=u'账户')
    fig.show()