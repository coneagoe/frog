from datetime import date
import argparse
import pandas as pd
import plotly.express as px
import conf
from stock import *


# import logging
# logging.getLogger().setLevel(logging.DEBUG)

conf.config = conf.parse_config()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int, default=120, help='how many days ago to show, default is 120')
    parser.add_argument('-s', type=str, help='start date, format: YYYY-M-D')
    parser.add_argument('-e', type=str, help='end date, format: YYYY-M-D')
    parser.add_argument('-i', type=str, nargs='*', default=None, help='stock id, default is None')
    args = parser.parse_args()

    start_date = args.s
    end_date = args.e
    n = args.n
    stock_ids = args.i

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')

    df_asset, df_profit, df_profit_rate = load_history_positions(start_date, end_date, stock_ids)

    fig = px.line(df_asset, title=col_market_value)
    fig.show()

    fig = px.line(df_profit, title=col_profit)
    fig.show()

    fig = px.line(df_profit_rate, title=col_profit_rate)
    fig.show()
