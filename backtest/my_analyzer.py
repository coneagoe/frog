import backtrader as bt


class MyAnalyzer(bt.Analyzer):
    def __init__(self):
        super(MyAnalyzer, self).__init__()
        self.cashflow = []
        self.values = []

    def next(self):
        broker = self.strategy.broker
        self.cashflow.append(broker.getcash())
        self.values.append(broker.getvalue())

    def get_analysis(self):
        return self
