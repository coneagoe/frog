import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    disable_plotly,
    enable_optimize,
    run,
    show_position,
)   # noqa: E402
from my_strategy import MyStrategy  # noqa: E402


conf.parse_config()


stocks = ['159915']


class TrendRoc(MyStrategy):
    # 参数定义
    params = dict(
        period=20,  # 动量周期
    )

    def __init__(self):
        super(TrendRoc, self).__init__()

        self.set_context(stocks)

        # self.target = round(self.params.n_portion / len(stocks), 2)
        self.target = 0.99

        self.roc = {i: bt.indicators.ROC(self.datas[i], period=self.params.period)
                    for i in range(len(self.datas))}
    

    def next(self):
        for i in range(len(self.datas)):
            if self.context[i].order is False:
                if self.roc[i][0] > 0.08:  # if fast crosses slow to the upside
                    self.order_target_percent(self.datas[i], target=self.target)  # enter long
            else:
                if self.roc[i][0] < 0:  # in the market & cross to the downside
                    self.order_target_percent(self.datas[i], target=0.0)


    def stop(self):
        print('(period %d) Ending Value %.2f' %
              (self.params.period, self.broker.getvalue()))

        for data, position in self.positions.items():
            if position:
                i = stocks.index(data._name)
                print(f'{data._name}: 持仓股数: {"%.2f" % position.size}, 成本: {self.context[i].open_price}, 现价: {self.context[i].current_price}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(TrendRoc, period=range(1, 30))
    else:
        cerebro.addstrategy(TrendRoc)

    run(strategy_name='trend_roc_0', cerebro=cerebro, stocks=stocks,
        start_date=args.start, end_date=args.end)
