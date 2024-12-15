from datetime import datetime
import os
import sys
import webbrowser
from btplotting import BacktraderPlotting
import backtrader as bt
import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import quantstats as qs
from tqdm import tqdm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from btplotting.analyzers import RecorderAnalyzer
from backtest.my_analyzer import MyAnalyzer
from stock import (
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    is_a_index,
    load_history_data,
    drop_suspended_stocks,
)  # noqa: E402


start_cash = 1000000
fee_rate = 0.0003


use_plotly = True


df_data = []


g_start_date = '2020-01-01'
g_end_date = '2020-12-31'
g_strategy_name = None

g_filter_st = False


def config(strategy_name: str, start_date: str, end_date: str):
    global g_strategy_name, g_start_date, g_end_date
    g_strategy_name = strategy_name
    g_start_date = start_date
    g_end_date = end_date


def disable_plotly():
    global use_plotly
    use_plotly = False


def enable_optimize():
    os.environ['OPTIMIZER'] = 'True'


def load_test_data(security_id: str, period: str, start_date: str, end_date: str,
                   adjust="qfq", security_type="auto") -> pd.DataFrame:
    df = load_history_data(security_id=security_id, period=period,
                           start_date=start_date, end_date=end_date,
                           adjust=adjust, security_type=security_type)
    # 打印df length
    # print(f"security_id: {security_id}, df length: {df.size}")

    # if is_a_index(security_id):
    #     df[COL_OPEN]    = df[COL_OPEN].astype(float)    # noqa: E221
    #     df[COL_CLOSE]   = df[COL_CLOSE].astype(float)   # noqa: E221
    #     df[COL_HIGH]    = df[COL_HIGH].astype(float)    # noqa: E221
    #     df[COL_LOW]     = df[COL_LOW].astype(float)     # noqa: E221

    #     df[COL_OPEN]    = df[COL_OPEN]  / df[COL_OPEN].iloc[0]      # noqa: E221
    #     df[COL_CLOSE]   = df[COL_CLOSE] / df[COL_CLOSE].iloc[0]     # noqa: E221
    #     df[COL_HIGH]    = df[COL_HIGH]  / df[COL_HIGH].iloc[0]      # noqa: E221
    #     df[COL_LOW]     = df[COL_LOW]   / df[COL_LOW].iloc[0]       # noqa: E221

    #     df[COL_OPEN]    = df[COL_OPEN].apply(lambda x: round(x, 2))     # noqa: E221
    #     df[COL_CLOSE]   = df[COL_CLOSE].apply(lambda x: round(x, 2))    # noqa: E221
    #     df[COL_HIGH]    = df[COL_HIGH].apply(lambda x: round(x, 2))     # noqa: E221
    #     df[COL_LOW]     = df[COL_LOW].apply(lambda x: round(x, 2))      # noqa: E221

    return df


def drop_suspended(stocks: list, start_date: str, end_date: str,
                          num_points: int) -> list:
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    delta = (end - start) / (num_points - 1)
    dates = [(start + i * delta).strftime('%Y-%m-%d') for i in range(num_points)]

    for date in dates:
        stocks = drop_suspended_stocks(stocks, date)

    return stocks


def set_stocks(cerebro, stocks: list, start_date: str, end_date: str, security_type: str):
    global df_data

    if pd.to_datetime(end_date) - pd.to_datetime(start_date) < pd.Timedelta(days=365):
        adjust = ""
    else:
        adjust = "qfq"

    # 添加数据
    for stock in tqdm(stocks):
        # 获取数据
        tmp = load_test_data(security_id=stock, period="daily",
                            start_date=start_date, end_date=end_date,
                            adjust=adjust, security_type=security_type)
        df = tmp.iloc[:, :6]

        df.columns = [
            'date',
            'open',
            'close',
            'high',
            'low',
            'volume',
        ]

        df.set_index('date', inplace=True)

        df.index.name = 'date'

        df_data.append(df)

        # 创建数据源
        data = bt.feeds.PandasData(dataname=df)

        # 添加数据源
        cerebro.adddata(data, name=stock)


def add_analyzer(cerebro):
    global start_cash

    if os.getenv('OPTIMIZER'):
        return

    # 设置起始资金
    if os.getenv('INIT_CASH'):
        start_cash = float(os.getenv('INIT_CASH'))
    cerebro.broker.setcash(start_cash)

    cerebro.broker.setcommission(commission=fee_rate)  # 设置交易手续费

    # cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analysis")
    # cerebro.addanalyzer(bt.analyzers.Transactions, _name="transactions")
    # cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio")
    # cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
    # cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    # cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    # cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    # cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro.addanalyzer(MyAnalyzer, _name="my_analyzer")
    # cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    # cerebro.addanalyzer(BacktraderPlottingLive)
    # cerebro.addanalyzer(RecorderAnalyzer)


