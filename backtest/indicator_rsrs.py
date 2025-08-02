import backtrader as bt
import numpy as np
import statsmodels.api as sm


class RSRS(bt.Indicator):
    lines = ("rsrs", "R2")

    params = (("N", 18), ("value", 5))

    def __init__(self):
        self.high = self.data.high
        self.low = self.data.low

    def next(self):
        high_N = self.high.get(ago=0, size=self.p.N)
        low_N = self.low.get(ago=0, size=self.p.N)

        try:
            X = sm.add_constant(np.array(low_N))
            model = sm.OLS(np.array(high_N), X)
            results = model.fit()
            self.l.rsrs[0] = results.params[1]
            self.l.R2[0] = results.rsquared
        except Exception:
            self.l.rsrs[0] = 0
            self.l.R2[0] = 0


class RSRS_Norm(bt.Indicator):
    lines = ("rsrs_norm", "rsrs_r2", "beta_right")
    params = (("N", 18), ("M", 300))

    def __init__(self):
        self.rsrs = RSRS()
        self.l.rsrs_norm = (
            self.rsrs - bt.ind.Average(self.rsrs, period=self.p.M)
        ) / bt.ind.StandardDeviation(self.rsrs, period=self.p.M)
        self.l.rsrs_r2 = self.l.rsrs_norm * self.rsrs.R2
        self.l.beta_right = self.rsrs * self.l.rsrs_r2
