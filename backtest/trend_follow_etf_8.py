import argparse
import logging
import os
import sys
import backtrader as bt
import pandas as pd
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
)   # noqa: E402
from stock import (
    COL_STOCK_ID,
)
from my_strategy import (
    OrderState,
    MyStrategy,
)   # noqa: E402
from stop_price_manager_ema import EmaStopPriceManager as StopPriceManager


conf.parse_config()

# enable_optimize()

# disable_plotly()


class TrendFollowingStrategy(MyStrategy):
    params = (
            ('ema_period', 20),
            ('n_portion', 2), # 每支股票允许持有的n倍最小仓位
            ('p_macd_1_dif', 6),
            ('p_macd_1_dea', 12),
            ('p_macd_1_signal', 5),
            ('param_sp', 5), # 过去n天的最低价作为initial stop price
        )


    def __init__(self):
        super().__init__()

        self.target = round(self.params.n_portion / len(self.stocks), 2)
        if self.target < 0.05:
            self.target = 0.05

        self.macd_1 = {i: bt.indicators.MACD(self.datas[i].close,
                                             period_me1=self.params.p_macd_1_dif,
                                             period_me2=self.params.p_macd_1_dea,
                                             period_signal=self.params.p_macd_1_signal)
                                             for i in range(len(self.datas))}

        self.cross_signal_1 = {i: bt.indicators.CrossOver(self.macd_1[i].macd,
                                                        self.macd_1[i].signal)
                                                        for i in range(len(self.datas))}

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
                    if (self.cross_signal_1[i] < 0
                        or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0):
                        self.context[i].is_candidator = False
                        continue
                    else:
                        if (self.context[i].current_price > self.stop_manager.ema20[i][0]
                            and self.macd_1[i].signal[0] > 0
                            and self.macd_1[i].macd[0] > 0):
                            self.order_target_percent(self.datas[i], target=self.target)
                            self.context[i].order_state = OrderState.ORDER_OPENING
                            self.context[i].stop_price = round(self.stop_manager.ema20[i][-1], 3)
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.stop_manager.update_stop_price(self.context, self.datas, i)

                if self.context[i].current_price < self.context[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)
                    self.context[i].order_state = OrderState.ORDER_CLOSING


    def notify_trade(self, trade):
        super().notify_trade(trade)

        if trade.isopen:
            i = self.stocks.index(trade.getdataname())
            self.context[i].stop_price = round(self.stop_manager.ema20[i][-1], 3)


    def stop(self):
        logging.info('ema_period: %d, n_positions: %d' % (self.params.ema_period, self.params.n_portion))
        # print('ema_period: %d, n_positions: %d' % (self.params.ema_period, self.params.n_portion))
        super().stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    parser.add_argument('-f', '--filter', required=False, help='Space-separated list of stock IDs to filter out')
    parser.add_argument('-c', '--cash', required=False, type=float, default=1000000, help='Initial cash amount')
    parser.add_argument('-p', '--plot', required=False, default='', help='Plot trade')
    parser.add_argument('-l', '--list', required=True, help='Path to CSV file containing stock list')
    args = parser.parse_args()

    os.environ['PLOT_TRADE'] = args.plot
    os.environ['INIT_CASH'] = str(args.cash)

    df = pd.read_csv(args.list, encoding='utf_8_sig', dtype={COL_STOCK_ID: str})
    df[COL_STOCK_ID] = df[COL_STOCK_ID].astype(str)
    stocks = df[COL_STOCK_ID].tolist()

    if args.filter:
        filter_list = args.filter.split()
        stocks = [stock for stock in stocks if stock not in filter_list]

    TrendFollowingStrategy.stocks = stocks

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 # num_positions=range(1, len(stocks)))
                                 # holding_bars=range(1, 20))
                                 n_portion=range(1, 10))
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(strategy_name=strategy_name, cerebro=cerebro, stocks=TrendFollowingStrategy.stocks,
        start_date=args.start, end_date=args.end, security_type='auto')
