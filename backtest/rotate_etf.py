import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf                 # noqa: E402
from common import (
    enable_optimize,
    run,
)   # noqa: E402


conf.parse_config()


start_date = "20200101"
end_date = "20240418"

# 股票池
stocks = [
    "513100",   # 纳指ETF
    "159985",   # 豆粕ETF
    "518880",   # 黄金ETF
    "162411",   # 华宝油气ETF
    # "512690",   # 酒ETF
    "sz399987",   # 中证酒
    # "515220",   # 煤炭ETF
    "sz399998",   # 中证煤炭
    "159915",   # 创业板ETF
    "510310",   # 沪深300ETF
    'sh000813',   # 细分化工
    "csi930901",   # 动漫游戏
    # "159869",   # 游戏ETF
    "512890",   # 红利低波ETF
    # "csi990001",    # 中华半导体芯片
    "512480", # 半导体ETF
    # "515700",   # 新能车ETF
    # "512400", # 有色金属ETF
    # "516510", # 云计算ETF
    # "159781", # 科创创业ETF
    # "159866", # 日经ETF
    # "516150", # 稀土ETF
    # "159992", # 创新药ETF
    # "588000", # 科创50ETF
    # "159819", # 人工智能ETF
    # "562500", # 机器人ETF
    # "159667", # 工业母机ETF
    # "512660", # 军工ETF
    # "159647", # 中药ETF
    # "159766", # 旅游ETF
    # "159786", # VRETF
    # "515250", # 智能汽车ETF
    # "512670", # 国防ETF
    # "159790", # 碳中和ETF
    # "159755", # 电池ETF
    # "515790", # 光伏ETF
    # "512290", # 生物医药ETF
    ]


class Context:
    def __init__(self):
        self.order = None
        self.stop_price = None
        self.hold_days = 0


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()

class MyStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('n_day_increase', 20),     # n天内涨幅
            ('num_positions', 3),       # 最大持仓股票数
            ('hold_days', 10),          # 持仓天数
        )


    def __init__(self):     # noqa: E303
        self.pct_change = {i: bt.indicators.PercentChange(self.datas[i].close, 
                                                          period=self.params.n_day_increase)
                           for i in range(len(self.datas))}
        # self.target = round(1 / len(self.datas), 2)
        self.target = round(1 / (self.params.num_positions * 2), 2)
        self.ema_low = {i: bt.indicators.EMA(self.datas[i].low, 
                                             period=self.params.ema_period) 
                                             for i in range(len(self.datas))}


    def next(self):    # noqa: E303
        # 计算所有股票的涨幅
        performance = {i: self.pct_change[i][0] for i in range(len(self.datas))}

        # 按照涨幅降序排列
        performance = sorted(performance.items(), key=lambda item: item[1], reverse=True)

        # 选择涨幅最大的前n个股票
        selected = [stock for stock, change in performance[:self.params.num_positions] if change > 0]

        for i in range(len(self.datas)):
            is_order = gContext[i].order is not None
            if is_order:
                gContext[i].hold_days += 1

                if (i not in selected) and (gContext[i].hold_days >= self.params.hold_days):
                    self.order_target_percent(self.datas[i], target=0.0)
                    gContext[i].order = None
            else:
                if i in selected and self.ema_low[i][0] < self.datas[i].close[0]:
                    gContext[i].order = self.order_target_percent(self.datas[i], target=self.target)
                    gContext[i].hold_days = 0


    # def notify_trade(self, trade):
    #     if trade.isopen:
    #         pass

    #     # if trade.isclosed:
    #     print('\n---------------------------- TRADE ---------------------------------')
    #     print('Size: ', trade.size)
    #     print('Price: ', trade.price)
    #     print('Value: ', trade.value)
    #     print('Commission: ', trade.commission)
    #     print('Profit, Gross: ', trade.pnl, ', Net: ', trade.pnlcomm)
    #     print('--------------------------------------------------------------------\n')


    def stop(self):     # noqa: E303
        print('(n_day_increase %d, num_positions %d, hold_days %d) Ending Value %.2f' %
                     (self.params.n_day_increase, self.params.num_positions,
                      self.params.hold_days, self.broker.getvalue()))

        for data, position in self.positions.items():
            if position:
                print(f'current position(当前持仓): {data._name}, size(数量): {"%.2f" % position.size}')


# 创建Cerebro实例
cerebro = bt.Cerebro()

# 添加策略
cerebro.addstrategy(MyStrategy)
# strats = cerebro.optstrategy(MyStrategy, 
#                              # n_day_increase=range(5, 30))
#                              # num_positions=range(1, 9))
#                              hold_days=range(1, 20))

run(cerebro, stocks, start_date, end_date)
