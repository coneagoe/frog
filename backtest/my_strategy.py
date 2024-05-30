import backtrader as bt


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.order = False
        self.open_time = None
        self.open_price = None
        self.stop_price = None
        self.close_time = None
        self.close_price = None
        self.is_candidator = False
        self.hold_days = 0


class MyStrategy(bt.Strategy):
    def __init__(self):
        self.trades = []
        self.context = None
        self.stocks = None


    def set_context(self, stocks):
        self.stocks = stocks
        self.context = [Context() for i in range(len(stocks))]


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
