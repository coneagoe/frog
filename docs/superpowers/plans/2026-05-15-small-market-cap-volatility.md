# Small Market Cap + Volatility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `small_market_capital_2` from pure small-cap selection to a 60/40 dual-factor ranking (small-cap + low-volatility) while preserving monthly rebalance behavior.

**Architecture:** Keep the existing `rebalance()` pipeline (filters, schedule, order flow), but replace the final selection step with a dual-factor score. Add small, testable helper functions inside `backtest/small_market_capital_2.py` for volatility computation and rank-based scoring. Add a new test module to lock scoring logic and integration behavior with mocked SQL/history data.

**Tech Stack:** Python 3.11+, pandas, backtrader strategy module, pytest, unittest.mock, poetry

---

## File map

- Modify: `backtest/small_market_capital_2.py`
  - Add strategy params: `vol_window`, `weight_mv`, `weight_vol`, `score_method`.
  - Add helper functions for volatility map and dual-factor scoring.
  - Replace current small-cap-only `df_sorted.head(top_n)` selection with weighted rank selection.
- Create: `test/backtest/test_small_market_capital_2.py`
  - Add unit tests for helper behavior and rebalance selection path with mocks.

### Task 1: Lock dual-factor score behavior with failing tests

**Files:**
- Create: `test/backtest/test_small_market_capital_2.py`
- Test: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Write failing helper tests (score ranking + missing volatility removal)**

```python
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from common.const import COL_STOCK_ID, COL_TOTAL_MV  # noqa: E402
from backtest.small_market_capital_2 import build_dual_factor_selection  # noqa: E402


def test_build_dual_factor_selection_prefers_small_and_low_vol():
    candidate = pd.DataFrame(
        {
            COL_STOCK_ID: ["A", "B", "C", "D"],
            COL_TOTAL_MV: [100, 300, 200, 400],  # A smallest, D largest
        }
    )
    vol_map = {"A": 0.05, "B": 0.01, "C": 0.02, "D": 0.03}  # B/C lower vol

    selected = build_dual_factor_selection(
        candidate_df=candidate,
        vol_map=vol_map,
        top_n=4,
        buy_count=2,
        weight_mv=0.6,
        weight_vol=0.4,
    )

    # small-cap preference + low-vol preference should keep A/C in top2
    assert selected == ["A", "C"]


def test_build_dual_factor_selection_drops_missing_vol():
    candidate = pd.DataFrame(
        {
            COL_STOCK_ID: ["A", "B", "C"],
            COL_TOTAL_MV: [100, 200, 300],
        }
    )
    vol_map = {"A": 0.02, "B": 0.03}  # C missing

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
```

- [ ] **Step 2: Run tests to verify RED state**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py::test_build_dual_factor_selection_prefers_small_and_low_vol -v`

Expected: FAIL because `build_dual_factor_selection` is not defined yet.

- [ ] **Step 3: Commit after Task 2 turns tests GREEN**

```bash
git add test/backtest/test_small_market_capital_2.py backtest/small_market_capital_2.py
git commit -m "feat(backtest): add dual-factor selection helpers"
```

### Task 2: Implement volatility map and dual-factor selection helpers

**Files:**
- Modify: `backtest/small_market_capital_2.py`
- Test: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Add helper functions for volatility and scoring**

```python
from common.const import AdjustType, COL_CLOSE, PeriodType


def build_volatility_map(
    storage,
    stock_ids: list[str],
    current_date,
    vol_window: int,
) -> dict[str, float]:
    volatility_map: dict[str, float] = {}
    for stock_id in stock_ids:
        history_df = storage.load_history_data_stock(
            stock_id=stock_id,
            period=PeriodType.DAILY,
            adjust=AdjustType.HFQ,
            end_date=current_date.strftime("%Y-%m-%d"),
        )
        if history_df is None or history_df.empty:
            continue

        close_series = pd.to_numeric(history_df[COL_CLOSE], errors="coerce").dropna()
        if len(close_series) < vol_window:
            continue

        vol = close_series.pct_change().rolling(vol_window).std().iloc[-1]
        if pd.notna(vol):
            volatility_map[stock_id] = float(vol)
    return volatility_map


def build_dual_factor_selection(
    candidate_df: pd.DataFrame,
    vol_map: dict[str, float],
    top_n: int,
    buy_count: int,
    weight_mv: float,
    weight_vol: float,
) -> list[str]:
    df = candidate_df.copy()
    df["volatility"] = df[COL_STOCK_ID].map(vol_map)
    df = df.dropna(subset=["volatility"])
    if df.empty:
        return []

    # size smaller => better; volatility lower => better
    df["mv_score"] = 1.0 - df[COL_TOTAL_MV].rank(pct=True, method="average")
    df["vol_score"] = 1.0 - df["volatility"].rank(pct=True, method="average")
    df["total_score"] = weight_mv * df["mv_score"] + weight_vol * df["vol_score"]

    selected = (
        df.sort_values("total_score", ascending=False)
        .head(min(top_n, len(df)))
        .head(min(buy_count, len(df)))
    )
    return selected[COL_STOCK_ID].tolist()
