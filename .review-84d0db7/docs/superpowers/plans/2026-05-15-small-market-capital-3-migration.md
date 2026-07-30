# Small Market Capital 3 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `small_market_capital_2.py` as original strategy and move dual-factor logic into a new `small_market_capital_3.py`.

**Architecture:** Copy the current dual-factor implementation into the new strategy file, restore `small_market_capital_2.py` to baseline content from `HEAD`, and align tests to the new strategy filename. Keep strategy behavior unchanged except file ownership.

**Tech Stack:** Python 3.12, pandas, backtrader, pytest, unittest.mock, poetry

---

## File map

- Create: `backtest/small_market_capital_3.py`
- Modify: `backtest/small_market_capital_2.py` (restore to baseline)
- Create: `test/backtest/test_small_market_capital_3.py`
- Delete: `test/backtest/test_small_market_capital_2.py`

### Task 1: Lock migration expectations with failing test import

**Files:**
- Modify: `test/backtest/test_small_market_capital_2.py`
- Test: `test/backtest/test_small_market_capital_2.py::test_build_dual_factor_selection_prefers_small_and_low_vol`

- [ ] **Step 1: Rename test module target to new strategy file**

```python
from backtest.small_market_capital_3 import (
    SmallMarketCapitalStrategy,
    build_dual_factor_selection,
)
```

- [ ] **Step 2: Run a single test to confirm RED before file creation**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py::test_build_dual_factor_selection_prefers_small_and_low_vol -v`

Expected: FAIL with `ModuleNotFoundError` for `backtest.small_market_capital_3`.

### Task 2: Create `small_market_capital_3.py` from current dual-factor logic

**Files:**
- Create: `backtest/small_market_capital_3.py`
- Test: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Copy current dual-factor strategy code into new file**

```bash
cp backtest/small_market_capital_2.py backtest/small_market_capital_3.py
```

- [ ] **Step 2: Update strategy name string in `run(...)` block**

```python
run(
    strategy_name="small_market_capital_3",
    cerebro=cerebro,
    ...
)
```

- [ ] **Step 3: Run test module and verify GREEN**

Run: `poetry run pytest test/backtest/test_small_market_capital_2.py -v`

Expected: PASS

### Task 3: Restore `small_market_capital_2.py` to original baseline

**Files:**
- Modify: `backtest/small_market_capital_2.py`
- Test: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Restore file from commit baseline**

```bash
git restore --source=HEAD -- backtest/small_market_capital_2.py
```

- [ ] **Step 2: Confirm the restored file no longer contains dual-factor helpers**

Run: `rg "build_dual_factor_selection|build_volatility_map|weight_mv|weight_vol|vol_window" backtest/small_market_capital_2.py`

Expected: no matches.

### Task 4: Rename tests to `_3` and run verification

**Files:**
- Create: `test/backtest/test_small_market_capital_3.py`
- Delete: `test/backtest/test_small_market_capital_2.py`

- [ ] **Step 1: Rename test file**

```bash
mv test/backtest/test_small_market_capital_2.py test/backtest/test_small_market_capital_3.py
```

- [ ] **Step 2: Update monkeypatch paths in tests**

```python
monkeypatch.setattr("backtest.small_market_capital_3.get_storage", lambda: fake_storage)
monkeypatch.setattr("backtest.small_market_capital_3.pd.read_sql", lambda *args, **kwargs: candidate)
```

- [ ] **Step 3: Run focused tests**

Run: `poetry run pytest test/backtest/test_small_market_capital_3.py -v`

Expected: PASS

- [ ] **Step 4: Run repo checks on touched files**

Run: `poetry run pre-commit run --files backtest/small_market_capital_2.py backtest/small_market_capital_3.py test/backtest/test_small_market_capital_3.py`

Expected: PASS
