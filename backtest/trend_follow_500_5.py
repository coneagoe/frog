import argparse
import os
import sys

import backtrader as bt

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import run  # noqa: E402
from trend_follow_500_pool import stocks  # noqa: E402

import conf  # noqa: E402

conf.parse_config()


class Context:
    def __init__(self):
        self.reset()

    def reset(self):
        self.order = False
        self.open_price = None
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


class TrendFollowingStrategy(bt.Strategy):
    params = (
        ("ema_period", 20),
        ("num_positions", 30),  # 最大持仓股票数
        # ('num_positions', 2),       # 最大持仓股票数
        ("p_macd_1_dif", 6),
        ("p_macd_1_dea", 12),
        ("p_macd_1_signal", 5),
        ("p_macd_2_dif", 6),
        ("p_macd_2_dea", 12),
        ("p_macd_2_signal", 5),
    )

    def __init__(self):
        self.target = round(3 / len(stocks), 2)

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
        # 遍历所有的股票
        for i in range(len(self.datas)):
            if gContext[i].order is False:
                if gContext[i].is_candidator is False:
                    # 如果MACD金叉
                    if self.cross_signal_1[i] > 0:
                        gContext[i].is_candidator = True
                        continue
                else:
                    # 如果MACD死叉或MACD.macd曲线不光滑
                    if (
                        self.cross_signal_1[i] < 0
                        or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0
                    ):
                        gContext[i].is_candidator = False
                        continue
                    else:
                        if (
                            self.datas[i].close[0] > self.ema20[i][0]
                            and self.macd_1[i].signal[0] > 0
                            and self.macd_1[i].macd[0] > 0
                        ):
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                open_price = gContext[i].open_price
                profit_rate = round(
                    (self.datas[i].close[0] - open_price) / open_price, 4
                )
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
                    if gContext[i].stop_price < self.datas[i].low[-1]:
                        gContext[i].stop_price = self.datas[i].low[-1]

                if ema is not None and gContext[i].stop_price < ema[i][-1]:
                    gContext[i].stop_price = ema[i][-1]

                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)

    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
            gContext[i].open_price = trade.price
            gContext[i].stop_price = self.ema20[i][-1]
            gContext[i].is_candidator = False
            return

        if trade.isclosed:
            gContext[i].reset()

    def stop(self):
        print(
            "(ema_period %d, num_positions %d) Ending Value %.2f"
            % (
                self.p.ema_period,
                self.p.num_positions,
                self.broker.getvalue(),
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
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(
            TrendFollowingStrategy,
            # ema_period=range(5, 30))
            num_positions=range(1, len(stocks)),
        )
        # holding_bars=range(1, 20))
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    run("trend_follow_500_5", cerebro, stocks, args.start, args.end)