```

- [ ] **Step 2: Run helper tests**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py -v`

Expected: PASS for the two helper tests.

- [ ] **Step 3: Keep touched factor regression green**

Run: `poetry run pytest test/factor/test_volatility.py -v`

Expected: PASS

### Task 3: Wire helpers into `SmallMarketCapitalStrategy.rebalance`

**Files:**
- Modify: `backtest/small_market_capital_2.py`
- Modify: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Add failing integration-style test for rebalance wiring**

```python
from unittest.mock import MagicMock

import pandas as pd

from backtest.small_market_capital_2 import SmallMarketCapitalStrategy
from common.const import COL_IPO_DATE, COL_PB, COL_PE, COL_STOCK_ID, COL_TOTAL_MV


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
    monkeypatch.setattr("backtest.small_market_capital_2.get_storage", lambda: fake_storage)
    monkeypatch.setattr("backtest.small_market_capital_2.pd.read_sql", lambda *args, **kwargs: candidate)
    monkeypatch.setattr("backtest.small_market_capital_2.build_volatility_map", lambda *args, **kwargs: {"A": 0.01})

    selected_calls = []

    def _fake_selection(**kwargs):
        selected_calls.append(kwargs)
        return ["A", "B"]

    monkeypatch.setattr(
        "backtest.small_market_capital_2.build_dual_factor_selection",
        _fake_selection,
    )

    strategy = SmallMarketCapitalStrategy.__new__(SmallMarketCapitalStrategy)
    strategy.p = type("P", (), {"top_n": 80, "buy_count": 2, "min_list_days": 730, "vol_window": 20, "weight_mv": 0.6, "weight_vol": 0.4})()
    strategy.stocks = ["A", "B", "C", "D"]
    strategy.datas = [type("D", (), {"_name": "A"})(), type("D", (), {"_name": "B"})()]
    strategy.broker = MagicMock()
    strategy.broker.getposition.return_value = type("P", (), {"size": 0})()
    strategy.order_target_percent = MagicMock()

    strategy.rebalance(now.to_pydatetime().date())

    assert len(selected_calls) == 1
    assert selected_calls[0]["top_n"] == 80
    assert selected_calls[0]["buy_count"] == 2
    assert strategy.order_target_percent.call_count == 2
```

- [ ] **Step 2: Run this test and confirm RED state**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py::test_rebalance_uses_dual_factor_selection -v`

Expected: FAIL before rebalance wiring is complete.

- [ ] **Step 3: Replace current selection segment in `rebalance()`**

```python
        vol_map = build_volatility_map(
            storage=storage,
            stock_ids=df[COL_STOCK_ID].tolist(),
            current_date=current_date,
            vol_window=self.p.vol_window,
        )
        selected_stocks = build_dual_factor_selection(
            candidate_df=df,
            vol_map=vol_map,
            top_n=self.p.top_n,
            buy_count=self.p.buy_count,
            weight_mv=self.p.weight_mv,
            weight_vol=self.p.weight_vol,
        )

        if not selected_stocks:
            print(f"No stocks pass dual factor selection for {date_str}")
            return

        buy_num = min(self.p.buy_count, len(selected_stocks))
        target_weight = 1.0 / buy_num
```

- [ ] **Step 4: Extend strategy params**

```python
    params = (
        ("top_n", 80),
        ("buy_count", 20),
        ("min_list_days", 730),
        ("vol_window", 20),
        ("weight_mv", 0.6),
        ("weight_vol", 0.4),
    )
```

- [ ] **Step 5: Run backtest module tests**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py -v`

Expected: PASS

- [ ] **Step 6: Commit rebalance integration**

```bash
git add backtest/small_market_capital_2.py test/backtest/test_small_market_capital_2.py
git commit -m "feat(backtest): integrate volatility with small-cap ranking"
```

### Task 4: Verification and guardrails

**Files:**
- Modify: `backtest/small_market_capital_2.py`
- Modify: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Run full relevant test slice**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py test/factor/test_volatility.py -v`

Expected: PASS

- [ ] **Step 2: Run pre-commit on touched files**

Run: `poetry run pre-commit run --files backtest/small_market_capital_2.py test/backtest/test_small_market_capital_2.py`

Expected: PASS

- [ ] **Step 3: Final commit**

```bash
git add backtest/small_market_capital_2.py test/backtest/test_small_market_capital_2.py
git commit -m "test(backtest): cover small-cap volatility dual-factor flow"
```
