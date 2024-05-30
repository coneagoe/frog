import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
    disable_plotly,
)   # noqa: E402
from trend_follow_etf_pool import etf_pool as stocks   # noqa: E402
from my_strategy import MyStrategy  # noqa: E402


conf.parse_config()

# enable_optimize()

# disable_plotly()


class TrendFollowingStrategy(MyStrategy):
    params = (
            ('ema_period', 20),
            ('n_portion', 2), # 每支股票允许持有的n倍最小仓位
            ('p_macd_1_dif', 6),
            ('p_macd_1_dea', 12),
            ('p_macd_1_signal', 5),
            ('p_macd_2_dif', 6),
            ('p_macd_2_dea', 12),
            ('p_macd_2_signal', 5),
        )


    def __init__(self):
        super(TrendFollowingStrategy, self).__init__()

        self.set_context(stocks)

        self.target = round(self.params.n_portion / len(stocks), 2)

        self.ema30 = {i: bt.indicators.EMA(self.datas[i].close, period=30)
                      for i in range(len(self.datas))}

        self.ema20 = {i: bt.indicators.EMA(self.datas[i].close, period=20)
                      for i in range(len(self.datas))}

        self.ema10 = {i: bt.indicators.EMA(self.datas[i].close, period=10)
                      for i in range(len(self.datas))}

        self.ema5 = {i: bt.indicators.EMA(self.datas[i].close, period=5)
                      for i in range(len(self.datas))}

        self.macd_1 = {i: bt.indicators.MACD(self.datas[i].close,
                                             period_me1=self.params.p_macd_1_dif,
                                             period_me2=self.params.p_macd_1_dea,
                                             period_signal=self.params.p_macd_1_signal)
                                             for i in range(len(self.datas))}

        self.cross_signal_1 = {i: bt.indicators.CrossOver(self.macd_1[i].macd,
                                                        self.macd_1[i].signal)
                                                        for i in range(len(self.datas))}


    def next(self):
        # 遍历所有的股票
        for i in range(len(self.datas)):
            if self.context[i].order is False:
                if self.context[i].is_candidator is False:
                    # 如果MACD金叉
                    if self.cross_signal_1[i] > 0:
                        self.context[i].is_candidator = True
                        continue
                else:
                    # 如果MACD死叉或MACD.macd曲线不光滑
                    if self.cross_signal_1[i] < 0 or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0:
                        self.context[i].is_candidator = False
                        continue
                    else:
                        if self.datas[i].close[0] > self.ema20[i][0] \
                            and self.macd_1[i].signal[0] > 0 and self.macd_1[i].macd[0] > 0:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 计算当前收益率
                # print(f"foo: {i}, price: {self.datas[i].close[0]}, open_price: {self.context[i].open_price}")
                open_price = self.context[i].open_price
                profit_rate = round((self.datas[i].close[0] - open_price) / open_price, 4)
                ema = None
                if profit_rate < 0.2:
                    ema = self.ema30
                elif profit_rate < 0.4:
                    ema = self.ema20
                elif profit_rate < 0.6:
                    ema = self.ema10
                elif profit_rate < 0.8:
                    ema = self.ema5
                else:
                    if self.context[i].stop_price < self.datas[i].low[-1]:
                        self.context[i].stop_price = self.datas[i].low[-1]

                if ema is not None and self.context[i].stop_price < round(ema[i][-1], 3):
                    self.context[i].stop_price = round(ema[i][-1], 3)
                    # print(f"{self.datas[i]._name}: 更新止损价: {self.context[i].stop_price}")

                if self.datas[i].close[0] < self.context[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)


    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = round(self.ema20[i][-1], 3)


    def stop(self):
        print('(ema_period %d, n_positions %d) Ending Value %.2f' %
              (self.params.ema_period, self.params.n_portion, self.broker.getvalue()))

        for data, position in self.positions.items():
            if position:
                i = stocks.index(data._name)
                print(f'{data._name}: 持仓股数: {"%.2f" % position.size}, 成本: {self.context[i].open_price}, 止损: {self.context[i].stop_price}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 # num_positions=range(1, len(stocks)))
                                 # hold_days=range(1, 20))
                                 n_portion=range(1, 10))
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    run(cerebro, stocks, args.start, args.end)

