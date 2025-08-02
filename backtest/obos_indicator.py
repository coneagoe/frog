import backtrader as bt


class OBOS(bt.Indicator):
    params = (
        ("n", 10),
        ("m", 25),
    )
    lines = ("obos",)

    def __init__(self):
        lowest_price = bt.indicators.Lowest(self.data.low, period=self.p.n)
        highest_price = bt.indicators.Highest(self.data.high, period=self.p.m)
        base = (highest_price - lowest_price) + 1e-8
        ratio = (self.data.close - lowest_price) / base * 4
        self.l.obos = bt.indicators.EMA(ratio, period=4)
