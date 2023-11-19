from datetime import date
import argparse
import pandas as pd
import plotly.express as px
import conf
from fund import *


# import logging
# logging.getLogger().setLevel(logging.DEBUG)

conf.parse_config()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int, default=120, help='how many days ago to show, default is 120')
    parser.add_argument('-s', type=str, help='start date, format: YYYY-M-D')
    parser.add_argument('-e', type=str, help='end date, format: YYYY-M-D')
    parser.add_argument('-i', type=str, nargs='*', default=None, help='fund id, default is None')
    args = parser.parse_args()

    start_date_str = args.s
    end_date_str = args.e
    n = args.n
    fund_ids = args.i

    if end_date_str is None:
        end_date_str = date.today().strftime('%Y-%m-%d')

    if start_date_str is None:
        start_date = pd.to_datetime(end_date_str) - pd.Timedelta(days=n)
        start_date_str = start_date.strftime('%Y-%m-%d')

    df_asset, df_profit, df_profit_rate = load_history_positions(start_date_str, end_date_str, fund_ids)

    fig = px.line(df_asset, title=col_asset)
    fig.show()

    fig = px.line(df_profit, title=col_profit)
    fig.show()

    fig = px.line(df_profit_rate, title=col_profit_rate)
    fig.show()
