from os.path import basename
import argparse
from datetime import date
import pandas as pd
import plotly.graph_objs as go
from stock import *
import conf


conf.parse_config()

trading_book_path = get_trading_book_path()


def get_target_prices(stock_id: str):
    df = pd.read_excel(trading_book_path, sheet_name=u'持仓', dtype={COL_STOCK_ID: str})
    df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
    df[COL_STOCK_ID] = df[COL_STOCK_ID].str.zfill(6)
    cost, tp0, tp1, tp2 = None, None, None, None
    try:
        cost = df.loc[df[COL_STOCK_ID] == stock_id][COL_BUYING_PRICE].iloc[0]
        tp0 = df.loc[df[COL_STOCK_ID] == stock_id][u'目标价格1'].iloc[0]
        tp1 = df.loc[df[COL_STOCK_ID] == stock_id][u'目标价格2'].iloc[0]
        tp2 = df.loc[df[COL_STOCK_ID] == stock_id][u'目标价格3'].iloc[0]
    except IndexError:
        pass

    return cost, tp0, tp1, tp2


def draw_support_resistance(stock_id: str, df: pd.DataFrame,
                            turning_points, support_point, resistance_point,
                            cost, target_price_0, target_price_1, target_price_2):
    stock_name = get_security_name(stock_id)

    fig = go.Figure()
    fig.update_layout(title={
        'text': f"{stock_name}",
        'y': 0.9,
        'x': 0.5,
        'xanchor': 'center',
        'yanchor': 'top'})
    fig.add_trace(go.Scatter(x=df[COL_DATE], y=df[COL_CLOSE], mode='lines', name='股价'))
    fig.add_trace(go.Scatter(x=df[COL_DATE][turning_points], y=df[COL_CLOSE][turning_points],
                             mode='markers', name='拐点'))

    current_price = df[COL_CLOSE].iloc[-1]
    if resistance_point:
        fig.add_shape(type="rect",
                      x0=df[COL_DATE][resistance_point],
                      y0=df[COL_CLOSE][resistance_point],
                      x1=df[COL_DATE][len(df) - 1],
                      y1=current_price,
                      fillcolor="lightgreen",
                      opacity=0.5,
                      layer="below",
                      line=dict(color="lightgreen", width=0),
                      name="阻力带")

        diff = df[COL_CLOSE][resistance_point] - current_price
        diff_percent = round(diff / current_price * 100, 2)
        fig.add_annotation(x=df[COL_DATE][resistance_point], y=df[COL_CLOSE][resistance_point],
                           text=f"阻力位\n{df[COL_CLOSE][resistance_point]}元\n({diff_percent}%)",
                           showarrow=True, arrowhead=1, ax=0, ay=-40)

    if support_point:
        fig.add_shape(type="rect",
                      x0=df[COL_DATE][support_point],
                      y0=df[COL_CLOSE][support_point],
                      x1=df[COL_DATE][len(df) - 1],
                      y1=current_price,
                      fillcolor="lightcoral",
                      opacity=0.5,
                      layer="below",
                      line=dict(color="lightcoral", width=0),
                      name="支撑带")

        diff = df[COL_CLOSE][support_point] - current_price
        diff_percent = round(diff / current_price * 100, 2)
        fig.add_annotation(x=df[COL_DATE][support_point], y=df[COL_CLOSE][support_point],
                           text=f"支撑位\n{df[COL_CLOSE][support_point]}元\n({diff_percent}%)",
                           showarrow=True, arrowhead=1, ax=0, ay=40)

    colors = ('black', 'red', 'blue', 'green')
    target_prices = (cost, target_price_0, target_price_1, target_price_2)
    for i in range(len(target_prices)):
        tp = target_prices[i]
        if not pd.isna(tp):
            if i == 0:
                name = u"成本价格"
            else:
                name = f"目标价格{i + 1}"

            fig.add_shape(type="line",
                          x0=df[COL_DATE].iloc[0],
                          y0=tp,
                          x1=df[COL_DATE].iloc[-1],
                          y1=tp,
                          line=dict(color=colors[i], width=1, dash='dash'),
                          name=name)

            fig.add_annotation(x=df[COL_DATE].iloc[-1], y=tp,
                               text=f"{tp}",
                               showarrow=False, xanchor='left', yanchor='middle')

    fig.show()


def usage():
    print(f"{basename(__file__)} [-n days] [-s start_date] [-e end_date] <stock_id>")
    print(f"{basename(__file__)} -h")
    print("-n days: since how many days ago, cannot be used together with -s and -e. default is 120")
    print("start_date/end_date: YYYY-MM-DD")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', type=int, default=360, help='since how many days ago to show')
    parser.add_argument('-s', type=str, help='start date, format: YYYY-M-D')
    parser.add_argument('-e', type=str, help='end date, format: YYYY-M-D')
    parser.add_argument('stock_id', type=str)
    args = parser.parse_args()

    stock_id = args.stock_id
    start_date = args.s
    end_date = args.e
    n = args.n

    if not stock_id:
        usage()
        exit()

    if start_date is None or end_date is None:
        end_date = date.today()
        start_date = end_date - pd.Timedelta(days=n)
        start_date = start_date.strftime('%Y%m%d')
        end_date = end_date.strftime('%Y%m%d')

    df = load_history_data(stock_id, start_date, end_date)
    turning_points, support_point, resistance_point = get_support_resistance(df)
    cost, tp0, tp1, tp2 = get_target_prices(stock_id)
    draw_support_resistance(stock_id, df,
                            turning_points, support_point, resistance_point,
                            cost, tp0, tp1, tp2)
