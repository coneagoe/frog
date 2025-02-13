from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import backtrader as bt
import pandas as pd
from stock import (
    get_security_name,
)
from backtrader import num2date


class OrderState(Enum):
    ORDER_IDLE = 0
    ORDER_OPENING = 1
    ORDER_HOLDING = 2
    ORDER_CLOSING = 3


@dataclass
class Trade:
    open_price: float
    close_price: float
    profit_rate: float
    open_time: datetime
    open_bar: int
    close_time: datetime
    close_bar: int
    holding_time: int

    def __str__(self):
        open_str = self.open_time.strftime('%Y-%m-%d') if self.open_time else '-'
        close_str = self.close_time.strftime('%Y-%m-%d') if self.close_time else '-'
        return (
            f"开仓时间: {open_str}, 开仓价格: {self.open_price}, "
            f"平仓时间: {close_str}, 平仓价格: {self.close_price}, "
            f"收益率: {self.profit_rate * 100:.2f}%, "
            f"HoldingBars: {self.holding_time})"
        )


class Context:
    def __init__(self):
        self.reset()


    def reset(self):
        self.name = None
        self.order_state = OrderState.ORDER_IDLE
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
        self.size = 0


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
            if self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.context[i].holding_bars += 1


    def notify_order(self, order):
        stock_name = order.data._name
        i = self.stocks.index(stock_name)
        if order.status in [order.Submitted, order.Accepted]:
            self.context[i].name = stock_name
            self.context[i].order_state = OrderState.ORDER_OPENING
        elif order.status == order.Completed:
            if order.executed.price is None:
                self.context[i].reset()
                return

            if order.isbuy():
                self.context[i].order_state = OrderState.ORDER_HOLDING
                self.context[i].open_time = bt.num2date(order.executed.dt)
                self.context[i].open_bar = len(self.datas[i])
                self.context[i].open_price = round(order.executed.price, 3)
                self.context[i].size = order.executed.size
            elif order.issell():
                self.context[i].order_state = OrderState.ORDER_IDLE
                self.context[i].close_time = bt.num2date(order.executed.dt)
                self.context[i].close_bar = len(self.datas[i])
                self.context[i].close_price = round(order.executed.price, 3)
                try:
                    new_trade = Trade(
                        open_price=self.context[i].open_price,
                        close_price=self.context[i].close_price,
                        profit_rate=round((self.context[i].close_price - self.context[i].open_price) / self.context[i].open_price, 2),
                        open_time=self.context[i].open_time,
                        open_bar=self.context[i].open_bar,
                        close_time=self.context[i].close_time,
                        close_bar=self.context[i].close_bar,
                        holding_time=self.context[i].close_bar - self.context[i].open_bar,
                    )
                    self.trades[stock_name].append(new_trade)
                    self.context[i].reset()
                except TypeError:
                    print(f"open_price: {self.context[i].open_price}, close_price: {self.context[i].close_price}")

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            logging.warning(order)
            self.context[i].reset()


    def notify_trade(self, trade):
        return

        stock_name = trade.getdataname()
        i = self.stocks.index(stock_name)
        if trade.isopen:
            self.context[i].order_state = ORDER_HOLDING
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
            new_trade = Trade(
                open_price=self.context[i].open_price,
                close_price=self.context[i].close_price,
                profit_rate=round((self.context[i].close_price - self.context[i].open_price) / self.context[i].open_price, 2),
                open_time=self.context[i].open_time,
                open_bar=self.context[i].open_bar,
                close_time=trade.close_datetime(),
                close_bar=trade.barclose,
                holding_time=trade.barlen,
            )
            self.trades[stock_name].append(new_trade)
            self.context[i].reset()


    def stop(self):
        print(f"Ending Value: {self.broker.getvalue():.2f}")

        self.show_positions()

        self.show_trades()

        # holding = []
        # closing = []

        # for data, position in self.positions.items():
        #     if position:
        #         i = self.stocks.index(data._name)
        #         open_str = self.context[i].open_time.strftime('%Y-%m-%d') if self.context[i].open_time else '-'
        #         stock_info = {
        #             '代码': data._name,
        #             '名称': get_security_name(data._name),
        #             '持仓数': "%.2f" % position.size,
        #             '成本': "%.3f" % self.context[i].open_price,
        #             '止损': "%.3f" % self.context[i].stop_price,
        #             '现价': "%.3f" % self.context[i].current_price,
        #             '开仓时间': open_str,
        #             '盈亏': "%.2f" % ((self.context[i].current_price - self.context[i].open_price) * position.size),
        #             '收益率': "%.2f%%" % ((self.context[i].current_price - self.context[i].open_price) / self.context[i].open_price * 100),
        #         }
        #         if ((self.context[i].stop_price is None) 
        #             or (self.context[i].current_price > self.context[i].stop_price)):
        #             holding.append(stock_info)
        #         else:
        #             closing.append(stock_info)

        # if len(holding) > 0:
        #     holding_df = pd.DataFrame(holding).sort_values(by=u'开仓时间', ascending=False)
        #     print("Holding:")
        #     print(holding_df.to_string(index=False))

        # if len(closing) > 0:
        #     closing_df = pd.DataFrame(closing).sort_values(by=u'开仓时间', ascending=False)
        #     print("Closing:")
        #     print(closing_df.to_string(index=False))


    def show_trades(self):
        for stock_name, trade_list in self.trades.items():
            if len(trade_list) == 0:
                continue

            print(f"Trades for {stock_name}:")
            for t in trade_list:
                print(f"{t}")


    def show_positions(self):
        holdings = []
        for i, data in enumerate(self.datas):
            position = self.getposition(data)
            if position.size != 0:
                context = self.context[i]
                open_time_str = context.open_time.strftime('%Y-%m-%d') if context.open_time else '-'
                stock_info = {
                    '代码': data._name,
                    '名称': get_security_name(data._name),
                    '持仓数': f"{position.size:.2f}",
                    '成本': f"{context.open_price:.3f}" if context.open_price else '-',
                    '止损': f"{context.stop_price:.3f}" if context.stop_price else '-',
                    '现价': f"{context.current_price:.3f}" if context.current_price else '-',
                    '开仓时间': open_time_str,
                    '开仓价格': f"{context.open_price:.3f}" if context.open_price else '-',
                    '盈亏': f"{(context.current_price - context.open_price) * position.size:.2f}"
                            if (context.current_price and context.open_price) else '-',
                    '收益率': f"{((context.current_price - context.open_price) / context.open_price * 100):.2f}%"
                             if (context.current_price and context.open_price) else '-',
                }
                holdings.append(stock_info)

        if holdings:
            df = pd.DataFrame(holdings)
            print("Current Positions:")
            print(df.to_string(index=False))
