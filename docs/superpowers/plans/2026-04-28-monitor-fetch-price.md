# Monitor Fetch Price Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monitor's EastMoney-backed current-price lookup with Tushare-backed price fetching for A shares, A-share ETFs, and Hong Kong stocks without breaking import safety or monitor execution.

**Architecture:** `monitor/price_fetcher.py` becomes the single place that maps `(stock_code, market)` to the correct Tushare realtime interface: `rt_k` for A shares and A-share ETFs, `rt_hk_k` for Hong Kong stocks. Because `rt_k` is rate-limited to one request per minute in the current environment, `monitor/monitor_runner.py` should prefetch a snapshot map once per run and reuse it for every target instead of calling Tushare once per target.

**Tech Stack:** Python 3.11+, Tushare Pro, pandas, numpy, pytest, unittest.mock, poetry

---

## File map

- Modify: `monitor/price_fetcher.py`
  - Add Tushare-backed helpers for token lookup, code normalization, grouped realtime requests, and `fetch_price`.
  - Keep `fetch_current_price()` as a thin compatibility wrapper so existing callers and tests stay simple.
- Modify: `monitor/monitor_runner.py`
  - Prefetch current prices once per monitor run and read target prices from a map to avoid `rt_k` per-target frequency-limit failures.
- Modify: `test/monitor/test_price_fetcher.py`
  - Replace EastMoney-specific assertions with Tushare route and error-handling tests.
- Modify: `test/monitor/test_price_fetcher_imports.py`
  - Keep the import-safety regression test focused on lazy imports and the removal of the EastMoney dependency.
- Modify: `test/monitor/test_monitor_runner.py`
  - Verify monitor runner uses the prefetched price map and still triggers alerts/reset logic correctly.

## Confirmed constraints to implement

- `TUSHARE_TOKEN` is available from `.env` when the app loads environment variables.
- `pro.rt_k(ts_code="600000.SH")` works for A shares and returns a single-row DataFrame with `close`.
- `pro.rt_hk_k(ts_code="00001.HK")` works for Hong Kong stocks and returns a single-row DataFrame with `close`.
- `rt_k` is currently limited to **1 request/minute**, so a one-call-per-target implementation would break multi-target monitor runs.
- User-approved failure behavior: **Tushare only**; no EastMoney fallback; missing token, unsupported market, empty result, or API error should return `np.nan`.

### Task 1: Lock in price-fetcher behavior with failing tests

**Files:**
- Modify: `test/monitor/test_price_fetcher.py`
- Modify: `test/monitor/test_price_fetcher_imports.py`

- [ ] **Step 1: Replace EastMoney-specific tests with Tushare-focused failing tests**

```python
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from monitor.price_fetcher import fetch_current_price, fetch_price


def _install_tushare_stub(monkeypatch, pro_client):
    ts_stub = SimpleNamespace(pro_api=lambda token: pro_client)
    monkeypatch.setitem(sys.modules, "tushare", ts_stub)


def test_fetch_price_a_share_uses_rt_k(monkeypatch):
    pro_client = SimpleNamespace(
        rt_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 1800.5}])
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("600519", "A") == 1800.5


def test_fetch_price_hk_uses_rt_hk_k(monkeypatch):
    pro_client = SimpleNamespace(
        rt_hk_k=lambda ts_code: pd.DataFrame([{"ts_code": ts_code, "close": 64.85}])
    )
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert fetch_price("00001", "HK") == 64.85


def test_fetch_price_returns_nan_without_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    assert np.isnan(fetch_price("600519", "A"))


def test_fetch_price_returns_nan_on_api_error(monkeypatch):
    def _raise(_ts_code):
        raise Exception("频率超限")

    pro_client = SimpleNamespace(rt_k=_raise)
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    _install_tushare_stub(monkeypatch, pro_client)

    assert np.isnan(fetch_price("510300", "ETF"))


def test_fetch_current_price_delegates_to_fetch_price(monkeypatch):
    monkeypatch.setattr("monitor.price_fetcher.fetch_price", lambda code, market: 3.25)
    assert fetch_current_price("510300", "ETF") == 3.25
```

- [ ] **Step 2: Update the import-safety regression so it no longer depends on EastMoney**

