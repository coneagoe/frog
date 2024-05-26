import os
import sys
from btplotting import BacktraderPlotting
import backtrader as bt
import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots
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
)  # noqa: E402


start_cash = 100000
fee_rate = 0.0003


use_plotly = True


def disable_plotly():
    global use_plotly
    use_plotly = False


def enable_optimize():
    os.environ['OPTIMIZER'] = 'True'


def load_test_data(security_id: str, period: str, start_date: str, end_date: str,
                   adjust="qfq") -> pd.DataFrame:
    df = load_history_data(security_id=security_id, period=period,
                           start_date=start_date, end_date=end_date,
                           adjust=adjust)
    if is_a_index(security_id):
        df[COL_OPEN]    = df[COL_OPEN].astype(float)    # noqa: E221
        df[COL_CLOSE]   = df[COL_CLOSE].astype(float)   # noqa: E221
        df[COL_HIGH]    = df[COL_HIGH].astype(float)    # noqa: E221
        df[COL_LOW]     = df[COL_LOW].astype(float)     # noqa: E221

        df[COL_OPEN]    = df[COL_OPEN]  / df[COL_OPEN].iloc[0]      # noqa: E221
        df[COL_CLOSE]   = df[COL_CLOSE] / df[COL_CLOSE].iloc[0]     # noqa: E221
        df[COL_HIGH]    = df[COL_HIGH]  / df[COL_HIGH].iloc[0]      # noqa: E221
        df[COL_LOW]     = df[COL_LOW]   / df[COL_LOW].iloc[0]       # noqa: E221

        df[COL_OPEN]    = df[COL_OPEN].apply(lambda x: round(x, 2))     # noqa: E221
        df[COL_CLOSE]   = df[COL_CLOSE].apply(lambda x: round(x, 2))    # noqa: E221
        df[COL_HIGH]    = df[COL_HIGH].apply(lambda x: round(x, 2))     # noqa: E221
        df[COL_LOW]     = df[COL_LOW].apply(lambda x: round(x, 2))      # noqa: E221

    return df


def set_stocks(cerebro, stocks: list, start_date: str, end_date: str):
    if pd.to_datetime(end_date) - pd.to_datetime(start_date) < pd.Timedelta(days=365):
        adjust = ""
    else:
        adjust = "hfq"

    # 添加数据
    for stock in tqdm(stocks):
        # 获取数据
        df = load_test_data(security_id=stock, period="daily",
                            start_date=start_date, end_date=end_date, 
                            adjust=adjust).iloc[:, :6]
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

        # 创建数据源
        data = bt.feeds.PandasData(dataname=df)

        # 添加数据源
        cerebro.adddata(data, name=stock)


def add_analyzer(cerebro):
    if os.getenv('OPTIMIZER'):
        return

    cerebro.broker.setcash(start_cash)  # 设置初始资本为 100000
    cerebro.broker.setcommission(commission=fee_rate)  # 设置交易手续费

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analysis")
    cerebro.addanalyzer(bt.analyzers.Transactions, _name="transactions")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(MyAnalyzer, _name="my_analyzer")
    # cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    # cerebro.addanalyzer(BacktraderPlottingLive)
    # cerebro.addanalyzer(RecorderAnalyzer)


