import argparse
import os
import sys

import backtrader as bt
import pandas as pd

from .bt_common import drop_suspended, run
from .my_strategy import MyStrategy, OrderState, parse_args
from .obos_indicator import OBOS
from .stop_price_manager import StopPriceManagerEma as StopPriceManager

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from common.const import COL_STOCK_ID, SecurityType  # noqa: E402
from indicator import OBOS_OVERBUY_THRESHOLD, OBOS_OVERSELL_THRESHOLD  # noqa: E402
from stock import drop_st  # noqa: E402

conf.parse_config()


class ObosStrategy(MyStrategy):
    params = (
        ("param_sp", 5),  # 过去n天的最低价作为initial stop price
        ("target", 0.01),  # 单笔仓位占比
    )

    def __init__(self):
        super().__init__()

        self.obos = {i: OBOS(data=self.datas[i]) for i in range(len(self.datas))}

        self.kdj = {
            i: bt.indicators.Stochastic(
                self.datas[i],
                period=14,  # 增加到14天，减少敏感度
                period_dfast=3,  # K值的平滑周期
                period_dslow=3,  # D值的平滑周期
                safediv=True,  # 启用安全除法，避免除零错误
            )
            for i in range(len(self.datas))
        }

        self.stop_manager = StopPriceManager(self.datas, 0.2)

    def is_over_sell(self, i):
        try:
            j_value = 3 * self.kdj[i].percK[0] - 2 * self.kdj[i].percD[0]
            kdj_oversell = j_value < -10
        except (ZeroDivisionError, IndexError):
            kdj_oversell = False

        return (self.obos[i] < OBOS_OVERSELL_THRESHOLD) or kdj_oversell

    def next(self):
        super().next()

        for i in range(len(self.datas)):
            if self.context[i].order_state == OrderState.ORDER_IDLE:
                if self.context[i].is_candidator is False:
                    if self.is_over_sell(i):
                        self.context[i].is_candidator = True
                        continue
                else:
                    # 如果close > ema20
                    if self.context[i].current_price > self.stop_manager.ema20[i][0]:
                        self.order_target_percent(self.datas[i], target=self.p.target)
                        self.context[i].stop_price = min(
                            [
                                self.datas[i].low[-j]
                                for j in range(1, self.p.param_sp + 1)
                            ]
                        )
                        self.context[i].order_state = OrderState.ORDER_PRE_OPENING
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


def read_stock_df(filename: str) -> pd.DataFrame:
    path = os.path.join(os.path.dirname(__file__), "..", filename)
    df = pd.read_csv(path, encoding="utf_8_sig", dtype={COL_STOCK_ID: str})
    df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
    return df


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

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    parse_args(args, strategy_name)

    df = read_stock_df("game.csv")
    df0 = read_stock_df("cigarette.csv")
    df = pd.concat([df, df0], ignore_index=True)
    df0 = read_stock_df("vape.csv")
    df = pd.concat([df, df0], ignore_index=True)
    df0 = read_stock_df("wine.csv")
    df = pd.concat([df, df0], ignore_index=True)
    df0 = read_stock_df("beer.csv")
    df = pd.concat([df, df0], ignore_index=True)
    df = df.drop_duplicates(subset=[COL_STOCK_ID])
    df = drop_st(pd.DataFrame(df[COL_STOCK_ID]))
    stocks = df[COL_STOCK_ID].tolist()

    if args.filter:
        filter_list = args.filter.split()
        stocks = [stock for stock in stocks if stock not in filter_list]

    ObosStrategy.stocks = drop_suspended(stocks, args.start, args.end, 10)

    cerebro = bt.Cerebro()

    if os.environ.get("OPTIMIZER") == "True":
        strats = cerebro.optstrategy(ObosStrategy, param_sp=range(1, 10))
    else:
        cerebro.addstrategy(ObosStrategy)

    df_stocks = pd.DataFrame(ObosStrategy.stocks, columns=[COL_STOCK_ID])

    run(
        strategy_name=strategy_name,
        cerebro=cerebro,
        stocks=ObosStrategy.stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.AUTO,
    )
