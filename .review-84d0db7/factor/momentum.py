import pandas as pd

from common.const import COL_CLOSE

COL_MOMENTUM = "momentum"
MOMENTUM_PARAM_N = 20


def compute_momentum(prices: pd.DataFrame, n: int = MOMENTUM_PARAM_N) -> pd.DataFrame:
    prices[COL_MOMENTUM] = prices[COL_CLOSE].div(prices[COL_CLOSE].shift(n)).sub(1)
    return prices
