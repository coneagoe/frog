import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from backtest.small_market_capital_3 import (  # noqa: E402
    SmallMarketCapitalStrategy,
    build_dual_factor_selection,
)
from common.const import (  # noqa: E402
    COL_IPO_DATE,
    COL_PB,
    COL_PE,
    COL_STOCK_ID,
    COL_TOTAL_MV,
)


def test_build_dual_factor_selection_prefers_small_and_low_vol():
    candidate = pd.DataFrame(
        {
            COL_STOCK_ID: ["A", "B", "C", "D"],
            COL_TOTAL_MV: [100, 500, 200, 400],
        }
    )
    vol_map = {"A": 0.05, "B": 0.01, "C": 0.02, "D": 0.03}

    selected = build_dual_factor_selection(
        candidate_df=candidate,
        vol_map=vol_map,
        top_n=4,
        buy_count=2,
        weight_mv=0.6,
        weight_vol=0.4,
    )

    assert selected == ["C", "A"]


def test_build_dual_factor_selection_drops_missing_vol():
    candidate = pd.DataFrame(
        {
            COL_STOCK_ID: ["A", "B", "C"],
            COL_TOTAL_MV: [100, 200, 300],
        }
    )
    vol_map = {"A": 0.02, "B": 0.03}

    selected = build_dual_factor_selection(
        candidate_df=candidate,
        vol_map=vol_map,
        top_n=3,
        buy_count=3,
        weight_mv=0.6,
        weight_vol=0.4,
    )

    assert "C" not in selected
    assert selected == ["A", "B"]


def test_rebalance_uses_dual_factor_selection(monkeypatch):
    now = pd.Timestamp("2025-08-01")
    candidate = pd.DataFrame(
        {
            COL_STOCK_ID: ["A", "B", "C", "D"],
            COL_TOTAL_MV: [100, 150, 200, 250],
            COL_PB: [1, 1, 1, 1],
            COL_PE: [10, 10, 10, 10],
            COL_IPO_DATE: [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-01"),
            ],
        }
    )

    fake_storage = MagicMock()
    fake_storage.engine = MagicMock()
    monkeypatch.setattr(
        "backtest.small_market_capital_3.get_storage", lambda: fake_storage
    )
    monkeypatch.setattr(
        "backtest.small_market_capital_3.pd.read_sql",
        lambda *args, **kwargs: candidate,
    )
    monkeypatch.setattr(
        "backtest.small_market_capital_3.build_volatility_map",
        lambda *args, **kwargs: {"A": 0.01},
    )

    selected_calls = []

    def _fake_selection(**kwargs):
        selected_calls.append(kwargs)
        return ["A", "B"]

    monkeypatch.setattr(
        "backtest.small_market_capital_3.build_dual_factor_selection",
        _fake_selection,
    )

    filtered_calls = []

    def _fake_filter(codes, market):
        filtered_calls.append((codes, market))
        return ["A"]

    monkeypatch.setattr(
        "backtest.small_market_capital_3.filter_explicit_buy_codes",
        _fake_filter,
        raising=False,
    )

    strategy = SmallMarketCapitalStrategy.__new__(SmallMarketCapitalStrategy)
    strategy.p = type(
        "P",
        (),
        {
            "top_n": 80,
            "buy_count": 2,
            "min_list_days": 730,
            "vol_window": 20,
            "weight_mv": 0.6,
            "weight_vol": 0.4,
        },
    )()
    strategy.stocks = ["A", "B", "C", "D"]
    strategy.datas = [type("D", (), {"_name": "A"})(), type("D", (), {"_name": "B"})()]
    strategy.broker = MagicMock()
    strategy.broker.getposition.return_value = type("Pos", (), {"size": 0})()
    order_target_percent = MagicMock()
    monkeypatch.setattr(strategy, "order_target_percent", order_target_percent)

    strategy.rebalance(now.to_pydatetime().date())

    assert len(selected_calls) == 1
    assert selected_calls[0]["top_n"] == 80
    assert selected_calls[0]["buy_count"] == 2
    assert filtered_calls == [(["A", "B"], "A")]
    order_target_percent.assert_called_once_with(strategy.datas[0], target=1.0)
