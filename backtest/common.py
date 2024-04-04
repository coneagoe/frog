import os
import sys
from btplotting import BacktraderPlotting
import backtrader as bt
import pandas as pd
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from btplotting.analyzers import RecorderAnalyzer
from stock import (
    load_history_data,
)  # noqa: E402


start_cash = 100000
fee_rate = 0.0003


def enable_optimize():
    os.environ['OPTIMIZER'] = 'True'


def set_stocks(cerebro, stocks: list, start_date: str, end_date: str):
    for stock in stocks:
        # 获取数据
        df = load_history_data(security_id=stock, period="daily",
                               start_date=start_date, end_date=end_date, 
                               adjust="hfq").iloc[:, :6]
        df.columns = [
            'date',
            'open',
            'close',
            'high',
            'low',
            'volume',
        ]

        # start_date_st = pd.Timestamp(start_date)
        # df['date'] = pd.to_datetime(df['date'])

        # # 用第一行的数据填充缺失的数据
        # if df['date'].iloc[0] > start_date_st:
        #     date_range = pd.date_range(start=start_date_st, end=df['date'].iloc[0])
        #     # 创建一个DateFrame，columns为df.columns
        #     df_new = pd.DataFrame(columns=df.columns)
        #     df_new['date'] = date_range
        #     df_new = df_new.fillna(df.iloc[0])
        #     df = pd.concat([df_new, df])
        #     print(f"fill {stock}:")
        #     print(df.head(10))

        # df.index = pd.to_datetime(df['date'])
        # 设置index为column 'date'
        df.set_index('date', inplace=True)

        df.index.name = 'date'

        # 创建数据源
        data = bt.feeds.PandasData(dataname=df)

        # 添加数据源
        cerebro.adddata(data)


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
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    # cerebro.addanalyzer(BacktraderPlottingLive)
    # cerebro.addanalyzer(RecorderAnalyzer)


def show_result(cerebro, results):
    if os.getenv('OPTIMIZER'):
        return

    strat = results[0]
    
    print('Sharpe Ratio:')
    sharpe_ratio = pd.DataFrame([strat.analyzers.sharpe_ratio.get_analysis()], index=[''])
    print(sharpe_ratio)

    annual_return = strat.analyzers.annual_return.get_analysis()
    annual_return_df = pd.DataFrame(list(annual_return.items()), columns=['Year', 'Return(%)'])
    annual_return_df['Return(%)'] = annual_return_df['Return(%)'].apply(lambda x: '{:.2f}'.format(x*100))
    print('\nAnnual Return:')
    print(annual_return_df)

    drawdown = strat.analyzers.drawdown.get_analysis()
    print('\nDrawdown:')
    print(f"len(最长回撤期): {drawdown['len']}")
    print(f"drawdown(最大回撤%): {drawdown['drawdown']:.2f}")
    print(f"moneydown(最大回撤金额): {drawdown['moneydown']:.2f}")
    print("max(最大回撤详细):")
    print(f"\tlen(最长回撤期): {drawdown['max']['len']}")
    print(f"\tdrawdown(最大回撤%): {drawdown['max']['drawdown']:.2f}")
    print(f"\tmoneydown(最大回撤金额): {drawdown['max']['moneydown']:.2f}")

    returns = strat.analyzers.returns.get_analysis()
    print('\nReturns:')
    print(f"rtot(总回报%): {returns['rtot']*100:.2f}")
    print(f"ravg(平均每天回报%): {returns['ravg']*100:.4f}")
    print(f"rnorm100(年化回报%): {returns['rnorm100']:.2f}")

    time_return = pd.DataFrame([strat.analyzers.time_return.get_analysis()], index=[''])
    print('\nTime Return:')
    print(time_return)

    vwr = strat.analyzers.vwr.get_analysis()['vwr']
    print('\nVWR(Variable Weighted Return):')
    print(f"{vwr:.2f}")

    sqn = strat.analyzers.sqn.get_analysis()['sqn']
    print('\nSQN(System Quality Number):')
    print(f"{sqn:.2f}")

    # print('\nTrade Analysis:')
    # trade_analysis = strat.analyzers.trade_analysis.get_analysis()
    # print(trade_analysis)

    # print('\nTransaction Records:')
    # transactions = strat.analyzers.transactions.get_analysis()
    # print(transactions)
    # transactions_df = pd.DataFrame(transactions).T
    # transactions_df.columns = ['id', 'price', 'amount', 'name', 'value']
    # print(transactions_df)

    p = BacktraderPlotting(style='bar', multiple_tabs=True)
    cerebro.plot(p)


def run(cerebro, stocks: list, start_date: str, end_date: str):
    set_stocks(cerebro, stocks, start_date, end_date)

    add_analyzer(cerebro)

    if os.environ.get('OPTIMIZER'):
        results = cerebro.run(maxcpus=1)
    else:
        results = cerebro.run()

    show_result(cerebro, results)
