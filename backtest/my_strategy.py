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
        self.open_price = None
        self.stop_price = None
        self.close_time = None
        self.close_price = None
        self.is_candidator = False
        self.hold_days = 0


class MyStrategy(bt.Strategy):
    stocks = []

    def __init__(self):
        assert len(self.stocks) > 0, "stocks is empty"
        self.trades = []
        self.context = [Context() for i in range(len(self.stocks))]


    def notify_trade(self, trade):
        i = self.stocks.index(trade.getdataname())
        if trade.isopen:
            self.context[i].order = True
            self.context[i].open_time = trade.data.datetime.datetime()
            self.context[i].open_price = round(trade.price, 3)
            self.context[i].is_candidator = False
            # print(f"{trade.getdataname()}: 开仓价: {self.context[i].open_price}, 止损: {self.context[i].stop_price}")
            return

        if trade.isclosed:
            self.context[i].close_time = trade.data.datetime.datetime()
            self.context[i].close_price = round(trade.price, 3)
            self.trades.append({
                'open_price': self.context[i].open_price,
                'close_price': self.context[i].close_price,
                'profit_rate': round((self.context[i].close_price - self.context[i].open_price) / self.context[i].open_price, 4),
                'open_time': self.context[i].open_time,
                'holding_time': self.context[i].close_time - self.context[i].open_time,
            })
            self.context[i].reset()

        # if trade.isclosed:
        #     self.current_trade.update({
        #         'profit': trade.pnl,
        #     })


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
                    '现价': self.context[i].current_price
                }
                if self.context[i].current_price > self.context[i].stop_price:
                    holding.append(stock_info)
                else:
                    closing.append(stock_info)

        holding_df = pd.DataFrame(holding)
        closing_df = pd.DataFrame(closing)

        if len(holding) > 0:
            print("Holding:")
            print(holding_df.to_string(index=False))

        if len(closing) > 0:
            print("Closing:")
            print(closing_df.to_string(index=False))