def show_result(cerebro, results):
    if os.getenv('OPTIMIZER'):
        return

    strategy = results[0]
    
    print('Sharpe Ratio:')
    sharpe_ratio = pd.DataFrame([strategy.analyzers.sharpe_ratio.get_analysis()], index=[''])
    print(sharpe_ratio)

    annual_return = strategy.analyzers.annual_return.get_analysis()
    annual_return_df = pd.DataFrame(list(annual_return.items()), columns=['Year', 'Return(%)'])
    annual_return_df['Return(%)'] = annual_return_df['Return(%)'].apply(lambda x: '{:.2f}'.format(x*100))
    print('\nAnnual Return:')
    print(annual_return_df)

    drawdown = strategy.analyzers.drawdown.get_analysis()
    print('\nDrawdown:')
    print(f"len(最长回撤期): {drawdown['len']}")
    print(f"\tdrawdown(最大回撤%): {drawdown['drawdown']:.2f}")
    print(f"\tmoneydown(最大回撤金额): {drawdown['moneydown']:.2f}")
    print("max(最大回撤详细):")
    print(f"\tlen(最长回撤期): {drawdown['max']['len']}")
    print(f"\tdrawdown(最大回撤%): {drawdown['max']['drawdown']:.2f}")
    print(f"\tmoneydown(最大回撤金额): {drawdown['max']['moneydown']:.2f}")

    returns = strategy.analyzers.returns.get_analysis()
    print('\nReturns:')
    print(f"rtot(总回报%): {returns['rtot']*100:.2f}")
    print(f"ravg(平均每天回报%): {returns['ravg']*100:.4f}")
    print(f"rnorm100(年化回报%): {returns['rnorm100']:.2f}")

    vwr = strategy.analyzers.vwr.get_analysis()['vwr']
    print('\nVWR(Variable Weighted Return):')
    print(f"{vwr:.2f}")

    sqn = strategy.analyzers.sqn.get_analysis()['sqn']
    print('\nSQN(System Quality Number):')
    print(f"{sqn:.2f}")

    # time_return = pd.DataFrame([strat.analyzers.time_return.get_analysis()], index=[''])
    # print('\nTime Return:')
    # print(time_return)

    # print('\nTrade Analysis:')
    # trade_analysis = strat.analyzers.trade_analysis.get_analysis()
    # print(trade_analysis)

    # print('\nTransaction Records:')
    # transactions = strat.analyzers.transactions.get_analysis()
    # print(transactions)
    # transactions_df = pd.DataFrame(transactions).T
    # transactions_df.columns = ['id', 'price', 'amount', 'name', 'value']
    # print(transactions_df)

    if use_plotly:
        plot(strategy)
    else:
        p = BacktraderPlotting(style='bar', multiple_tabs=True)

        # programe_name = os.path.basename(sys.argv[0])
        # p = BacktraderPlotting(style='bar', plotkwargs=dict(output_file=f'{programe_name}.html'))

        cerebro.plot(p)


def run(cerebro, stocks: list, start_date: str, end_date: str):
    set_stocks(cerebro, stocks, start_date, end_date)

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

    # fig = make_subplots(rows=len(strategy.datas) + 1, cols=1)
    fig = make_subplots(rows=1, cols=1)

    # fig.update_layout(height=10000)

    df_cashflow = pd.DataFrame(analyzer.cashflow, columns=['total'])
    df_value = pd.DataFrame(analyzer.values, columns=['value'])

    x_axis = [bt.num2date(x) for x in strategy.datas[0].datetime.array]

    # 'Value' 和 'Cashflow' 在同一个子图中，位于顶部
    fig.add_trace(go.Scatter(x=x_axis, y=df_value['value'], name='Value', yaxis='y1'), row=1, col=1)
    fig.add_trace(go.Scatter(x=x_axis, y=df_cashflow['total'], name='Cashflow', yaxis='y2'), row=1, col=1)

    fig.update_layout(
        yaxis1=dict(title='Value', side='left'),
        yaxis2=dict(title='Cashflow', side='right', overlaying='y1')
    )

    for i, data in enumerate(strategy.datas):
        break
        df = pd.DataFrame({
            'open': data.open.array,
            'high': data.high.array,
            'low': data.low.array,
            'close': data.close.array
        })
        x_axis = [bt.num2date(x) for x in data.datetime.array]

        # 创建 K线图
        fig.add_trace(go.Candlestick(x=x_axis,
                                     open=df['open'],
                                     high=df['high'],
                                     low=df['low'],
                                     close=df['close'],
                                     name=data._name,
                                     yaxis='y{}'.format(i+3)),  # 指定 y 轴
                      row=i+2, col=1)  # 指定子图的位置，从第二行开始

        # 添加 y 轴配置
        fig.update_layout(**{'yaxis{}'.format(i+3): dict(overlaying='y1', side='right')})

    fig.show()
