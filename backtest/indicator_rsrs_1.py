import backtrader as bt
import numpy as np
import statsmodels.api as sm


class RsrsZscore(bt.Indicator):
    lines = ('rsrs', 'beta')
    params = (('N', 18), ('M', 300))

    def __init__(self):
        self.addminperiod(max(self.params.N, self.params.M))

    def next(self):
        highs = np.array(self.data.high.get(size=self.params.N))
        lows = np.array(self.data.low.get(size=self.params.N))

        X = sm.add_constant(lows)
        model = sm.OLS(highs, X).fit()
        self.lines.beta[0] = model.params[1]

        if len(self.lines.rsrs) < self.params.M:
            self.lines.rsrs[0] = 0
        else:
            betas = np.array(self.lines.beta.get(size=self.params.M))
            mean_beta = np.mean(betas)
            std_beta = np.std(betas)
            zscore = (self.lines.beta[0] - mean_beta) / std_beta
            print(f'mean_beta: {mean_beta}, std_beta: {std_beta}, zscore: {zscore}')
            self.lines.rsrs[0] = zscore
