from os.path import basename
import sys
import argparse
from datetime import date
import pandas as pd
import akshare as ak
from stock import *
import plotly.graph_objs as go


conf.config = conf.parse_config()


def load_data(stock_id: str, start_date: str, end_date: str):
    stock_name = get_stock_name(stock_id)
    if stock_name:
        df = ak.stock_zh_a_hist(symbol=stock_id, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="")
        return stock_name, df

    etf_name = get_etf_name(stock_id)
    if etf_name:
        df = ak.fund_etf_hist_em(symbol=stock_id, period="daily",
                                 start_date=start_date, end_date=end_date,
                                 adjust="")
        return etf_name, df

    logging.error(f"wrong stock id({stock_id}), please check.")
    exit()


def show_two_securities(stock_name_0: str, df0: pd.DataFrame, stock_name_1: str, df1: pd.DataFrame):
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=df0[col_date], y=df0[col_close], mode='lines', name=stock_name_0, yaxis='y'))
    fig.add_trace(go.Scatter(x=df1[col_date], y=df1[col_close], mode='lines', name=stock_name_1, yaxis='y2'))
    fig.update_layout(yaxis=dict(title=stock_name_0),
                      yaxis2=dict(title=stock_name_1, overlaying='y', side='right'))

    fig.show()


def usage():
    print(f"{basename(__file__)} [-n days] [-s start_date] [-e end_date] <stock_id_0> <stock_id_1>")
    print("-n days: since how many days ago, cannot be used together with -s and -e. default is 120")
    print("start_date/end_date: YYYYMMDD")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int)
    parser.add_argument('-s', type=str)
    parser.add_argument('-e', type=str)
    parser.add_argument('start_id_0', type=str)
    parser.add_argument('start_id_1', type=str)
    args = parser.parse_args()

    stock_id_0 = args.start_id_0
    stock_id_1 = args.start_id_1
    start_date = args.s
    end_date = args.e
    n = args.n if args.n else 120

    if stock_id_0 is None or stock_id_1 is None:
        usage()
        exit()

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y%m%d')
        end_date = end_date.strftime('%Y%m%d')

    stock_name_0, df0 = load_data(stock_id_0, start_date, end_date)
    stock_name_1, df1 = load_data(stock_id_1, start_date, end_date)
    show_two_securities(stock_name_0, df0, stock_name_1, df1)
