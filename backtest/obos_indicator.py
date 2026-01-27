import backtrader as bt


class OBOS(bt.Indicator):
    """
    OBOS (Overbought/Oversold) Indicator for Backtrader.

    Usage with multiple data feeds:
        self.obos = {i: OBOS(self.datas[i]) for i in range(len(self.datas))}

    Even though __init__ doesn't accept an explicit data parameter, Backtrader's
    MetaIndicator metaclass automatically uses the first positional argument as
    the data feed for the indicator. This means:
        - OBOS(self.datas[0]) → self.data refers to datas[0] (stock 0)
        - OBOS(self.datas[1]) → self.data refers to datas[1] (stock 1)
        - Each instance's self.data points to its respective stock's historical data
    """

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
