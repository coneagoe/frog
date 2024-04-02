import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backtrader as bt
from btplotting import (
    BacktraderPlotting,
)
# from btplotting.schemes import Tradimo
import pandas as pd
import conf
from common import (
    set_stocks,
    add_analyzer,
    show_analysis,
)


conf.parse_config()


start_date="20190101"
end_date="20231231"

# 股票池
stocks = [
    "513100", # 纳指ETF
    "159985", # 豆粕ETF
    "518880", # 黄金ETF
    "162411", # 华宝油气ETF
    "512690", # 酒ETF
    "515220", # 煤炭ETF
    "159915", # 创业板ETF
    "510310", # 沪深300ETF
    "159869", # 游戏ETF
    # "512400", # 有色金属ETF
    # "516510", # 云计算ETF
    # "159781", # 科创创业ETF
    # "515700", # 新能车ETF
    # "159866", # 日经ETF
    # "516150", # 稀土ETF
    # "159992", # 创新药ETF
    # "512480", # 半导体ETF
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


class MyStrategy(bt.Strategy):
    params = (
            ('n_day_increase', 13), # n天内涨幅
            ('num_positions', 3),   # 最大持仓股票数
            ('hold_days', 5),       # 持仓天数
            ('printlog', False),
        )


    def __init__(self):
        self.pct_change = {i: bt.indicators.PercentChange(self.datas[i].close, 
                                                          period=self.params.n_day_increase) 
                                                          for i in range(len(self.datas))}
        self.hold_days = {i: 0 for i in range(len(self.datas))}


    def log(self, txt, dt=None, doprint=False):
        ''' Logging function fot this strategy'''
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))


    def next(self):
        # 计算所有股票的涨幅
        performance = {i: self.pct_change[i][0] for i in range(len(self.datas))}

        # 按照涨幅降序排列
        performance = sorted(performance.items(), key=lambda item: item[1], reverse=True)

        # 选择涨幅最大的前3个股票
        selected = [stock for stock, change in performance[:self.params.num_positions] if change > 0]

        # 如果没有股票的涨幅大于0，卖出所有股票
        if not selected:
            for i in range(len(self.datas)):
                self.order_target_percent(self.datas[i], target=0.0)
                self.hold_days[i] = 0  # reset hold days
        else:
            # 平均分配仓位
            target_percent = 1.0 / len(selected)
            for i in selected:
                if self.hold_days[i] < self.params.hold_days:
                    self.order_target_percent(self.datas[i], target=0.3)
                    self.hold_days[i] += 1  # increase hold days
                else:
                    self.order_target_percent(self.datas[i], target=0.0)  # sell if hold days exceed limit
                    self.hold_days[i] = 0  # reset hold days


    def stop(self):
        self.log('Ending Value %.2f' % self.broker.getvalue(), doprint=True)
        # self.log('(n_day_increase %d) Ending Value %.2f' %
        #           (self.params.n_day_increase, self.broker.getvalue()), doprint=True)
        # self.log('(num_positions %d) Ending Value %.2f' %
        #           (self.params.num_positions, self.broker.getvalue()), doprint=True)
        # self.log('(hold_days %d) Ending Value %.2f' %
        #           (self.params.hold_days, self.broker.getvalue()), doprint=True)


# 创建Cerebro实例
cerebro = bt.Cerebro()

# 添加策略
cerebro.addstrategy(MyStrategy)
# strats = cerebro.optstrategy(MyStrategy, 
#                              # n_day_increase=range(5, 30))
#                              # num_positions=range(1, 9)) 
#                              hold_days=range(1, 30))

set_stocks(stocks, start_date, end_date, cerebro)

add_analyzer(cerebro)

# 运行回测
results = cerebro.run()
# results = cerebro.run(maxcpus=1)

show_analysis(results)

# cerebro.plot(style='bar', bardown='red', barup='green', fmt_x_ticks = '%Y-%m-%d', fmt_x_data = '%Y-%m-%d')
p = BacktraderPlotting(style='bar', multiple_tabs=True)
cerebro.plot(p)
# cerebro.plot()
