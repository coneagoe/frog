import argparse
import os
import sys

import backtrader as bt

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import run  # noqa: E402
from my_strategy import MyStrategy, OrderState  # noqa: E402
from rotate_etf_pool import etf_pool as stocks  # noqa: E402

import conf  # noqa: E402

conf.parse_config()


class RotateStrategy(MyStrategy):
    params = (
        ("ema_period", 12),
        ("n_day_increase", 20),  # n天内涨幅
        # ('num_positions', 3),       # 最大持仓股票数
        ("num_positions", 6),  # 最大持仓股票数
        ("holding_bars", 10),  # 最少持仓天数
    )

    def __init__(self):  # noqa: E303
        super().__init__()

        self.target = round(3 / len(self.stocks), 2)

        self.pct_change = {
            i: bt.indicators.PercentChange(
                self.datas[i].close, period=self.p.n_day_increase
            )
            for i in range(len(self.datas))
        }

        self.ema_low = {
            i: bt.indicators.EMA(self.datas[i].low, period=self.p.ema_period)
            for i in range(len(self.datas))
        }

    def next(self):  # noqa: E303
        super().next()

        # 计算所有股票的涨幅
        performance = {i: self.pct_change[i][0] for i in range(len(self.datas))}

        # 按照涨幅降序排列
        ranked_performance = sorted(
            performance.items(), key=lambda item: item[1], reverse=True
        )

        # 选择涨幅最大的前n个股票
        selected = [
            stock
            for stock, change in ranked_performance[: self.p.num_positions]
            if change > 0
        ]

        for i in range(len(self.datas)):
            if self.context[i].order_state == OrderState.ORDER_IDLE:
                if i in selected and self.ema_low[i][0] < self.context[i].current_price:
                    self.order_target_percent(self.datas[i], target=self.target)
                    self.context[i].stop_price = 0.0
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                if i not in selected and (
                    self.context[i].holding_bars >= self.p.holding_bars
                ):
                    self.order_target_percent(self.datas[i], target=0.0)
                    self.context[i].order_state = OrderState.ORDER_CLOSING

    def stop(self):  # noqa: E303
        print(
            "n_day_increase: %d, num_positions: %d, holding_bars: %d"
            % (
                self.p.n_day_increase,
                self.p.num_positions,
                self.p.holding_bars,
            )
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
    parser.add_argument(
        "-f",
        "--filter",
        required=False,
        help="Space-separated list of stock IDs to filter out",
    )
    parser.add_argument(
        "-c",
        "--cash",
        required=False,
        type=float,
        default=1000000,
        help="Initial cash amount",
    )
    parser.add_argument("-p", "--plot", required=False, default="", help="Plot trade")
    args = parser.parse_args()

    os.environ["PLOT_TRADE"] = args.plot
    os.environ["INIT_CASH"] = str(args.cash)

    RotateStrategy.stocks = stocks

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(
            RotateStrategy,
            # n_day_increase=range(5, 30))
            num_positions=range(1, len(stocks)),
        )
        # holding_bars=range(1, 20))
    else:
        cerebro.addstrategy(RotateStrategy)

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type="auto",
    )
