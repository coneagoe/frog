import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf                 # noqa: E402
from common import (
    enable_optimize,
    run,
    show_position,
)   # noqa: E402


conf.parse_config()


# start_date = "20200101"
# end_date = "20240513"

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
    # "csi990001",    # 中华半导体芯片
    "512480", # 半导体ETF
    "513050", # 中概互联网ETF
    # "513010", # 恒生科技30ETF
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
    # "512290", # 生物医药ETF
    ]


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.hold_days = 0


gContext = [Context() for i in range(len(stocks))]


# enable_optimize()

class RotateStrategy(bt.Strategy):
    params = (
            ('ema_period', 12),
            ('n_day_increase', 20),     # n天内涨幅
            # ('num_positions', 3),       # 最大持仓股票数
            ('num_positions', 6),       # 最大持仓股票数
            ('hold_days', 10),          # 持仓天数
        )


    def __init__(self):     # noqa: E303
        self.pct_change = {i: bt.indicators.PercentChange(self.datas[i].close,
                                                          period=self.params.n_day_increase)
                           for i in range(len(self.datas))}
        self.target = round(3 / len(stocks), 2)
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
            if gContext[i].order is False:
                gContext[i].hold_days += 1

                if (i not in selected) and (gContext[i].hold_days >= self.params.hold_days):
                    self.order_target_percent(self.datas[i], target=0.0)
            else:
                if i in selected and self.ema_low[i][0] < self.datas[i].close[0]:
                    self.order_target_percent(self.datas[i], target=self.target)


    def notify_trade(self, trade):
        i = stocks.index(trade.getdataname())
        if trade.isopen:
            gContext[i].order = True
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


    def stop(self):     # noqa: E303
        print('(n_day_increase %d, num_positions %d, hold_days %d) Ending Value %.2f' %
                     (self.params.n_day_increase, self.params.num_positions,
                      self.params.hold_days, self.broker.getvalue()))

        show_position(self.positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-d', '--end', required=True, help='End date in YYYY-MM-DD format')
    args = parser.parse_args()

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(RotateStrategy,
                                # n_day_increase=range(5, 30))
                                num_positions=range(1, len(stocks)))
                                # hold_days=range(1, 20))
    else:
        cerebro.addstrategy(RotateStrategy)

    run(cerebro, stocks, args.start, args.end)

