import argparse
import os
import sys

import backtrader as bt

from .bt_common import drop_suspended, run
from .my_strategy import MyStrategy, OrderState
from .stop_price_manager import StopPriceManagerEma as StopPriceManager

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from common.const import COL_STOCK_ID, SecurityType  # noqa: E402
from stock import drop_delisted_stocks, load_general_info_hk_ggt  # noqa: E402

conf.parse_config()


class TrendFollowingStrategy(MyStrategy):
    params = (
        ("ema_period", 20),
        ("p_macd_1_dif", 6),
        ("p_macd_1_dea", 12),
        ("p_macd_1_signal", 5),
    )

    def __init__(self):
        super().__init__()

        self.target = 0.01

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

        self.stop_manager = StopPriceManager(self.datas)

    def next(self):
        super().next()

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
                        if (
                            self.context[i].current_price is not None
                            and self.context[i].current_price
                            > self.stop_manager.ema20[i][0]
                            and self.macd_1[i].signal[0] > 0
                            and self.macd_1[i].macd[0] > 0
                        ):
                            self.order_target_percent(self.datas[i], target=self.target)
                            self.context[i].stop_price = round(
                                self.stop_manager.ema20[i][-1], 3
                            )
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.stop_manager.update_stop_price(self.context, self.datas, i)

                current_price = self.context[i].current_price
                stop_price = self.context[i].stop_price
                if (
                    isinstance(current_price, (int, float))
                    and isinstance(stop_price, (int, float))
                    and current_price < stop_price
                ):
                    self.order_target_percent(self.datas[i], target=0.0)
                    self.context[i].order_state = OrderState.ORDER_CLOSING

    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = round(self.stop_manager.ema20[i][-1], 3)

    def stop(self):
        print("ema_period: %d" % self.p.ema_period)
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
        "-c", "--cash", required=False, type=float, help="Initial cash amount"
    )
    parser.add_argument("-p", "--plot", required=False, default="", help="Plot trade")
    args = parser.parse_args()

    os.environ["PLOT_TRADE"] = args.plot
    if args.cash:
        os.environ["INIT_CASH"] = str(args.cash)

    hk_ggt_stocks_df = load_general_info_hk_ggt()

    stocks = hk_ggt_stocks_df[COL_STOCK_ID].tolist()
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
        )
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=TrendFollowingStrategy.stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.AUTO,
    )
