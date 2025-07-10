<<<<<<< HEAD
import argparse
import os
import sys

import backtrader as bt

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common import run, show_position  # noqa: E402
from trend_follow_etf_pool import etf_pool as stocks  # noqa: E402

import conf  # noqa: E402

conf.parse_config()


class Context:
    def __init__(self):
        self.reset()

    def reset(self):
        self.order = False
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


class TrendFollowingStrategy(bt.Strategy):
    params = (
        ("ema_period", 12),
        ("num_positions", 6),  # 最大持仓股票数
        # ('num_positions', 2),       # 最大持仓股票数
        ("p_macd_1_dif", 6),
        ("p_macd_1_dea", 12),
        ("p_macd_1_signal", 5),
        # ('p_macd_2_dif', 6),
        # ('p_macd_2_dea', 12),
        # ('p_macd_2_signal', 5),
        ("period_pct_change", 20),
    )

    def __init__(self):
        self.target = round(1 / (self.p.num_positions), 2)

        self.ema_low = {
            i: bt.indicators.EMA(self.datas[i].low, period=self.p.ema_period)
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
                        if self.datas[i].close[0] > self.ema_low[i][0]:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 如果stop_price < ema_low，则stop_price = ema_low
                if gContext[i].stop_price < self.ema_low[i][-1]:
                    gContext[i].stop_price = self.ema_low[i][-1]

                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)

    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
            gContext[i].stop_price = self.ema_low[i][-1]
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

        show_position(self.positions)


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

    run(
        strategy_name="trend_follow_etf_2",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
    )
||||||| parent of db76fd2 (chore) [deprecate] move obos_hk_2 to deprecate)
import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402
from trend_follow_etf_pool import etf_pool as stocks   # noqa: E402


conf.parse_config()


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()


class TrendFollowingStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('num_positions', 6),       # 最大持仓股票数
            # ('num_positions', 2),       # 最大持仓股票数
            ('p_macd_1_dif', 6),
            ('p_macd_1_dea', 12),
            ('p_macd_1_signal', 5),
            # ('p_macd_2_dif', 6),
            # ('p_macd_2_dea', 12),
            # ('p_macd_2_signal', 5),
            ('period_pct_change', 20),
        )


    def __init__(self):
        self.target = round(1 / (self.params.num_positions), 2)

        self.ema_low = {i: bt.indicators.EMA(self.datas[i].low,
                                             period=self.params.ema_period)
                                             for i in range(len(self.datas))}

        self.macd_1 = {i: bt.indicators.MACD(self.datas[i].close,
                                             period_me1=self.params.p_macd_1_dif,
                                             period_me2=self.params.p_macd_1_dea,
                                             period_signal=self.params.p_macd_1_signal)
                                             for i in range(len(self.datas))}

        self.cross_signal_1 = {i: bt.indicators.CrossOver(self.macd_1[i].macd,
                                                        self.macd_1[i].signal)
                                                        for i in range(len(self.datas))}

        # self.avg_growth = {i: bt.indicators.SimpleMovingAverage(
        #     bt.indicators.PercentChange(self.datas[i].close, period=1), period=20)
        #                    for i in range(len(self.datas))}

        # self.middle = {i: (self.datas[i].high + self.datas[i].low) / 2.0
        #                                             for i in range(len(self.datas))}

        # self.macd_2 = {i: bt.indicators.MACD(self.middle[i],
        #                                      period_me1=self.params.p_macd_2_dif,
        #                                      period_me2=self.params.p_macd_2_dea,
        #                                      period_signal=self.params.p_macd_2_signal)
        #                                      for i in range(len(self.datas))}

        # self.cross_signal_2 = {i: bt.indicators.CrossOver(self.macd_2[i].macd,
        #                                                 self.macd_2[i].signal)
        #                                                 for i in range(len(self.datas))}


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
                    if self.cross_signal_1[i] < 0 or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0:
                        gContext[i].is_candidator = False
                        continue
                    else:
                        if self.datas[i].close[0] > self.ema_low[i][0]:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 如果stop_price < ema_low，则stop_price = ema_low
                if gContext[i].stop_price < self.ema_low[i][-1]:
                    gContext[i].stop_price = self.ema_low[i][-1]

                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
            gContext[i].stop_price = self.ema_low[i][-1]
            gContext[i].is_candidator = False
            return

        if trade.isclosed:
            gContext[i].reset()

        # print('\n---------------------------- TRADE ---------------------------------')
        # print('Size: ', trade.size)
        # print('Price: ', trade.price)
        # print('Value: ', trade.value)
        # print('Commission: ', trade.commission)
        # print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
        # print('--------------------------------------------------------------------\n')


    def stop(self):
        print('(ema_period %d, num_positions %d) Ending Value %.2f' %
              (self.params.ema_period, self.params.num_positions, self.broker.getvalue()))

        show_position(self.positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 num_positions=range(1, len(stocks)))
                                # holding_bars=range(1, 20))
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    run(strategy_name='trend_follow_etf_2', cerebro=cerebro, stocks=stocks,
        start_date=args.start, end_date=args.end)