def show_result(cerebro, results):
    if os.getenv('OPTIMIZER'):
        return

    strategy = results[0]

    pyfolio = strategy.analyzers.getbyname('pyfolio')
    returns, positions, transactions, gross_lev = pyfolio.get_pf_items()
    qs.reports.metrics(returns)

    if use_plotly:
        report_file_name = f'report_{g_strategy_name}_{g_start_date}_{g_end_date}.html'
        qs.reports.html(returns=returns, positions=positions,
                        transactions=transactions, gross_lev=gross_lev,
                        output=report_file_name)
        webbrowser.open('file://' + os.path.realpath(report_file_name))
        plot(strategy)
    else:
        # p = BacktraderPlotting(style='bar', multiple_tabs=True)

        programe_name = os.path.basename(sys.argv[0])
        p = BacktraderPlotting(style='bar', plotkwargs=dict(output_file=f'{programe_name}.html'))

        cerebro.plot(p)


def run(strategy_name: str, cerebro, stocks: list, start_date: str, end_date: str, security_type: str):
    config(strategy_name, start_date, end_date)

    set_stocks(cerebro, stocks, start_date, end_date, security_type)

    add_analyzer(cerebro)

    if os.environ.get('OPTIMIZER'):
        results = cerebro.run(maxcpus=1)
    else:
        results = cerebro.run()

    show_result(cerebro, results)


def show_position(positions):
    for data, position in positions.items():
        if position:
            print(f'current position(当前持仓): {data._name}, size(数量): {"%.2f" % position.size}')


def plot(strategy: bt.Strategy):
    analyzer = strategy.analyzers.my_analyzer.get_analysis()

    df_cashflow = pd.DataFrame(analyzer.cashflow, columns=['total'])
    df_value = pd.DataFrame(analyzer.values, columns=['value'])

    trades_list = []
    for stock, trades in strategy.trades.items():
        trades_list.extend(trades)
    df_trades = pd.DataFrame(trades_list)
    holding_time_counts = df_trades['holding_time'].value_counts().sort_index()

    df_trades['open_time'] = pd.to_datetime(df_trades['open_time'])  # ensure open_time is datetime
    monthly_trades = df_trades.groupby(df_trades['open_time'].dt.to_period('M')).size()

    num_subplots = 4

    subplot_titles = ['Value & Cashflow', '', 'Holding Time', 'Monthly Trades']

    fig = make_subplots(rows=num_subplots, cols=1,
                        subplot_titles=subplot_titles,)

    fig.update_layout(height=500*num_subplots)

    x_axis = df_data[0].index

    row = 1
    fig.add_trace(go.Scatter(x=x_axis, y=df_value['value'], name='Value', yaxis='y1'), row=row, col=1)
    fig.add_trace(go.Scatter(x=x_axis, y=df_cashflow['total'], name='Cashflow', yaxis='y2'), row=row, col=1)

    row += 2
    fig.add_trace(go.Bar(x=holding_time_counts.index, y=holding_time_counts.values,
                         name='Holding Time', xaxis='x3', yaxis='y3'), row=row, col=1)

    row += 1
    fig.add_trace(go.Bar(x=monthly_trades.index.astype(str), y=monthly_trades.values,
                         name='Monthly Trades', xaxis='x4', yaxis='y4'), row=row, col=1)

    fig.update_layout(
        yaxis1=dict(title='Value', side='left'),
        yaxis2=dict(title='Cashflow', side='right', overlaying='y1'),
        xaxis3=dict(title=u'持仓时间'),
        yaxis3=dict(title=u'交易次数'),
        xaxis4=dict(title=u'月份'),
        yaxis4=dict(title=u'交易次数'),
        # yaxis5=dict(title='Average Monthly Profit')
    )

    fig.show()

    plot_detail(strategy)


def plot_detail(strategy: bt.Strategy):
    if os.environ.get('DRAW_DETAIL', 'false').lower() != 'true':
        return

    for i, data in enumerate(strategy.datas):
        df = df_data[i]
        fig = go.Figure()

        fig.add_trace(go.Candlestick(x=df.index,
                                     open=df['open'],
                                     high=df['high'],
                                     low=df['low'],
                                     close=df['close'],
                                     name=data._name))

        trades = strategy.trades[data._name]
        buy_markers = []
        sell_markers = []
        for trade in trades:
            buy_markers.append(dict(
                x=trade['open_time'],
                y=trade['open_price'],
                marker=dict(symbol='triangle-up', color='yellow', size=10),
                mode='markers',
                name='Buy'
            ))
            sell_markers.append(dict(
                x=trade['close_time'],
                y=trade['close_price'],
                marker=dict(symbol='triangle-down', color='blue', size=10),
                mode='markers',
                name='Sell'
            ))

        for marker in buy_markers:
            fig.add_trace(go.Scatter(x=[marker['x']], y=[marker['y']],
                                     mode=marker['mode'],
                                     marker=marker['marker'],
                                     name=marker['name']))

        for marker in sell_markers:
            fig.add_trace(go.Scatter(x=[marker['x']], y=[marker['y']],
                                     mode=marker['mode'],
                                     marker=marker['marker'],
                                     name=marker['name']))

        fig.update_layout(title=data._name,
                          yaxis_title='Price',
                          xaxis_title='Date')

        fig.show()
