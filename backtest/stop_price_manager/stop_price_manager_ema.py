import backtrader as bt
from my_strategy import Context


class StopPriceManagerEma:
    def __init__(self, datas, profit_rate_threshold: float = 0):
        self.profit_rate_threshold = profit_rate_threshold

        self.ema5 = {i: bt.indicators.EMA(datas[i].close, period=5)
                      for i in range(len(datas))}

        self.ema10 = {i: bt.indicators.EMA(datas[i].close, period=10)
                      for i in range(len(datas))}

        self.ema20 = {i: bt.indicators.EMA(datas[i].close, period=20)
                      for i in range(len(datas))}

        self.ema30 = {i: bt.indicators.EMA(datas[i].close, period=30)
                      for i in range(len(datas))}


    def update_stop_price(self, context: list[Context], datas, i: int):
        profit_rate = context[i].profit_rate
        ema = None
        if profit_rate < self.profit_rate_threshold:
            return
        elif profit_rate < 0.2:
            ema = self.ema30
        elif profit_rate < 0.4:
            ema = self.ema20
        elif profit_rate < 0.6:
            ema = self.ema10
        elif profit_rate < 0.8:
            ema = self.ema5
        else:
            context[i].stop_price = max(
                context[i].stop_price,
                round(datas[i].low[-1], 3)
            )

        if ema is not None:
            context[i].stop_price = max(
                context[i].stop_price,
                round(ema[i][-1], 3)
            )
