import argparse
import os
import sys

import backtrader as bt

from .bt_common import run
from .my_strategy import MyStrategy

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from common.const import SecurityType  # noqa: E402

conf.parse_config()


stocks = ["159915"]


class TrendRoc(MyStrategy):
    # 参数定义
    params = (("period", 20),)  # 动量周期

    def __init__(self):
        super(TrendRoc, self).__init__()

        self.set_context(stocks)

        self.target = 0.99

        self.roc = {
            i: bt.indicators.ROC(self.datas[i], period=self.p.period)
            for i in range(len(self.datas))
        }

    def next(self):
        for i in range(len(self.datas)):
            if self.context[i].order is False:
                if self.roc[i][0] > 0.08:  # if fast crosses slow to the upside
                    self.order_target_percent(
                        self.datas[i], target=self.target
                    )  # enter long
            else:
                if self.roc[i][0] < 0:  # in the market & cross to the downside
                    self.order_target_percent(self.datas[i], target=0.0)

    def stop(self):
        print("(period %d) Ending Value %.2f" % (self.p.period, self.broker.getvalue()))

        super().stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--start", required=True, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "-e", "--end", required=True, help="End date in YYYY-MM-DD format"
    )
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(TrendRoc, period=range(1, 30))
    else:
        cerebro.addstrategy(TrendRoc)

    run(
        strategy_name="trend_roc_0",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.ETF,
    )
