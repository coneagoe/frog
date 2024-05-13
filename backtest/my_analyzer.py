import backtrader as bt

class MyAnalyzer(bt.Analyzer):
    def __init__(self):
        self.cashflow = []
        self.values = []

    def next(self):
        self.cashflow.append(self.strategy.broker.getcash())
        self.values.append(self.strategy.broker.getvalue())

    def get_analysis(self):
        return self
