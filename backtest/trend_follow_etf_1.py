import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402


conf.parse_config()


start_date = "20200101"
end_date = "20240508"

# 股票池
stocks = [
    "513100",   # 纳指ETF
    "159985",   # 豆粕ETF
    "518880",   # 黄金ETF
    "162411",   # 华宝油气ETF
    # "512690",   # 酒ETF
    "sz399987",   # 中证酒
    "510310",   # 沪深300ETF
    "512100",   # 中证1000ETF
    "159915",   # 创业板ETF
    # "515220",   # 煤炭ETF
    "sz399998",   # 中证煤炭
    # "159869",   # 游戏ETF
    "csi930901",   # 动漫游戏
    'sh000813',   # 细分化工
    "512890",   # 红利低波ETF
    "512480",   # 半导体ETF
    "513050",   # 中概互联网ETF
    # "513010",   # 恒生科技30ETF
#    "159866", # 日经ETF
#    "159819", # 人工智能ETF
#    "562500", # 机器人ETF
#    "516510", # 云计算ETF
#    "159667", # 工业母机ETF
#    "512660", # 军工ETF
#    "159647", # 中药ETF
#    "159766", # 旅游ETF
#    "516150", # 稀土ETF
#    "159786", # VRETF
#    "515250", # 智能汽车ETF
#    "512670", # 国防ETF
#    "159790", # 碳中和ETF
#    "159781", # 科创创业ETF
#    "159755", # 电池ETF
#    "588000", # 科创50ETF
#    "515790", # 光伏ETF
#    "512400", # 有色金属ETF
#    "512290", # 生物医药ETF
#    "159992", # 创新药ETF
#    "515700", # 新能车ETF
    ]


class Context:
    def __init__(self):
        self.order = None
        self.open_price = None
        self.stop_price = None
        self.is_candidator = False

    def reset(self):
        self.order = None
        self.open_price = None
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
            ('p_macd_2_dif', 6),
            ('p_macd_2_dea', 12),
            ('p_macd_2_signal', 5),
        )


    def __init__(self):
        self.target = round(1 / (self.params.num_positions), 2)
        # self.target = round(1 / len(stocks), 2)

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
            if gContext[i].order is None:
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
                        if self.datas[i].close[0] > self.ema_low[i][0] \
                            and self.macd_1[i].signal[0] > 0 and self.macd_1[i].macd[0] > 0:
                            self.order_target_percent(self.datas[i], target=self.target)
            else:
                # 如果stop_price < ema_low，则stop_price = ema_low
                if gContext[i].stop_price < self.ema_low[i][-1]:
                    gContext[i].stop_price = self.ema_low[i][-1]

                # 如果close < stop_price，平仓
                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)  # sell if hold days exceed limit
                    # gContext[i].reset()


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            # print(f"foo: {trade.getdataname()}, price: {trade.price}, index: {i}")
            gContext[i].order = True
            gContext[i].open_price = trade.price
            gContext[i].stop_price = self.ema_low[i][-1]
            gContext[i].is_candidator = False
            return

        if trade.isclosed:
            gContext[i].reset()

    #     print('\n---------------------------- TRADE ---------------------------------')
    #     print('Size: ', trade.size)
    #     print('Price: ', trade.price)
    #     print('Value: ', trade.value)
    #     print('Commission: ', trade.commission)
    #     print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
    #     print('--------------------------------------------------------------------\n')


    def stop(self):
        print('(ema_period %d, num_positions %d) Ending Value %.2f' %
              (self.params.ema_period, self.params.num_positions, self.broker.getvalue()))

        show_position(self.positions)


cerebro = bt.Cerebro()

if os.environ.get('OPTIMIZER') == 'True':
    strats = cerebro.optstrategy(TrendFollowingStrategy,
                                 # ema_period=range(5, 30))
                                 num_positions=range(1, len(stocks)))
else:
    cerebro.addstrategy(TrendFollowingStrategy)

run(cerebro, stocks, start_date, end_date)