```python
import importlib
import sys

MODULES_TO_RESET = [
    "monitor.price_fetcher",
    "tushare",
]


def test_price_fetcher_import_stays_lazy_without_tushare(monkeypatch):
    cached_modules = {}
    for module_name in MODULES_TO_RESET:
        module = sys.modules.pop(module_name, None)
        if module is not None:
            cached_modules[module_name] = module

    monkeypatch.setitem(sys.modules, "tushare", None)

    try:
        module = importlib.import_module("monitor.price_fetcher")
        assert callable(module.fetch_price)
        assert callable(module.fetch_current_price)
    finally:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)
        sys.modules.update(cached_modules)
```

- [ ] **Step 3: Run the focused tests to verify they fail before implementation**

Run: `poetry run pytest test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py -v`

Expected: FAIL because `fetch_price` does not exist yet and `fetch_current_price` still imports EastMoney.

- [ ] **Step 4: Commit the test changes after they pass later in Task 2**

```bash
git add test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py
git commit -m "test: cover tushare monitor price fetcher"
```

### Task 2: Implement Tushare-backed `fetch_price` with grouped snapshot helpers

**Files:**
- Modify: `monitor/price_fetcher.py`
- Test: `test/monitor/test_price_fetcher.py`
- Test: `test/monitor/test_price_fetcher_imports.py`

- [ ] **Step 1: Add code-normalization and lazy-client helpers**

```python
import os
from typing import Iterable

import numpy as np
import pandas as pd


def _create_tushare_client():
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        return None

    try:
        import tushare as ts
    except ImportError:
        return None

    return ts.pro_api(token=token)


def _to_ts_code(stock_code: str, market: str) -> str | None:
    normalized = stock_code.strip()
    if market == "HK":
        return f"{normalized.zfill(5)}.HK"
    if market == "ETF":
        suffix = ".SH" if normalized.startswith("5") else ".SZ"
        return f"{normalized}{suffix}"
    if market == "A":
        suffix = ".SH" if normalized.startswith(("5", "6", "9")) else ".SZ"
        return f"{normalized}{suffix}"
    return None
```

- [ ] **Step 2: Add grouped realtime fetch helpers so one API call can serve many targets**

```python
def _fetch_rt_k_map(pro, ts_codes: list[str]) -> dict[str, float]:
    if not ts_codes:
        return {}

    try:
        df = pro.rt_k(ts_code=",".join(ts_codes))
    except Exception:
        return {}

    if df is None or df.empty or "ts_code" not in df.columns or "close" not in df.columns:
        return {}

    return (
        df[["ts_code", "close"]]
        .dropna(subset=["ts_code", "close"])
        .assign(close=lambda frame: pd.to_numeric(frame["close"], errors="coerce"))
        .dropna(subset=["close"])
        .set_index("ts_code")["close"]
        .astype(float)
        .to_dict()
    )


def _fetch_rt_hk_k_map(pro, ts_codes: list[str]) -> dict[str, float]:
    if not ts_codes:
        return {}

    result = {}
    for ts_code in ts_codes:
        try:
            df = pro.rt_hk_k(ts_code=ts_code)
        except Exception:
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        close = pd.to_numeric(df.iloc[-1]["close"], errors="coerce")
        if pd.notna(close):
            result[ts_code] = float(close)
    return result
```

- [ ] **Step 3: Expose a reusable snapshot map and implement `fetch_price` / `fetch_current_price`**

```python
def fetch_price_map(items: Iterable[tuple[str, str]]) -> dict[tuple[str, str], float]:
    pairs = list(items)
    result = {(stock_code, market): np.nan for stock_code, market in pairs}
    pro = _create_tushare_client()
    if pro is None:
        return result

    a_etf_codes = []
    hk_codes = []
    reverse_lookup = {}

    for stock_code, market in pairs:
        ts_code = _to_ts_code(stock_code, market)
        if ts_code is None:
            continue
        reverse_lookup[ts_code] = (stock_code, market)
        if market == "HK":
            hk_codes.append(ts_code)
        else:
            a_etf_codes.append(ts_code)

    for ts_code, price in _fetch_rt_k_map(pro, a_etf_codes).items():
        result[reverse_lookup[ts_code]] = price

    for ts_code, price in _fetch_rt_hk_k_map(pro, hk_codes).items():
        result[reverse_lookup[ts_code]] = price

    return result


def fetch_price(stock_code: str, market: str) -> float:
    return fetch_price_map([(stock_code, market)]).get((stock_code, market), np.nan)


def fetch_current_price(stock_code: str, market: str) -> float:
    return fetch_price(stock_code, market)
```

- [ ] **Step 4: Run the focused tests to verify the new behavior passes**

