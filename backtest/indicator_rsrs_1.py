import backtrader as bt
import numpy as np
import statsmodels.api as sm


class RsrsZscore(bt.Indicator):
    lines = ("rsrs", "beta")
    params = (("N", 18), ("M", 300))

    def __init__(self):
        self.addminperiod(max(self.p.N, self.p.M))

    def next(self):
        highs = np.array(self.data.high.get(size=self.p.N))
        lows = np.array(self.data.low.get(size=self.p.N))

        X = sm.add_constant(lows)
        model = sm.OLS(highs, X).fit()
        self.l.beta[0] = model.params[1]

        if len(self.l.rsrs) < self.p.M:
            self.l.rsrs[0] = 0
        else:
            betas = np.array(self.l.beta.get(size=self.p.M))
            mean_beta = np.mean(betas)
            std_beta = np.std(betas)
            zscore = (self.l.beta[0] - mean_beta) / std_beta
            print(f"mean_beta: {mean_beta}, std_beta: {std_beta}, zscore: {zscore}")
            self.l.rsrs[0] = zscore
