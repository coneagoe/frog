import argparse
import os
import sys

import backtrader as bt
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import drop_suspended, run  # noqa: E402
from my_strategy import MyStrategy, OrderState  # noqa: E402

import conf  # noqa: E402
from stock import (  # noqa: E402
    COL_STOCK_ID,
    drop_delisted_stocks,
    load_300_ingredients,
    load_500_ingredients,
)

conf.parse_config()

# enable_optimize()

# disable_plotly()


class TrendFollowingStrategy(MyStrategy):
    params = (
        ("ema_period", 20),
        ("n_portion", 2),  # 每支股票允许持有的n倍最小仓位
        ("p_macd_1_dif", 6),
        ("p_macd_1_dea", 12),
        ("p_macd_1_signal", 5),
        ("holding_bars", 10),
        ("profit_rate", 0.05),
    )

    def __init__(self):
        super().__init__()

        self.target = round(self.p.n_portion / len(self.stocks), 2)
        if self.target < 0.02:
            self.target = 0.02

        self.ema30 = {
            i: bt.indicators.EMA(self.datas[i].close, period=30)
            for i in range(len(self.datas))
        }

        self.ema20 = {
            i: bt.indicators.EMA(self.datas[i].close, period=20)
            for i in range(len(self.datas))
        }

        self.ema10 = {
            i: bt.indicators.EMA(self.datas[i].close, period=10)
            for i in range(len(self.datas))
        }

        self.ema5 = {
            i: bt.indicators.EMA(self.datas[i].close, period=5)
            for i in range(len(self.datas))
        }

        self.macd_1 = {
            i: bt.indicators.MACD(
                self.datas[i].close,
                period_me1=self.p.p_macd_1_dif,
                period_me2=self.p.p_macd_1_dea,
                period_signal=self.p.p_macd_1_signal,
            )
            for i in range(len(self.datas))
        }

        self.cross_signal_1 = {
            i: bt.indicators.CrossOver(self.macd_1[i].macd, self.macd_1[i].signal)
            for i in range(len(self.datas))
        }

    def next(self):
        super().next()

        is_affordable = True

        for i in range(len(self.datas)):
            if self.context[i].order_state == OrderState.ORDER_IDLE:
                if self.context[i].is_candidator is False:
                    # 如果MACD金叉
                    if self.cross_signal_1[i] > 0:
                        self.context[i].is_candidator = True
                        continue
                else:
                    # 如果MACD死叉或MACD.macd曲线不光滑
                    if (
                        self.cross_signal_1[i] < 0
                        or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0
                    ):
                        self.context[i].is_candidator = False
                        continue
                    else:
                        if is_affordable is False:
                            continue

                        if (
                            self.context[i].current_price > self.ema20[i][0]
                            and self.macd_1[i].signal[0] > 0
                            and self.macd_1[i].macd[0] > 0
                        ):
                            available_cash = self.broker.get_cash()
                            portion_value = self.calculate_portion_value()
                            if available_cash < portion_value:
                                is_affordable = False
                                # self.close_3_smallest_score_holdings()
                                continue

                            # recompute available_cash here if needed
                            size = int(
                                (portion_value / self.context[i].current_price)
                                // 100
                                * 100
                            )
                            if size > 0:
                                self.buy(data=self.datas[i], size=size, valid=0)
                                self.context[i].size = size
                                self.context[i].stop_price = round(self.ema20[i][-1], 3)

            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                profit_rate = self.context[i].profit_rate

                if (
                    self.context[i].holding_bars > self.p.holding_bars
                    and profit_rate < self.p.profit_rate
                ):
                    self.close(data=self.datas[i])
                    self.context[i].order_state = OrderState.ORDER_CLOSING
                    continue

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
                    self.context[i].stop_price = max(
                        self.context[i].stop_price, self.datas[i].low[-1]
                    )

                if ema is not None:
                    self.context[i].stop_price = max(
                        self.context[i].stop_price, ema[i][-1]
                    )

                if self.context[i].current_price < self.context[i].stop_price:
                    self.close(data=self.datas[i])
                    self.context[i].order_state = OrderState.ORDER_CLOSING

    def calculate_portion_value(self):
        return self.broker.get_value() * self.target

    def close_3_smallest_score_holdings(self):
        holdings = [
            (i, c.score)
            for i, c in enumerate(self.context)
            if (c.order_state == OrderState.ORDER_HOLDING and c.score < -10)
        ]
        holdings.sort(key=lambda x: x[1])
        # for i, _ in holdings[:3]:
        for i, _ in holdings:
            self.close(data=self.datas[i])

    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = round(self.ema20[i][-1], 3)

    def stop(self):
        print("ema_period: %d, n_positions: %d" % (self.p.ema_period, self.p.n_portion))
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

    stocks = load_300_ingredients(args.start)
    tmp = load_500_ingredients(args.start)
    stocks.extend(tmp)
    if args.filter:
        filter_list = args.filter.split()
        stocks = [stock for stock in stocks if stock not in filter_list]

    stocks = drop_delisted_stocks(stocks, args.start, args.end)
    TrendFollowingStrategy.stocks = drop_suspended(stocks, args.start, args.end, 10)

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(
            TrendFollowingStrategy,
            # ema_period=range(5, 30))
            # num_positions=range(1, len(stocks)))
            # holding_bars=range(1, 20))
            n_portion=range(1, 10),
        )
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    df_stocks = pd.DataFrame(TrendFollowingStrategy.stocks, columns=[COL_STOCK_ID])

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=TrendFollowingStrategy.stocks,
        start_date=args.start,
        end_date=args.end,
        security_type="stock",
    )
