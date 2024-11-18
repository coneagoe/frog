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
from my_strategy import MyStrategy  # noqa: E402


conf.parse_config()

# enable_optimize()

# disable_plotly()


class RotateStrategy(MyStrategy):
    params = (
            ('ema_period', 12),
            ('n_day_increase', 20),     # n天内涨幅
            # ('num_positions', 3),       # 最大持仓股票数
            ('num_positions', 6),       # 最大持仓股票数
            ('holding_bars', 10),          # 最少持仓天数
        )


    def __init__(self):     # noqa: E303
        super(RotateStrategy, self).__init__()

        self.target = round(3 / len(self.stocks), 2)

        self.pct_change = {i: bt.indicators.PercentChange(self.datas[i].close,
                                                          period=self.params.n_day_increase)
                           for i in range(len(self.datas))}
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
            if self.context[i].order:
                self.context[i].holding_bars += 1

                if (i not in selected) and (self.context[i].holding_bars >= self.params.holding_bars):
                    self.order_target_percent(self.datas[i], target=0.0)
            else:
                if i in selected and self.ema_low[i][0] < self.datas[i].close[0]:
                    self.order_target_percent(self.datas[i], target=self.target)


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

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(strategy_name=strategy_name, cerebro=cerebro, stocks=stocks,
        start_date=args.start, end_date=args.end)
