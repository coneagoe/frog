import backtrader as bt
import pandas as pd
from stock import (
    get_security_name,
)


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.current_price = None
        self.open_time = None
        self.open_bar = None
        self.open_price = None
        self.stop_price = None
        self.close_time = None
        self.close_bar = None
        self.close_price = None
        self.is_candidator = False
        self.holding_bars = 0


class MyStrategy(bt.Strategy):
    stocks = []

    def __init__(self):
        assert len(self.stocks) > 0, "stocks is empty"
        self.context = [Context() for i in range(len(self.stocks))]
        self.trades = {stock: [] for stock in self.stocks}


    def open_position(self, i, percent):
        self.order_target_percent(self.datas[i], target=percent)


    def next(self):
        for i in range(len(self.datas)):
            self.context[i].current_price = self.datas[i].close[0]


    def notify_trade(self, trade):
        stock_name = trade.getdataname()
        i = self.stocks.index(stock_name)
        if trade.isopen:
            self.context[i].order = True
            self.context[i].open_time = trade.open_datetime()
            self.context[i].open_bar = trade.baropen
            self.context[i].open_price = round(trade.price, 3)
            self.context[i].is_candidator = False
            return

        if trade.isclosed:
            self.context[i].close_time = trade.close_datetime()
            self.context[i].close_bar = trade.barclose
            # self.context[i].close_price = round(trade.price, 3)
            self.context[i].close_price = round(self.datas[i].open[0], 3)
            self.trades[stock_name].append({
                'open_price': self.context[i].open_price,
                'close_price': self.context[i].close_price,
                'profit_rate': round((self.context[i].close_price - self.context[i].open_price) / self.context[i].open_price, 4),
                'open_time': self.context[i].open_time,
                'open_bar': self.context[i].open_bar,
                'close_time': trade.close_datetime(),
                'close_bar': trade.barclose,
                'holding_time': trade.barlen,
            })
            self.context[i].reset()


    def stop(self):
        holding = []
        closing = []

        for data, position in self.positions.items():
            if position:
                i = self.stocks.index(data._name)
                stock_info = {
                    '代码': data._name,
                    '名称': get_security_name(data._name),
                    '持仓数': "%.2f" % position.size,
                    '成本': self.context[i].open_price,
                    '止损': self.context[i].stop_price,
                    '现价': self.context[i].current_price,
                    '开仓时间': self.context[i].open_time,
                    '盈亏': "%.2f" % ((self.context[i].current_price - self.context[i].open_price) * position.size),
                    '收益率': "%.2f%%" % ((self.context[i].current_price - self.context[i].open_price) / self.context[i].open_price * 100),
                }
                if ((self.context[i].stop_price is None) 
                    or (self.context[i].current_price > self.context[i].stop_price)):
                    holding.append(stock_info)
                else:
                    closing.append(stock_info)

        if len(holding) > 0:
            holding_df = pd.DataFrame(holding).sort_values(by=u'开仓时间', ascending=False)
            print("Holding:")
            print(holding_df.to_string(index=False))

        if len(closing) > 0:
            closing_df = pd.DataFrame(closing).sort_values(by=u'开仓时间', ascending=False)
            print("Closing:")
            print(closing_df.to_string(index=False))
