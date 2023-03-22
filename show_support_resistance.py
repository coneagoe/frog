from os.path import basename
import sys
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


def draw_support_resistance(stock_name: str, df: pd.DataFrame,
                            turning_points, support_point, resistance_point):
    fig = go.Figure()
    fig.update_layout(title={
        'text': f"{stock_name}",
        'y': 0.9,
        'x': 0.5,
        'xanchor': 'center',
        'yanchor': 'top'})
    fig.add_trace(go.Scatter(x=df[col_date], y=df[col_close], mode='lines', name='股价'))
    fig.add_trace(go.Scatter(x=df[col_date][turning_points], y=df[col_close][turning_points],
                             mode='markers', name='拐点'))

    current_price = df[col_close].iloc[-1]
    if resistance_point:
        fig.add_shape(type="rect",
                      x0=df[col_date][resistance_point],
                      y0=df[col_close][resistance_point],
                      x1=df[col_date][len(df) - 1],
                      y1=current_price,
                      fillcolor="lightgreen",
                      opacity=0.5,
                      layer="below",
                      line=dict(color="lightgreen", width=0),
                      name="阻力带")

        diff = df[col_close][resistance_point] - current_price
        diff_percent = round(diff / current_price * 100, 2)
        fig.add_annotation(x=df[col_date][resistance_point], y=df[col_close][resistance_point],
                           text=f"阻力位\n{df[col_close][resistance_point]}元\n({diff_percent}%)",
                           showarrow=True, arrowhead=1, ax=0, ay=-40)

    if support_point:
        fig.add_shape(type="rect",
                      x0=df[col_date][support_point],
                      y0=df[col_close][support_point],
                      x1=df[col_date][len(df) - 1],
                      y1=current_price,
                      fillcolor="lightcoral",
                      opacity=0.5,
                      layer="below",
                      line=dict(color="lightcoral", width=0),
                      name="支撑带")

        diff = df[col_close][support_point] - current_price
        diff_percent = round(diff / current_price * 100, 2)
        fig.add_annotation(x=df[col_date][support_point], y=df[col_close][support_point],
                           text=f"支撑位\n{df[col_close][support_point]}元\n({diff_percent}%)",
                           showarrow=True, arrowhead=1, ax=0, ay=40)

    fig.show()


def usage():
    print(f"{basename(__file__)} [-n days] [-s start_date] [-e end_date] <stock_id>")
    print("-n days: since how many days ago, cannot be used together with -s and -e. default is 120")
    print("start_date/end_date: YYYYMMDD")


if __name__ == "__main__":
    stock_id = None
    start_date = None
    end_date = None
    n = 120

    for i in range(1, len(sys.argv)):
        if sys.argv[i] == '-n':
            n = int(sys.argv[i+1])
        elif sys.argv[i] == '-s':
            start_date = sys.argv[i+1]
        elif sys.argv[i] == '-e':
            end_date = sys.argv[i+1]
        else:
            stock_id = sys.argv[i]

    if not stock_id:
        usage()
        exit()

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y%m%d')
        end_date = end_date.strftime('%Y%m%d')

    stock_name, df = load_data(stock_id, start_date, end_date)
    turning_points, support_point, resistance_point = get_support_resistance(df)
    draw_support_resistance(stock_name, df, turning_points, support_point, resistance_point)
