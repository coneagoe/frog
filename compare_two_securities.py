from os.path import basename
import argparse
from datetime import date
import pandas as pd
import plotly.graph_objs as go
import conf
from stock import (
    get_security_name,
    col_date,
    col_close,
    load_history_data
)


conf.parse_config()


def show_two_securities(stock_id_0: str, df0: pd.DataFrame, stock_id_1: str, df1: pd.DataFrame):
    stock_name_0 = get_security_name(stock_id_0)
    stock_name_1 = get_security_name(stock_id_1)

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=df0[col_date], y=df0[col_close], mode='lines', name=stock_name_0, yaxis='y'))
    fig.add_trace(go.Scatter(x=df1[col_date], y=df1[col_close], mode='lines', name=stock_name_1, yaxis='y2'))
    fig.update_layout(yaxis=dict(title=stock_name_0),
                      yaxis2=dict(title=stock_name_1, overlaying='y', side='right'))

    fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', default=360, type=int,
                        help='since how many days ago to compare, cannot be used together with -s and -e')
    parser.add_argument('-s', type=str, help='start date, YYYYMMDD')
    parser.add_argument('-e', type=str, help='end date, YYYYMMDD')
    parser.add_argument('security_id_0', type=str,
                        help='can be .IXIC(NASDAQ Composite), .DJI(Dow Jones Industrial Average) and .INX(S&P 500)')
    parser.add_argument('security_id_1', type=str)
    args = parser.parse_args()

    security_id_0 = args.security_id_0
    security_id_1 = args.security_id_1
    start_date = args.s
    end_date = args.e

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=args.n)
        start_date = start_date.strftime('%Y%m%d')
        end_date = end_date.strftime('%Y%m%d')

    df0 = load_history_data(security_id_0, start_date, end_date)
    df1 = load_history_data(security_id_1, start_date, end_date)

    show_two_securities(security_id_0, df0, security_id_1, df1)
