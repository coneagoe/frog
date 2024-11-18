import backtrader as bt

class MyAnalyzer(bt.Analyzer):
    cashflow = []
    values = []

    def next(self):
        broker = self.strategy.broker
        self.cashflow.append(broker.getcash())
        self.values.append(broker.getvalue())


    def get_analysis(self):
        return self
