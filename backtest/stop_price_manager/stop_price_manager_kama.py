import backtrader as bt
from my_strategy import Context


class StopPriceManagerKama:
    def __init__(self, datas):
        self.kama = {i: bt.indicators.KAMA(datas[i].close)
                        for i in range(len(datas))}

    def update_stop_price(self, context: list[Context], datas, i: int):
        profit_rate = context[i].profit_rate
        if profit_rate < 0.05:
            return
        else:
            context[i].stop_price = max(
                context[i].stop_price,
                round(self.kama[i][-1], 3)
            )
