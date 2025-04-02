from enum import Enum
import pandas as pd
from stock import (
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
)


COL_LOWEST = 'lowest'
COL_HIGHEST = 'highest'
COL_OBOS = 'obos'


OBOS_OVERBUY_THRESHOLD = 3.5
OBOS_OVERBUY_THRESHOLD_SHORT = 3.0
OBOS_OVERSELL_THRESHOLD_SHORT = 1.0
OBOS_OVERSELL_THRESHOLD = 0.3


OBOS_PARAM_N = 10
OBOS_PARAM_M = 25


class OBOSState(Enum):
    NEUTRAL = 0
    OVERBUY = 1
    OVERSELL = 2


def compute_overbuy_oversell(prices: pd.DataFrame, n=OBOS_PARAM_N, m=OBOS_PARAM_M) -> pd.DataFrame:
    prices[COL_LOWEST] = prices[COL_LOW].rolling(n).min()
    prices[COL_HIGHEST] = prices[COL_HIGH].rolling(m).max()

    # obos = ema(4, ((prices['COL_CLOSE'] - prices['lowest']) / (prices['highest'] - prices['lowest'])) * 4)
    prices[COL_OBOS] = \
        prices[COL_CLOSE].sub(prices[COL_LOWEST]).div(
            prices[COL_HIGHEST].sub(prices[COL_LOWEST])).mul(4).ewm(span=4).mean()

    return prices
