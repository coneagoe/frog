import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf                 # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402
from rotate_etf_pool import etf_pool as stocks   # noqa: E402


conf.parse_config()


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.holding_bars = 0


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()

class RotateStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('n_day_increase', 20),     # n天内涨幅
            # ('num_positions', 3),       # 最大持仓股票数
            ('num_positions', 6),       # 最大持仓股票数
            ('holding_bars', 10),          # 最少持仓天数
        )


    def __init__(self):     # noqa: E303
        self.pct_change = {i: bt.indicators.PercentChange(self.datas[i].close,
                                                          period=self.params.n_day_increase)
                           for i in range(len(self.datas))}
        self.target = round(1 / self.params.num_positions, 2)
        self.ema_low = {i: bt.indicators.EMA(self.datas[i].low,
                                             period=self.params.ema_period)
                                             for i in range(len(self.datas))}


    def next(self):    # noqa: E303
        # 计算所有股票的涨幅
        performance = {i: self.pct_change[i][0] for i in range(len(self.datas))}

        # 按照涨幅降序排列
        performance = sorted(performance.items(), key=lambda item: item[1], reverse=True)

        # 选择涨幅最大的前n个股票
        selected = [stock for stock, change in performance[:self.params.num_positions] if change > 0]

        for i in range(len(self.datas)):
            if gContext[i].order:
                gContext[i].holding_bars += 1

                if (i not in selected) and (gContext[i].holding_bars >= self.params.holding_bars):
                    self.order_target_percent(self.datas[i], target=0.0)
            else:
                if i in selected and self.ema_low[i][0] < self.datas[i].close[0]:
                    self.order_target_percent(self.datas[i], target=self.target)


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
            return

        if trade.isclosed:
            gContext[i].reset()

        # print('\n---------------------------- TRADE ---------------------------------')
        # print('Size: ', trade.size)
        # print('Price: ', trade.price)
        # print('Value: ', trade.value)
        # print('Commission: ', trade.commission)
        # print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
        # print('--------------------------------------------------------------------\n')


    def stop(self):     # noqa: E303
        print('(n_day_increase %d, num_positions %d, holding_bars %d) Ending Value %.2f' %
                     (self.params.n_day_increase, self.params.num_positions,
                      self.params.holding_bars, self.broker.getvalue()))

        show_position(self.positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(RotateStrategy,
                                # n_day_increase=range(5, 30))
                                num_positions=range(1, len(stocks)))
                                # holding_bars=range(1, 20))
    else:
        cerebro.addstrategy(RotateStrategy)

    run(strategy_name='rotate_etf_0', cerebro=cerebro, stocks=stocks,
        start_date=args.start, end_date=args.end)
