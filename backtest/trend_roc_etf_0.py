import argparse
import os
import sys

import backtrader as bt

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import run  # noqa: E402
from my_strategy import MyStrategy  # noqa: E402
from trend_follow_etf_pool import etf_pool as stocks  # noqa: E402

import conf  # noqa: E402

conf.parse_config()


class TrendRoc(MyStrategy):
    # 参数定义
    params = (
        ("period", 20),  # 动量周期
        ("n_portion", 2),  # 每支股票允许持有的n倍最小仓位
    )

    def __init__(self):
        super(TrendRoc, self).__init__()

        self.set_context(stocks)

        self.target = round(self.p.n_portion / len(stocks), 2)
        # self.target = 0.99

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
        print(
            "(period %d, n_portion %d) Ending Value %.2f"
            % (self.p.period, self.p.n_portion, self.broker.getvalue())
        )

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
    )
