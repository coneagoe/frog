import argparse
import os
import sys

import backtrader as bt

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import run  # noqa: E402
from indicator_rsrs import RSRS_Norm  # noqa: E402
from my_strategy import MyStrategy  # noqa: E402

import conf  # noqa: E402

stocks = ("sh000300",)


conf.parse_config()


class RsrsNormStrategy(MyStrategy):
    params = (("period", 18),)  # RSRS周期

    def __init__(self):
        super().__init__()
        # self.rsrs = RSRS(self.data, N=self.p.period)
        # self.rsrs_norm = RSRS_Norm(self.data, N=self.p.period)
        self.rsrs_norm = RSRS_Norm()
        self.ma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)

    def next(self):
        super().next()
        if not self.position:  # not in the market
            # if (self.rsrs_norm[0] > 0.7
            if (
                self.rsrs_norm.beta_right[0] > 0.7
                and self.context[0].current_price > self.ma20[0]
            ):
                self.order_target_percent(self.data, 0.99)  # enter long
                # self.buy()

        # elif self.rsrs_norm[0] < -0.7:
        elif self.rsrs_norm.beta_right[0] < -0.7:
            self.close()  # close long position

    def stop(self):
        print(f"period: {self.p.period}")
        super().stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--start", required=True, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "-e", "--end", required=True, help="End date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "-c",
        "--cash",
        required=False,
        type=float,
        default=1000000,
        help="Initial cash amount",
    )
    args = parser.parse_args()

    os.environ["INIT_CASH"] = str(args.cash)

    RsrsNormStrategy.stocks = stocks

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(RsrsNormStrategy, period=range(1, 10))
    else:
        cerebro.addstrategy(RsrsNormStrategy)

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=RsrsNormStrategy.stocks,
        start_date=args.start,
        end_date=args.end,
        security_type="auto",
    )
