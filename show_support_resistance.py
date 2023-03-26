from os.path import basename
import sys
import argparse
from datetime import date
import pandas as pd
import akshare as ak
from stock import *
import plotly.graph_objs as go


conf.config = conf.parse_config()

trading_book_path = get_trading_book_path()


def load_history_data(stock_id: str, start_date: str, end_date: str):
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


def get_target_prices(stock_id: str):
    df = pd.read_excel(trading_book_path, sheet_name=u'持仓', dtype={col_stock_id: str})
    df[col_stock_id] = df[col_stock_id].astype(str)
    df[col_stock_id] = df[col_stock_id].str.zfill(6)
    cost, tp0, tp1, tp2 = None, None, None, None
    try:
        cost = df.loc[df[col_stock_id] == stock_id][col_buying_price].iloc[0]
        tp0 = df.loc[df[col_stock_id] == stock_id][u'目标价格1'].iloc[0]
        tp1 = df.loc[df[col_stock_id] == stock_id][u'目标价格2'].iloc[0]
        tp2 = df.loc[df[col_stock_id] == stock_id][u'目标价格3'].iloc[0]
    except IndexError:
        pass

    return cost, tp0, tp1, tp2


def draw_support_resistance(stock_name: str, df: pd.DataFrame,
                            turning_points, support_point, resistance_point,
                            cost, target_price_0, target_price_1, target_price_2):
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

    if not pd.isna(cost):
        fig.add_shape(type="line",
                      x0=df[col_date].iloc[0],
                      y0=cost,
                      x1=df[col_date].iloc[-1],
                      y1=cost,
                      line=dict(color='black', width=1, dash='dash'),
                      name=u"成本价格")

        fig.add_annotation(x=df[col_date].iloc[-1], y=cost,
                           text=f"{cost}",
                           showarrow=False, xanchor='left', yanchor='middle')

    colors = ('red', 'blue', 'green')
    target_prices = (target_price_0, target_price_1, target_price_2)
    for i in range(3):
        tp = target_prices[i]
        if not pd.isna(tp):
            fig.add_shape(type="line",
                          x0=df[col_date].iloc[0],
                          y0=tp,
                          x1=df[col_date].iloc[-1],
                          y1=tp,
                          line=dict(color=colors[i], width=1, dash='dash'),
                          name=f"目标价格{i + 1}")

            fig.add_annotation(x=df[col_date].iloc[-1], y=tp,
                               text=f"{tp}",
                               showarrow=False, xanchor='left', yanchor='middle')
        else:
            break

    fig.show()


def usage():
    print(f"{basename(__file__)} [-n days] [-s start_date] [-e end_date] <stock_id>")
    print("-n days: since how many days ago, cannot be used together with -s and -e. default is 120")
    print("start_date/end_date: YYYYMMDD")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int)
    parser.add_argument('-s', type=str)
    parser.add_argument('-e', type=str)
    parser.add_argument('start_id', type=str)
    args = parser.parse_args()

    stock_id = args.start_id
    start_date = args.s
    end_date = args.e
    n = args.n if args.n else 120

    if not stock_id:
        usage()
        exit()

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y%m%d')
        end_date = end_date.strftime('%Y%m%d')

    stock_name, df = load_history_data(stock_id, start_date, end_date)
    turning_points, support_point, resistance_point = get_support_resistance(df)
    cost, tp0, tp1, tp2 = get_target_prices(stock_id)
    draw_support_resistance(stock_name, df,
                            turning_points, support_point, resistance_point,
                            cost, tp0, tp1, tp2)
