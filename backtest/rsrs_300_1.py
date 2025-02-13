import argparse
import os
import sys
import backtrader as bt
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import conf     # noqa: E402
from common import (
    disable_plotly,
    enable_optimize,
    run,
    show_position,
)   # noqa: E402
from my_strategy import MyStrategy  # noqa: E402
from indicator_rsrs_0 import RsrsZscore  # noqa: E402


stocks = ('sh000300', )


conf.parse_config()


class RsrsStrategy(MyStrategy):
    params = (('S', 0.7), )

    def __init__(self):
        super().__init__()
        self.rsrs = RsrsZscore()
        self.ma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)


    def next(self):
        super().next()
        rsrs_value = self.rsrs.rsrs[0]
        print(f'rsrs: {rsrs_value}')
        if not self.position:
            if (rsrs_value > self.params.S 
                and self.context[0].current_price > self.ma20[0]): 
                self.order_target_percent(self.data,0.99)  # enter long
                # self.buy()
        else:
            if rsrs_value < -self.params.S:
                self.close()


    def stop(self):
        print(f'S: {self.params.S}')
        super().stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', required=True, help='Start date in YYYY-MM-DD format')
    parser.add_argument('-e', '--end', required=True, help='End date in YYYY-MM-DD format')
    parser.add_argument('-c', '--cash', required=False, type=float, default=1000000, help='Initial cash amount')
    args = parser.parse_args()

    os.environ['INIT_CASH'] = str(args.cash)

    RsrsStrategy.stocks = stocks

    cerebro = bt.Cerebro()

    if os.environ.get('OPTIMIZER') == 'True':
        strats = cerebro.optstrategy(RsrsStrategy,
                                     period=range(1, 10))
    else:
        cerebro.addstrategy(RsrsStrategy)

    strategy_name = os.path.splitext(os.path.basename(__file__))[0]
    run(strategy_name=strategy_name, cerebro=cerebro, stocks=RsrsStrategy.stocks,
        start_date=args.start, end_date=args.end, security_type='auto')
