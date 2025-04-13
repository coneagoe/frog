from datetime import datetime
import logging
import os
import sys
import backtrader as bt
import pandas as pd
import pandas_market_calendars as mcal
import quantstats as qs
from tqdm import tqdm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.my_analyzer import MyAnalyzer
from stock import (
    COL_DATE,
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_VOLUME,
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
    df = df.iloc[:, :6]

    df.columns = [
        'date',
        'open',
        'close',
        'high',
        'low',
        'volume',
    ]

    start_date_dt = pd.to_datetime(start_date)
    if start_date_dt < df.iloc[0]['date']:
        cal = mcal.get_calendar('XSHG')
        schedule = cal.schedule(start_date=start_date, end_date=df.iloc[0]['date'])
        all_days = schedule.index

        df_tmp = pd.DataFrame(columns=['date', 'open', 'close', 'high',
                                    'low', 'volume'],
                              index=range(len(all_days)))

        df_tmp['date'] = all_days
        df_tmp[['open', 'close', 'high', 'low', 'volume']] = 1.0
        df_tmp.set_index('date', inplace=True)
        df.set_index('date', inplace=True)

        df = pd.concat([df_tmp, df], axis=0)
        df.sort_index(inplace=True)

    else:
        df.set_index('date', inplace=True)

    df.index.name = 'date'

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

    # if pd.to_datetime(end_date) - pd.to_datetime(start_date) < pd.Timedelta(days=365):
    #     adjust = ""
    # else:
    #     adjust = "qfq"
    adjust = "qfq"

    # 添加数据
    for stock in tqdm(stocks):
        # 获取数据
        df = load_test_data(security_id=stock, period="daily",
                            start_date=start_date, end_date=end_date,
                            adjust=adjust, security_type=security_type)

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


def generate_report(cerebro, results):
    if os.getenv('OPTIMIZER'):
        return

    strategy = results[0]

    pyfolio = strategy.analyzers.getbyname('pyfolio')
    returns, positions, transactions, gross_lev = pyfolio.get_pf_items()
    qs.reports.metrics(returns)
    report_file_name = f'report_{g_strategy_name}_{g_start_date}_{g_end_date}.html'
    qs.reports.html(returns=returns, positions=positions,
                    transactions=transactions, gross_lev=gross_lev,
                    output=report_file_name)

    if os.getenv('PLOT_REPORT') == 'true':
        import webbrowser
        webbrowser.open('file://' + os.path.realpath(report_file_name))
        plot(strategy)
    # else:
        # from btplotting import BacktraderPlotting
        # from btplotting.analyzers import RecorderAnalyzer
        # # p = BacktraderPlotting(style='bar', multiple_tabs=True)

        # programe_name = os.path.basename(sys.argv[0])
        # p = BacktraderPlotting(style='bar', plotkwargs=dict(output_file=f'{programe_name}.html'))
        # cerebro.plot(p)


def run(strategy_name: str, cerebro, stocks: list, start_date: str, end_date: str, security_type: str):
    config(strategy_name, start_date, end_date)

    set_stocks(cerebro, stocks, start_date, end_date, security_type)

    add_analyzer(cerebro)

    if os.environ.get('OPTIMIZER'):
        results = cerebro.run(maxcpus=1)
    else:
        results = cerebro.run()

    generate_report(cerebro, results)


def show_position(positions):
    for data, position in positions.items():
        if position:
            logging.info(f'current position(当前持仓): {data._name}, size(数量): {"%.2f" % position.size}')


def plot(strategy: bt.Strategy):
    import plotly.graph_objs as go
    from plotly.subplots import make_subplots

    analyzer = strategy.analyzers.my_analyzer.get_analysis()

    df_cashflow = pd.DataFrame(analyzer.cashflow, columns=['total'])
    df_value = pd.DataFrame(analyzer.values, columns=['value'])

    trades_list = []
    for stock, trades in strategy.trades.items():
        trades_list.extend(trades)

    if len(trades_list) == 0:
        return

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

    plot_trade(strategy)


def plot_trade(strategy: bt.Strategy):
    if not os.getenv('PLOT_TRADE'):
        return

    stock_ids = os.getenv('PLOT_TRADE').split()

    for i, data in enumerate(strategy.datas):
        if data._name in stock_ids:
            df = df_data[i]
            fig = go.Figure()

            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name=data._name
            ))

            trades = strategy.trades[data._name]
            buy_markers = []
            sell_markers = []
            for t in trades:
                buy_markers.append(dict(
                    x=t.open_time,
                    y=t.open_price,
                    marker=dict(symbol='triangle-up', color='yellow', size=10),
                    mode='markers',
                    name='Buy'
                ))
                sell_markers.append(dict(
                    x=t.close_time,
                    y=t.close_price,
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

            # ema20_values = [strategy.ema20[i][idx] for idx in range(len(df))]
            # fig.add_trace(go.Scatter(
            #     x=df.index,
            #     y=ema20_values,
            #     mode='lines',
            #     name='EMA20'
            # ))

            fig.update_layout(title=data._name,
                              yaxis_title='Price',
                              xaxis_title='Date')

            fig.show()
