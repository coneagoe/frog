import argparse
from datetime import (
    date,
    datetime,
    timedelta
)
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402
import plotly.graph_objs as go  # noqa: E402

import conf     # noqa: E402
from stock import (
    get_security_name,
    get_last_trading_day,
    load_history_data,
    COL_DATE,
    COL_CLOSE,
)   # noqa: E402


conf.parse_config()


def show_two_securities(stock_id_0: str, df0: pd.DataFrame, stock_id_1: str, df1: pd.DataFrame):
    stock_name_0 = get_security_name(stock_id_0)
    stock_name_1 = get_security_name(stock_id_1)

    df = pd.merge(df0, df1, on=COL_DATE, suffixes=('_0', '_1'))
    avg_close = (df[COL_CLOSE + '_0'] + df[COL_CLOSE + '_1']) / 2

    fig = go.Figure()

    fig.add_trace(go.Scatter(x=df0[COL_DATE], y=df0[COL_CLOSE], mode='lines', name=stock_name_0, yaxis='y'))
    fig.add_trace(go.Scatter(x=df1[COL_DATE], y=df1[COL_CLOSE], mode='lines', name=stock_name_1, yaxis='y2'))
    fig.add_trace(go.Scatter(x=df[COL_DATE], y=avg_close, mode='lines', name='Average', yaxis='y3'))

    fig.update_layout(yaxis=dict(title=stock_name_0),
                      yaxis2=dict(title=stock_name_1, overlaying='y', side='right'),
                      yaxis3=dict(title='Average', overlaying='y', side='left'))

    fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', default=360, type=int,
                        help='since how many days ago to compare, cannot be used together with -s and -e')
    parser.add_argument('-s', "--start", type=str, help='start date, YYYYMMDD')
    parser.add_argument('-e', "--end", type=str, help='end date, YYYYMMDD')
    parser.add_argument('-t', '--template', help='The template file to read securities from.')
    parser.add_argument('security_id_0', nargs='?', type=str,
                        help='can be .IXIC(NASDAQ Composite), .DJI(Dow Jones Industrial Average) and .INX(S&P 500)')
    parser.add_argument('security_id_1', nargs='?', type=str)
    args = parser.parse_args()

    if args.template:
        if not os.path.exists(args.template):
            print(f'The template file {args.template} does not exist.')
            exit()

        with open(args.template, 'r') as f:
            args.security_id_0, args.security_id_1 = f.readline().split()
    elif not (args.security_id_0 and args.security_id_1):
        parser.error('You must specify both security_id_0 and security_id_1, or use the -t option.')
        exit()

    security_id_0 = args.security_id_0
    security_id_1 = args.security_id_1
    start_date = args.start
    end_date = args.end

    if end_date is None:
        end_date = get_last_trading_day()

    if start_date is None:
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')
        start_date = (end_date_dt - timedelta(days=args.n)).strftime('%Y-%m-%d')

    df0 = load_history_data(security_id=security_id_0, period='daily',
                                  start_date=start_date, end_date=end_date)
    df1 = load_history_data(security_id=security_id_1, period='daily',
                                  start_date=start_date, end_date=end_date)

    show_two_securities(security_id_0, df0, security_id_1, df1)
