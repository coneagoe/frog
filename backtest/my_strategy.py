import backtrader as bt


class MyStrategy(bt.Strategy):
    def __init__(self):
        self.trades = []
        self.current_trade = None

    def next(self):
        # Your trading logic here

        # If a trade is opened, record the open time
        if self.order and self.order.status == self.order.Completed and self.order.isbuy():
            self.current_trade = {
                'open_time': self.datas[0].datetime.date(0),
                'open_price': self.order.executed.price,
            }

        # If a trade is closed, record the close time
        if self.order and self.order.status == self.order.Completed and self.order.issell():
            self.current_trade.update({
                'close_time': self.datas[0].datetime.date(0),
                'close_price': self.order.executed.price,
            })
            self.trades.append(self.current_trade)

    def notify_trade(self, trade):
        if trade.isclosed:
            self.current_trade.update({
                'profit': trade.pnl,
            })