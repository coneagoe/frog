import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from common.const import COL_CLOSE  # noqa: E402
from factor.momentum import COL_MOMENTUM, compute_momentum  # noqa: E402


def test_compute_momentum_uses_rate_of_return_definition():
    prices = pd.DataFrame({COL_CLOSE: [100.0, 110.0, 121.0, 133.1]})

    result = compute_momentum(prices.copy(), n=2)

    expected = pd.Series([None, None, 0.21, 0.21], name=COL_MOMENTUM)
    pd.testing.assert_series_equal(result[COL_MOMENTUM].round(4), expected.round(4))
