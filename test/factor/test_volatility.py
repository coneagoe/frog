import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from common.const import COL_CLOSE  # noqa: E402
from factor.volatility import COL_VOLATILITY, compute_volatility  # noqa: E402


def test_compute_volatility_uses_return_rolling_std():
    prices = pd.DataFrame({COL_CLOSE: [100.0, 110.0, 121.0, 133.1, 146.41]})

    result = compute_volatility(prices.copy(), n=2)

    expected_ret = prices[COL_CLOSE].pct_change()
    expected = expected_ret.rolling(2).std()
    expected.name = COL_VOLATILITY
    pd.testing.assert_series_equal(
        result[COL_VOLATILITY].round(10),
        expected.round(10),
        check_names=True,
    )


def test_compute_volatility_default_window_is_20():
    prices = pd.DataFrame({COL_CLOSE: [100.0 + i for i in range(30)]})

    result = compute_volatility(prices.copy())

    assert result[COL_VOLATILITY].iloc[:20].isna().all()
    assert result[COL_VOLATILITY].iloc[21:].notna().any()
