import pandas as pd

from common.const import COL_CLOSE

COL_VOLATILITY = "volatility"
VOLATILITY_PARAM_N = 20


def compute_volatility(
    prices: pd.DataFrame, n: int = VOLATILITY_PARAM_N
) -> pd.DataFrame:
    returns = prices[COL_CLOSE].pct_change()
    prices[COL_VOLATILITY] = returns.rolling(n).std()
    return prices
