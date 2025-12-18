import argparse
import os
import sys

import backtrader as bt
import pandas as pd

from .bt_common import drop_suspended, run
from .my_strategy import MyStrategy, OrderState
from .obos_indicator import OBOS
from .stop_price_manager import StopPriceManagerEma as StopPriceManager

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from common.const import COL_STOCK_ID, SecurityType  # noqa: E402
from indicator import OBOS_OVERBUY_THRESHOLD, OBOS_OVERSELL_THRESHOLD  # noqa: E402
from stock import (  # noqa: E402
    drop_delisted_stocks,
    load_ingredient_300,
    load_ingredient_500,
)

conf.parse_config()


class ObosStrategy(MyStrategy):
    params = (("param_sp", 5),)  # 过去n天的最低价作为initial stop price

    def __init__(self):
        super().__init__()

        self.obos = {i: OBOS(data=self.datas[i]) for i in range(len(self.datas))}

        self.stop_manager = StopPriceManager(self.datas)

    def next(self):
        super().next()

        for i in range(len(self.datas)):
            if self.context[i].order_state == OrderState.ORDER_IDLE:
                if self.context[i].is_candidator is False:
                    # 如果OBOS超卖
                    if self.obos[i] < OBOS_OVERSELL_THRESHOLD:
                        self.context[i].is_candidator = True
                        continue
                else:
                    # 如果close > ema20
                    if (
                        self.context[i].current_price is not None
                        and self.context[i].current_price
                        > self.stop_manager.ema20[i][0]
                    ):
                        self.order_target_percent(self.datas[i], target=self.p.target)
                        self.context[i].stop_price = min(
                            [
                                self.datas[i].low[-j]
                                for j in range(1, self.p.param_sp + 1)
                            ]
                        )
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.stop_manager.update_stop_price(self.context, self.datas, i)
                # 如果OBOS超买
                if self.obos[i] > OBOS_OVERBUY_THRESHOLD:
                    self.context[i].stop_price = max(
                        self.context[i].stop_price, self.datas[i].low[-1]
                    )

                if self.context[i].current_price < self.context[i].stop_price:  # type: ignore[operator]
                    self.order_target_percent(self.datas[i], target=0.0)
                    self.context[i].order_state = OrderState.ORDER_CLOSING

    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = min(
                [self.datas[i].low[-j] for j in range(1, self.p.param_sp + 1)]
            )

    # def stop(self):
    #     print('ema_period: %d, n_positions: %d' %
    #         (self.p.ema_period, self.p.n_portion))
    #     super().stop()


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

    stocks = load_ingredient_300(args.start)
    tmp = load_ingredient_500(args.start)
    stocks.extend(tmp)
    if args.filter:
        filter_list = args.filter.split()
        stocks = [stock for stock in stocks if stock not in filter_list]

    stocks = drop_delisted_stocks(stocks, args.start, args.end)
    ObosStrategy.stocks = drop_suspended(stocks, args.start, args.end, 10)

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(ObosStrategy, param_sp=range(1, 10))
    else:
        cerebro.addstrategy(ObosStrategy)

    df_stocks = pd.DataFrame(ObosStrategy.stocks, columns=[COL_STOCK_ID])

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=ObosStrategy.stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.STOCK,
    )
