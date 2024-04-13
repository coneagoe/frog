import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf     # noqa: E402
from common import (
    enable_optimize,
    run,
)   # noqa: E402


conf.parse_config()


start_date = "20180101"
end_date = "20240412"

# 股票池
stocks = [
    "513100",   # 纳指ETF
    # "159985",   # 豆粕ETF
    # "518880",   # 黄金ETF
    "162411",   # 华宝油气ETF
    # "512690",   # 酒ETF
    "sz399987",   # 中证酒
    "159915",   # 创业板ETF
    "510310",   # 沪深300ETF
    # "515220",   # 煤炭ETF
    "sz399998",   # 中证煤炭
    # "159869",   # 游戏ETF
    # "csi930901",   # 动漫游戏
    'sh000813',   # 细分化工
#    "512480", # 半导体ETF
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
        self.stop_price = None
        self.is_candidator = False


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()


class TrendFollowingStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('printlog', False),
        )


    def __init__(self):
        # 分别生成根据close、high、low生成EMA
        # self.ema_middle = {i: bt.indicators.EMA(self.datas[i].close, 
        #                                         period=self.params.ema_period) 
        #                                         for i in range(len(self.datas))}
        # self.ema_high = {i: bt.indicators.EMA(self.datas[i].high, 
        #                                       period=self.params.ema_period) 
        #                                       for i in range(len(self.datas))}
        self.ema_low = {i: bt.indicators.EMA(self.datas[i].low, 
                                             period=self.params.ema_period) 
                                             for i in range(len(self.datas))}
        # self.ema_low = {i: bt.indicators.EMA(self.datas[i].close, 
        #                                      period=self.params.ema_period) 
        #                                      for i in range(len(self.datas))}

        # 生成MACD(12, 26, 9)
        self.macd = {i: bt.indicators.MACD(self.datas[i].close, 
                                           period_me1=12, 
                                           period_me2=26, 
                                           period_signal=9) 
                                           for i in range(len(self.datas))}

        # 根据MACD macd和signal是否金叉，生成交叉信号
        self.cross_signal = {i: bt.indicators.CrossOver(self.macd[i].macd, 
                                                        self.macd[i].signal) 
                                                        for i in range(len(self.datas))}


    def log(self, txt, dt=None, doprint=False):
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))


    def next(self):
        # 遍历所有的股票
        for i in range(len(self.datas)):
            is_candidator = gContext[i].is_candidator
            is_order = gContext[i].order is not None
            if not is_order:
                if not is_candidator:
                    # 如果MACD金叉
                    if self.cross_signal[i] > 0:
                        gContext[i].is_candidator = True
                        continue
                else:
                    # 如果MACD死叉或MACD.macd曲线不光滑
                    if self.cross_signal[i] < 0 or self.macd[i].macd[0] - self.macd[i].macd[-1] <= 0:
                        gContext[i].is_candidator = False
                        continue
                    else:
                        # 如果MACD.signal和MACD.macd都>0
                        if self.macd[i].signal[0] > 0 and self.macd[i].macd[0] > 0:
                            # size = self.broker.getcash() / len(self.datas) / self.datas[i].close[0] / 100 * 100
                            # gContext[i].order = self.buy(data=self.datas[i])
                            gContext[i].order = self.order_target_percent(self.datas[i], target=0.1)
                            # 设置stop_price为ema_low
                            gContext[i].stop_price = self.ema_low[i][0]
                            # 从候选股票中移除
                            gContext[i].is_candidator = False
            else:
                # 如果stop_price < ema_low，则stop_price = ema_low
                if gContext[i].stop_price < self.ema_low[i][-1]:
                    gContext[i].stop_price = self.ema_low[i][-1]

                # 如果close < stop_price，平仓
                if self.datas[i].close[0] < gContext[i].stop_price:
                    self.order_target_percent(self.datas[i], target=0.0)  # sell if hold days exceed limit
                    gContext[i].order = None


    # def notify_trade(self, trade):
    #     # if trade.isclosed:
    #     print('\n---------------------------- TRADE ---------------------------------')
    #     print('Size: ', trade.size)
    #     print('Price: ', trade.price)
    #     print('Value: ', trade.value)
    #     print('Commission: ', trade.commission)
    #     print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
    #     print('--------------------------------------------------------------------\n')


    def stop(self):
        # self.log('Ending Value %.2f' % self.broker.getvalue(), doprint=True)
        self.log('(ema_period %d) Ending Value %.2f' %
                  (self.params.ema_period, self.broker.getvalue()), doprint=True)


cerebro = bt.Cerebro()

cerebro.addstrategy(TrendFollowingStrategy)
# strats = cerebro.optstrategy(TrendFollowingStrategy, 
#                              ema_period=range(5, 30))

run(cerebro, stocks, start_date, end_date)
