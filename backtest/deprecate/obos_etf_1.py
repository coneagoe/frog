import argparse
import os
import sys
import backtrader as bt
import pandas as pd
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    drop_suspended,
)   # noqa: E402
from stock import (
    COL_STOCK_ID,
    drop_delisted_stocks,
)   # noqa: E402
from indicator import (
    OBOS_OVERBUY_THRESHOLD,
    OBOS_OVERSELL_THRESHOLD,
    OBOS_PARAM_N,
    OBOS_PARAM_M,
)
from my_strategy import (
    OrderState,
    MyStrategy,
)   # noqa: E402
from obos_indicator import OBOS
from stop_price_manager_ema import EmaStopPriceManager as StopPriceManager
from trend_follow_etf_pool import etf_pool as stocks   # noqa: E402


conf.parse_config()


# enable_optimize()


class ObosStrategy(MyStrategy):
    params = (
            ('param_n', OBOS_PARAM_N),
            ('param_m', OBOS_PARAM_M),
            ('n_portion', 2), # 每支股票允许持有的n倍最小仓位
        )


    def __init__(self):
        super().__init__()

        self.target = round(self.params.n_portion / len(self.stocks), 2)
        if self.target < 0.02:
            self.target = 0.02

        self.obos = {i: OBOS(self.datas[i], n=self.params.param_n, m=self.params.param_m)
                     for i in range(len(self.datas))}

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
                    if self.context[i].current_price > self.stop_manager.ema20[i][0]:
                        self.order_target_percent(self.datas[i], target=self.target)
                        self.context[i].order_state = OrderState.ORDER_OPENING
                        self.context[i].stop_price = self.datas[i].low[-1]
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.stop_manager.update_stop_price(self.context, self.datas, i)
                # 如果OBOS超买
                if self.obos[i] > OBOS_OVERBUY_THRESHOLD:
                    self.context[i].stop_price = max(self.context[i].stop_price, self.datas[i].low[-1])

                if self.context[i].current_price < self.context[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)
                    self.context[i].order_state = OrderState.ORDER_CLOSING


    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = self.datas[i].low[-1]


    # def stop(self):
    #     print('ema_period: %d, n_positions: %d' %
    #         (self.params.ema_period, self.params.n_portion))
    #     super().stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    parser.add_argument('-f', '--filter', required=False, help='Space-separated list of stock IDs to filter out')
    parser.add_argument('-c', '--cash', required=False, type=float, default=1000000, help='Initial cash amount')
    parser.add_argument('-p', '--plot', required=False, default='', help='Plot trade')
    args = parser.parse_args()

    os.environ['PLOT_TRADE'] = args.plot
    os.environ['INIT_CASH'] = str(args.cash)

    if args.filter:
        filter_list = args.filter.split()
        stocks = [stock for stock in stocks if stock not in filter_list]

    stocks = drop_delisted_stocks(stocks, args.start, args.end)
    ObosStrategy.stocks = drop_suspended(stocks, args.start, args.end, 10)

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(ObosStrategy,
                                 n_portion=range(1, 10))
    else:
        cerebro.addstrategy(ObosStrategy)

    df_stocks = pd.DataFrame(ObosStrategy.stocks, columns=[COL_STOCK_ID])

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(strategy_name=strategy_name, cerebro=cerebro, stocks=ObosStrategy.stocks,
        start_date=args.start, end_date=args.end, security_type='auto')
