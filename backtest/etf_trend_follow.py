from datetime import datetime

import backtrader as bt
# from btplotting import BacktraderPlottingLive
# from btplotting.tabs import MetadataTab
import matplotlib.pyplot as plt
import akshare as ak
import pandas as pd


# symbol = '512100' # 中证1000
# symbol = '513100' # 纳指
# symbol = '159985' # 豆粕
# symbol = '513550' # 港股通50
symbol = '512690' # 酒ETF
short_period = 20
long_period = 60
init_stoploss_rate = 0.05

start_cash = 100000
start_date = datetime(1991, 1, 1)  # 回测开始时间
end_date = datetime(2023, 10, 1)  # 回测结束时间
fee_rate = 0.0003

# plt.rcParams["font.sans-serif"] = ["SimHei"]
# plt.rcParams["axes.unicode_minus"] = False

# 利用 AKShare 获取股票的后复权数据，这里只获取前 6 列
stock_hfq_df = ak.fund_etf_hist_em(symbol=symbol, adjust="hfq").iloc[:, :6]

# print(stock_hfq_df.head())

# 处理字段命名，以符合 Backtrader 的要求
stock_hfq_df.columns = [
    'date',
    'open',
    'close',
    'high',
    'low',
    'volume',
]
# 把 date 作为日期索引，以符合 Backtrader 的要求
stock_hfq_df.index = pd.to_datetime(stock_hfq_df['date'])
stock_hfq_df.index.name = 'date'


class TrendFollowingStrategy(bt.Strategy):
    def __init__(self):
        self.data_close = self.datas[0].close
        self.order = None
        self.stop_price = None

        # Create the short and long term Simple Moving Averages
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=short_period
        )
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=long_period
        )

        # Create a CrossOver Signal
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

    def next(self):
        if not self.position:
            if self.crossover > 0:
                # if all(self.data_close[i] > self.sma_short[i] for i in range(-5, 0)):
                self.order = self.buy()
                self.buy_price = self.data_close[0]
                self.stop_price = self.buy_price * (1 - init_stoploss_rate)
        else:
            # If profit exceeds 5%, move stop loss to 20-day moving average
            if self.data_close[0] > self.buy_price * 1.05:
                self.stop_price = max(self.stop_price, self.sma_short[0], self.buy_price)

            if self.data_close[0] <= self.stop_price:  # check if stop loss price has been hit
                self.order = self.sell()  # close long position
                self.stop_price = None
                self.buy_price = None

    def notify_trade(self, trade):
        if trade.isclosed:
            print('---------------------------- TRADE ---------------------------------')
            print('Size: ', trade.size)
            print('Price: ', trade.price)
            print('Value: ', trade.value)
            print('Commission: ', trade.commission)
            print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
            print('--------------------------------------------------------------------\n')


cerebro = bt.Cerebro()  # 初始化回测系统
data = bt.feeds.PandasData(dataname=stock_hfq_df, fromdate=start_date, todate=end_date)  # 加载数据
cerebro.adddata(data)  # 将数据传入回测系统
cerebro.addstrategy(TrendFollowingStrategy)  # 将交易策略加载到回测系统中
cerebro.broker.setcash(start_cash)  # 设置初始资本为 100000
cerebro.broker.setcommission(commission=fee_rate)  # 设置交易手续费

# cerebro.addanalyzer(BacktraderPlottingLive)
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
results = cerebro.run()  # 运行回测系统

port_value = cerebro.broker.getvalue()  # 获取回测结束后的总资金
pnl = port_value - start_cash  # 盈亏统计

print(f"初始资金: {start_cash}\n回测期间：{start_date.strftime('%Y%m%d')}:{end_date.strftime('%Y%m%d')}")
print(f"总资金: {round(port_value, 2)}")
print(f"净收益: {round(pnl, 2)}")

cerebro.plot()