=======
import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402
from trend_follow_etf_pool import etf_pool as stocks   # noqa: E402


conf.parse_config()


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()


class TrendFollowingStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('num_positions', 6),       # 最大持仓股票数
            # ('num_positions', 2),       # 最大持仓股票数
            ('p_macd_1_dif', 6),
            ('p_macd_1_dea', 12),
            ('p_macd_1_signal', 5),
            # ('p_macd_2_dif', 6),
            # ('p_macd_2_dea', 12),
            # ('p_macd_2_signal', 5),
            ('period_pct_change', 20),
        )


    def __init__(self):
        self.target = round(1 / (self.params.num_positions), 2)

        self.ema_low = {i: bt.indicators.EMA(self.datas[i].low,
                                             period=self.params.ema_period)
                                             for i in range(len(self.datas))}

        self.macd_1 = {i: bt.indicators.MACD(self.datas[i].close,
                                             period_me1=self.params.p_macd_1_dif,
                                             period_me2=self.params.p_macd_1_dea,
                                             period_signal=self.params.p_macd_1_signal)
                                             for i in range(len(self.datas))}

        self.cross_signal_1 = {i: bt.indicators.CrossOver(self.macd_1[i].macd,
                                                        self.macd_1[i].signal)
                                                        for i in range(len(self.datas))}

        # self.avg_growth = {i: bt.indicators.SimpleMovingAverage(
        #     bt.indicators.PercentChange(self.datas[i].close, period=1), period=20)
        #                    for i in range(len(self.datas))}

        # self.middle = {i: (self.datas[i].high + self.datas[i].low) / 2.0
        #                                             for i in range(len(self.datas))}

        # self.macd_2 = {i: bt.indicators.MACD(self.middle[i],
        #                                      period_me1=self.params.p_macd_2_dif,
        #                                      period_me2=self.params.p_macd_2_dea,
        #                                      period_signal=self.params.p_macd_2_signal)
        #                                      for i in range(len(self.datas))}

        # self.cross_signal_2 = {i: bt.indicators.CrossOver(self.macd_2[i].macd,
        #                                                 self.macd_2[i].signal)
        #                                                 for i in range(len(self.datas))}


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
                    if self.cross_signal_1[i] < 0 or self.macd_1[i].macd[0] - self.macd_1[i].macd[-1] <= 0:
                        gContext[i].is_candidator = False
                        continue
                    else:
                        if self.datas[i].close[0] > self.ema_low[i][0]:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 如果stop_price < ema_low，则stop_price = ema_low
                if gContext[i].stop_price < self.ema_low[i][-1]:
                    gContext[i].stop_price = self.ema_low[i][-1]

                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
            gContext[i].stop_price = self.ema_low[i][-1]
            gContext[i].is_candidator = False
            return

        if trade.isclosed:
            gContext[i].reset()

        # print('\n---------------------------- TRADE ---------------------------------')
        # print('Size: ', trade.size)
        # print('Price: ', trade.price)
        # print('Value: ', trade.value)
        # print('Commission: ', trade.commission)
        # print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
        # print('--------------------------------------------------------------------\n')


    def stop(self):
        print('(ema_period %d, num_positions %d) Ending Value %.2f' %
              (self.params.ema_period, self.params.num_positions, self.broker.getvalue()))

        show_position(self.positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 num_positions=range(1, len(stocks)))
                                # holding_bars=range(1, 20))
    else:
        cerebro.addstrategy(TrendFollowingStrategy)

    run(strategy_name='trend_follow_etf_2', cerebro=cerebro, stocks=stocks,
        start_date=args.start, end_date=args.end)
>>>>>>> db76fd2 (chore) [deprecate] move obos_hk_2 to deprecate)