Run: `poetry run pytest test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py -v`

Expected: PASS with Tushare-stubbed tests covering A share, ETF error handling, HK realtime, missing token, and lazy imports.

- [ ] **Step 5: Commit the finished price-fetcher slice**

```bash
git add monitor/price_fetcher.py test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py
git commit -m "feat: add tushare monitor price fetching"
```

### Task 3: Switch monitor runs to one snapshot fetch per cycle

**Files:**
- Modify: `monitor/monitor_runner.py`
- Modify: `test/monitor/test_monitor_runner.py`

- [ ] **Step 1: Add a failing regression test for multi-target runs using a prefetched price map**

```python
def test_run_monitor_prefetches_prices_once_for_all_targets():
    first = _make_target(id=1, stock_code="600519", market="A", last_state=False)
    second = _make_target(
        id=2,
        stock_code="00001",
        market="HK",
        last_state=False,
        condition={"type": "price_threshold", "direction": "above", "value": 60.0},
    )

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [first, second]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch(
            "monitor.monitor_runner.fetch_price_map",
            return_value={("600519", "A"): 1400.0, ("00001", "HK"): 64.85},
        ) as mock_prices,
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        summary = run_monitor(frequency="daily")

    mock_prices.assert_called_once()
    assert mock_email.call_count == 2
    assert summary.triggered == 2
```

- [ ] **Step 2: Run the monitor-runner test to verify it fails before the integration change**

Run: `poetry run pytest test/monitor/test_monitor_runner.py::test_run_monitor_prefetches_prices_once_for_all_targets -v`

Expected: FAIL because `monitor_runner` still calls `fetch_current_price()` for each target.

- [ ] **Step 3: Update `monitor_runner` to fetch one snapshot map before the target loop**

```python
from monitor.price_fetcher import fetch_current_price, fetch_history_df, fetch_price_map


def run_monitor(frequency: str = "daily") -> MonitorSummary:
    storage = get_storage()
    storage.ensure_monitor_targets_table()
    targets = storage.load_monitor_targets(frequency=frequency)
    price_map = fetch_price_map((target.stock_code, target.market) for target in targets)

    summary = MonitorSummary(total=len(targets))

    for target in targets:
        try:
            current_price = price_map.get(
                (target.stock_code, target.market),
                fetch_current_price(target.stock_code, target.market),
            )
            ...
```

- [ ] **Step 4: Tighten the fallback so monitor stays Tushare-only**

```python
            current_price = price_map.get((target.stock_code, target.market), np.nan)
```

Use the fallback-free version in the final code so a missing batch result does **not** silently call the old single-target path in a way that can re-trigger the `rt_k` rate limit.

- [ ] **Step 5: Run the monitor tests to verify alerting logic still works**

Run: `poetry run pytest test/monitor/test_monitor_runner.py -v`

Expected: PASS for the new prefetch regression plus the existing trigger/reset tests.

- [ ] **Step 6: Commit the monitor-runner integration**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py
git commit -m "feat: batch monitor realtime price fetches"
```

### Task 4: Final verification and cleanup

**Files:**
- Modify: `monitor/price_fetcher.py`
- Modify: `monitor/monitor_runner.py`
- Modify: `test/monitor/test_price_fetcher.py`
- Modify: `test/monitor/test_price_fetcher_imports.py`
- Modify: `test/monitor/test_monitor_runner.py`

- [ ] **Step 1: Run the targeted monitor test suite**

Run: `poetry run pytest test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py test/monitor/test_monitor_runner.py -v`

Expected: PASS

- [ ] **Step 2: Run repository checks on the touched files**

Run: `poetry run pre-commit run --files monitor/price_fetcher.py monitor/monitor_runner.py test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py test/monitor/test_monitor_runner.py`

Expected: PASS

- [ ] **Step 3: Create the final commit**

```bash
git add monitor/price_fetcher.py monitor/monitor_runner.py test/monitor/test_price_fetcher.py test/monitor/test_price_fetcher_imports.py test/monitor/test_monitor_runner.py
git commit -m "feat: switch monitor prices to tushare"
```

- [ ] **Step 4: Record the implementation note for reviewers**

```text
Monitor current-price fetching now uses Tushare only:
- A shares and A-share ETFs use rt_k
- Hong Kong stocks use rt_hk_k
- Missing token, unsupported markets, empty results, and API failures resolve to np.nan
- Monitor runner batches current-price retrieval per cycle to avoid rt_k 1/min frequency-limit failures
```
