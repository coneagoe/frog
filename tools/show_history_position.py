import argparse
import os.path
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402

import conf  # noqa: E402
import fund  # noqa: E402
import stock  # noqa: E402

conf.parse_config()


def show_stock_history_position(start_date: str, end_date: str, stock_ids: tuple):
    df_asset, df_profit, df_profit_rate = stock.load_history_positions(
        start_date, end_date, stock_ids
    )
    fig = px.line(df_asset, title=stock.COL_MARKET_VALUE)
    fig.show()
    fig = px.line(df_profit, title=stock.COL_PROFIT)
    fig.show()
    fig = px.line(df_profit_rate, title=stock.COL_PROFIT_RATE)
    fig.show()


def show_fund_history_position(start_date: str, end_date: str, fund_ids: tuple):
    df_asset, df_profit, df_profit_rate = fund.load_history_positions(
        start_date, end_date, fund_ids
    )
    fig = px.line(df_asset, title=fund.COL_ASSET)
    fig.show()
    fig = px.line(df_profit, title=fund.COL_PROFIT)
    fig.show()
    fig = px.line(df_profit_rate, title=fund.COL_PROFIT_RATE)
    fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n", type=int, default=120, help="how many days ago to show, default is 120"
    )
    parser.add_argument("-s", type=str, help="start date, format: YYYY-M-D")
    parser.add_argument("-e", type=str, help="end date, format: YYYY-M-D")
    parser.add_argument(
        "-i", type=str, nargs="*", default=None, help="security ids, default is None"
    )
    parser.add_argument("-t", type=str, required=True, help="stock or fund")
    args = parser.parse_args()

    start_date_str = args.s
    end_date_str = args.e
    n = args.n
    security_ids = args.i

    if end_date_str is None:
        end_date_str = date.today().strftime("%Y-%m-%d")

    if start_date_str is None:
        start_date = pd.to_datetime(end_date_str) - pd.Timedelta(days=n)
        start_date_str = start_date.strftime("%Y-%m-%d")

    if args.t == "fund":
        show_fund_history_position(start_date_str, end_date_str, security_ids)
    elif args.t == "stock":
        show_stock_history_position(start_date_str, end_date_str, security_ids)
    else:
        print(f"unknown type: {args.t}")
