import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import backtrader as bt
import pandas as pd

from stock import get_security_name


class OrderState(Enum):
    ORDER_IDLE = 0
    ORDER_OPENING = 1
    ORDER_HOLDING = 2
    ORDER_CLOSING = 3
    ORDER_PRE_OPENING = 4


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
        open_str = self.open_time.strftime("%Y-%m-%d") if self.open_time else "-"
        close_str = self.close_time.strftime("%Y-%m-%d") if self.close_time else "-"
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
        self.profit_rate = 0
        self.score = 0
        self.order_submit_bar = None
        self.order = None
        # 'open' | 'close' | None, 标记当前挂单意图，避免平仓单被误 reset
        self.order_purpose: str | None = None


class MyStrategy(bt.Strategy):
    stocks: list[str] = []

    def __init__(self):
        self.reset()

    def reset(self):
        assert len(self.stocks) > 0, "stocks is empty"
        self.context = [Context() for i in range(len(self.stocks))]
        self.trades: dict[str, list[Trade]] = {stock: [] for stock in self.stocks}
        for i in range(len(self.stocks)):
            self.context[i].name = self.stocks[i]

    def next(self):
        for i in range(len(self.datas)):
            self.context[i].current_price = self.datas[i].close[0]
            # 如果订单处于OPENING状态且超过2个bar未成交，则取消
            if self.context[i].order_state == OrderState.ORDER_OPENING:
                assert isinstance(
                    self.context[i].order_submit_bar, int
                ), f"{self.stocks[i]} order_submit_bar is None"

                # 仅对开仓（buy）挂单做超时取消。平仓单不在这里被 reset。
                if (
                    self.context[i].order_purpose == "open"
                    and len(self.datas[i]) - self.context[i].order_submit_bar  # type: ignore[operator]
                    >= 2
                ):
                    self.cancel(self.context[i].order)
                    # 开仓失败直接重置
                    self.context[i].reset()
            elif self.context[i].order_state == OrderState.ORDER_CLOSING:
                # 可选：也可以添加超时处理，如果平仓挂单长时间不成交则撤单回到持仓
                if isinstance(self.context[i].order_submit_bar, int) and (
                    len(self.datas[i]) - self.context[i].order_submit_bar  # type: ignore[operator]
                    >= 5
                ):
                    # 撤销未及时成交的平仓单，回到持仓状态，保留开仓信息
                    self.cancel(self.context[i].order)
                    self.context[i].order = None
                    self.context[i].order_submit_bar = None
                    self.context[i].order_state = OrderState.ORDER_HOLDING
                    self.context[i].order_purpose = None
            elif self.context[i].order_state == OrderState.ORDER_HOLDING:
                self.context[i].holding_bars += 1
                profit_diff = (
                    self.context[i].current_price - self.context[i].open_price  # type: ignore[operator]
                )
                self.context[i].profit_rate = round(
                    profit_diff / self.context[i].open_price,
                    4,
                )
                self.context[i].score = (
                    self.context[i].profit_rate * 100 + self.context[i].holding_bars
                )

    def notify_order(self, order):
        stock_name = order.data._name
        i = self.stocks.index(stock_name)
        if order.status in [order.Submitted, order.Accepted]:
            self.context[i].name = stock_name
            # 根据当前持仓与订单方向推断目的
            pos = self.broker.getposition(order.data)
            has_position = pos.size != 0
            if order.isbuy():
                # 只有当当前没有持仓时，这才是开仓；否则可能是加仓（视策略需要，可扩展）
                self.context[i].order_state = OrderState.ORDER_OPENING
                self.context[i].order_purpose = "open"
            elif order.issell():
                # 卖单：如果有持仓，则视为平仓/减仓
                if has_position or self.context[i].open_price is not None:
                    self.context[i].order_state = OrderState.ORDER_CLOSING
                    self.context[i].order_purpose = "close"
                else:
                    # 没有持仓又发出卖单(罕见)——仍标记为 closing 但不重置开仓信息
                    self.context[i].order_state = OrderState.ORDER_CLOSING
                    self.context[i].order_purpose = "close"
            else:
                # 其他类型(如调整单)，保守处理
                self.context[i].order_state = OrderState.ORDER_OPENING
                self.context[i].order_purpose = "open"

            self.context[i].order_submit_bar = len(self.datas[i])
            self.context[i].order = order
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
                self.context[i].order_purpose = None
            elif order.issell():
                self.context[i].close_time = bt.num2date(order.executed.dt)
                self.context[i].close_bar = len(self.datas[i])
                self.context[i].close_price = round(order.executed.price, 3)
                # 防御：如果缺失 open_price，尝试从 position 里取（若仍失败则放弃记录收益）
                if self.context[i].open_price is None:
                    pos = self.broker.getposition(order.data)
                    if pos.size and pos.price:
                        try:
                            self.context[i].open_price = round(pos.price, 3)
                        except Exception:  # noqa: BLE001
                            pass
                if self.context[i].open_price is None:
                    logging.error(
                        f"skip trade record due to missing open_price, close_price: {self.context[i].close_price}"
                    )
                    self.context[i].reset()
                    return
                profit_diff = (
                    self.context[i].close_price - self.context[i].open_price  # type: ignore[operator]
                )
                new_trade = Trade(
                    open_price=self.context[i].open_price,  # type: ignore
                    close_price=self.context[i].close_price,  # type: ignore
                    profit_rate=round(
                        profit_diff / self.context[i].open_price,
                        2,
                    ),
                    open_time=self.context[i].open_time,  # type: ignore
                    open_bar=self.context[i].open_bar,  # type: ignore
                    close_time=self.context[i].close_time,  # type: ignore
                    close_bar=self.context[i].close_bar,  # type: ignore
                    holding_time=self.context[i].close_bar  # type: ignore
                    - self.context[i].open_bar,
                )
                self.trades[stock_name].append(new_trade)
                self.context[i].reset()

        elif order.status == order.Margin:
            # logging.warning(order)
            self.cancel(order)

        elif order.status in [order.Canceled, order.Rejected]:
            # 如果是开仓挂单被取消，且尚未建立仓位，则重置；如果是平仓挂单被取消且仍有 open_price，则回退为持仓状态
            pos = self.broker.getposition(order.data)
            if self.context[i].order_purpose == "open" and (
                self.context[i].open_price is None and pos.size == 0
            ):
                self.context[i].reset()
            elif (
                self.context[i].order_purpose == "close"
                and self.context[i].open_price is not None
            ):
                self.context[i].order_state = OrderState.ORDER_HOLDING
                self.context[i].order_purpose = None
                self.context[i].order = None
                self.context[i].order_submit_bar = None
            else:
                self.context[i].reset()

    def notify_trade(self, trade):
        return

        stock_name = trade.getdataname()
        i = self.stocks.index(stock_name)
        if trade.isopen:
            self.context[i].order_state = OrderState.ORDER_HOLDING
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
                profit_rate=round(
                    (self.context[i].close_price - self.context[i].open_price)
                    / self.context[i].open_price,
                    2,
                ),
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

    def show_trades(self):
        for stock_name, trade_list in self.trades.items():
            if len(trade_list) == 0:
                continue

            print(f"Trades for {stock_name}: {get_security_name(stock_name)}")
            for t in trade_list:
                print(f"{t}")

    def show_positions(self):
        openings = []
        holdings = []
        closings = []

        for context in self.context:
            if (
                context.order_state == OrderState.ORDER_PRE_OPENING
                or context.order_state == OrderState.ORDER_OPENING
            ):
                total_value = self.broker.getvalue()
                price = context.current_price if context.current_price else 1
                expected_shares = int((total_value * self.target) / price)
                stock_info = {
                    "代码": context.name,
                    "名称": (
                        get_security_name(context.name)
                        if context.name is not None
                        else "-"
                    ),
                    "预估持仓数": f"{expected_shares}",
                    "止损": (
                        f"{context.stop_price:.3f}"
                        if context.stop_price is not None
                        else "-"
                    ),
                }
                openings.append(stock_info)
            elif context.order_state == OrderState.ORDER_HOLDING:
                stock_info = {
                    "代码": context.name,
                    "名称": (
                        get_security_name(context.name)
                        if context.name is not None
                        else "-"
                    ),
                    "持仓数": f"{context.size:.2f}",
                    "成本": (
                        f"{context.open_price:.3f}"
                        if context.open_price is not None
                        else "-"
                    ),
                    "止损": (
                        f"{context.stop_price:.3f}"
                        if context.stop_price is not None
                        else "-"
                    ),
                    "现价": (
                        f"{context.current_price:.3f}"
                        if context.current_price is not None
                        else "-"
                    ),
                    "开仓时间": (
                        context.open_time.strftime("%Y-%m-%d")
                        if context.open_time is not None
                        else "-"
                    ),
                    "开仓价格": (
                        f"{context.open_price:.3f}"
                        if context.open_price is not None
                        else "-"
                    ),
                    "盈亏": (
                        f"{(context.current_price - context.open_price) * context.size:.2f}"  # noqa: E501
                        if context.current_price is not None
                        and context.open_price is not None
                        else "-"
                    ),
                    "收益率": (
                        f"{(context.profit_rate * 100):.2f}%"
                        if context.profit_rate is not None
                        else "-"
                    ),
                }
                holdings.append(stock_info)
            elif context.order_state == OrderState.ORDER_CLOSING:
                stock_info = {
                    "代码": context.name,
                    "名称": (
                        get_security_name(context.name)
                        if context.name is not None
                        else "-"
                    ),
                    "持仓数": f"{context.size:.2f}",
                    "成本": (
                        f"{context.open_price:.3f}"
                        if context.open_price is not None
                        else "-"
                    ),
                    "止损": (
                        f"{context.stop_price:.3f}"
                        if context.stop_price is not None
                        else "-"
                    ),
                    "现价": (
                        f"{context.current_price:.3f}"
                        if context.current_price is not None
                        else "-"
                    ),
                    "开仓时间": (
                        context.open_time.strftime("%Y-%m-%d")
                        if context.open_time is not None
                        else "-"
                    ),
                    "开仓价格": (
                        f"{context.open_price:.3f}"
                        if context.open_price is not None
                        else "-"
                    ),
                    "盈亏": (
                        f"{(context.current_price - context.open_price) * context.size:.2f}"  # noqa: E501
                        if context.current_price is not None
                        and context.open_price is not None
                        else "-"
                    ),
                    "收益率": (
                        f"{(context.profit_rate * 100):.2f}%"
                        if context.profit_rate is not None
                        else "-"
                    ),
                }
                closings.append(stock_info)

        if openings:
            df = pd.DataFrame(openings)
            print("Opening Positions:")
            print(df.to_string(index=False))

        if holdings:
            df = pd.DataFrame(holdings)
            df.sort_values(by="开仓时间", ascending=False, inplace=True)
            print("Holding Positions:")
            print(df.to_string(index=False))

        if closings:
            df = pd.DataFrame(closings)
            print("Closing Positions:")
            print(df.to_string(index=False))
