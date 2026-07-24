# HK yfinance History Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add yfinance as the default source for Hong Kong stock daily BFQ history while retaining Tushare and AkShare fallbacks.

**Architecture:** Add a yfinance-only adapter which validates HK daily BFQ requests and translates raw Yahoo OHLCV to the existing eleven-column HK history contract. Register it in the existing provider dispatcher and make it the first configured default; `DownloadManager` fallback behavior remains unchanged.

**Tech Stack:** Python 3.11+, pandas, yfinance 0.2.55, pytest, Ruff, uv.

## Global Constraints

- Support HK stocks only, with `PeriodType.DAILY` and `AdjustType.BFQ` only.
- Request raw Yahoo OHLCV (`auto_adjust=False`); do not persist `Adj Close`.
- Convert the caller's inclusive `end_date` into yfinance's exclusive end date by adding one day.
- Convert five-digit HK IDs to Yahoo symbols by removing leading zeroes and appending `.HK`: `03738` becomes `3738.HK`; persist the original ID.
- Produce the exact `download.dl.downloader_tushare.hk_history_columns` schema and dtypes.
- Estimate `成交额` as raw `收盘 * 成交量`, because Yahoo does not provide transaction amount.
- Mock every yfinance interaction; tests must make no network calls.
- Use `uv run` for Python, pytest, and Ruff commands.

---

## File Structure

- Create `download/dl/downloader_yfinance.py`: yfinance request, validation, ticker/date conversion, and canonical HK dataframe normalization.
- Create `test/download/dl/test_downloader_yfinance.py`: mocked adapter contract tests.
- Modify `download/dl/downloader.py`: register the yfinance HK adapter.
- Modify `download/provider_order.py`: allow yfinance and make it the first HK default.
- Modify `test/download/dl/test_downloader.py`: dispatcher test.
- Modify `test/download/test_provider_order.py`: default-order and explicit-provider tests.
- Modify `test/download/test_download_manager.py`: manager fallback-order test.

### Task 1: Implement the yfinance HK adapter from a failing happy-path test

**Files:**
- Create: `download/dl/downloader_yfinance.py`
- Create: `test/download/dl/test_downloader_yfinance.py`

**Interfaces:**
- Consumes: `PeriodType`, `AdjustType`, and `COL_*` values from `common.const`; `convert_date`, `hk_history_columns`, and `_empty_hk_history_dataframe` from `download.dl.downloader_tushare`.
- Produces: `download_history_data_stock_hk_yf(stock_id: str, start_date: str, end_date: str, period: PeriodType = PeriodType.DAILY, adjust: AdjustType = AdjustType.BFQ) -> pd.DataFrame`.

- [ ] **Step 1: Write the failing normalization test**

Create a fixture that stubs `yfinance.Ticker`. Make `Ticker.history()` return a one-row, timezone-aware dataframe with `Open`, `High`, `Low`, `Close`, `Adj Close`, and `Volume`. Add this test:

```python
def test_download_history_data_stock_hk_yf_normalizes_raw_daily_history(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame(
        {
            "Open": [10.0], "High": [12.0], "Low": [9.0],
            "Close": [11.0], "Adj Close": [10.5], "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2026-01-02"], tz="Asia/Hong_Kong"),
    )

    result = module.download_history_data_stock_hk_yf("03738", "2026-01-01", "2026-01-02")

    ticker.assert_called_once_with("3738.HK")
    ticker.return_value.history.assert_called_once_with(
        start="2026-01-01", end="2026-01-03", interval="1d",
        auto_adjust=False, actions=False, back_adjust=False, repair=False,
        prepost=False, raise_errors=True,
    )
    assert list(result.columns) == module.hk_history_columns
    assert result[module.COL_STOCK_ID].tolist() == ["03738"]
    assert result[module.COL_CLOSE].tolist() == [11.0]
    assert result[module.COL_AMOUNT].tolist() == [11000.0]
    assert result[module.COL_CHANGE].tolist() == [0.0]
```

Add a second assertion using `end_date="2026/01/02"` so supported repository date formats still produce the ISO exclusive end `2026-01-03`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest test/download/dl/test_downloader_yfinance.py -q`

Expected: collection fails because `download.dl.downloader_yfinance` does not exist.

- [ ] **Step 3: Write the minimal adapter**

Create `download/dl/downloader_yfinance.py`. Validate with `re.fullmatch(r"\d{5}", stock_id)` and raise `ValueError("Stock ID must be 5 digits.")`; derive the symbol with `f"{int(stock_id):04d}.HK"`. Reject non-daily periods and non-BFQ adjustments with provider-specific `ValueError`s.

Implement the request boundary exactly:

```python
start = datetime.strptime(convert_date(start_date), "%Y%m%d").strftime("%Y-%m-%d")
end = (
    datetime.strptime(convert_date(end_date), "%Y%m%d") + timedelta(days=1)
).strftime("%Y-%m-%d")
raw = yf.Ticker(symbol).history(
    start=start, end=end, interval="1d", auto_adjust=False, actions=False,
    back_adjust=False, repair=False, prepost=False, raise_errors=True,
)
```

For valid non-empty rows, require `Open`, `High`, `Low`, `Close`, and `Volume`. Convert the index into `COL_DATE` without timezone data, map Yahoo fields to existing Chinese constants, retain the original `stock_id`, calculate `COL_AMOUNT = COL_CLOSE * COL_VOLUME`, set `COL_CHANGE`, `COL_CHANGE_RATE`, and `COL_TURNOVER_RATE` to `0.0`, reindex to `hk_history_columns`, convert numeric columns to `float64`, and `reset_index(drop=True)`. Ignore `Adj Close`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest test/download/dl/test_downloader_yfinance.py -q`

Expected: PASS for ticker conversion, raw request arguments, exclusive end date, canonical order, original ID, ignored adjusted close, and estimated amount.

- [ ] **Step 5: Commit**

```bash
git add download/dl/downloader_yfinance.py test/download/dl/test_downloader_yfinance.py
git commit -m "feat: add yfinance HK history downloader"
```

### Task 2: Cover adapter validation and invalid provider responses

**Files:**
- Modify: `download/dl/downloader_yfinance.py`
- Modify: `test/download/dl/test_downloader_yfinance.py`

**Interfaces:**
- Consumes: `download_history_data_stock_hk_yf` from Task 1.
- Produces: canonical empty results, explicit response-schema errors, and unmodified provider exceptions for the manager fallback loop.

- [ ] **Step 1: Write failing boundary tests**

Add parameterized tests for invalid IDs `"700"`, `"0700"`, `"03738.HK"`, and `"ABCDE"`, asserting `Ticker` is not called. Add tests for `PeriodType.WEEKLY` and `AdjustType.QFQ`, also with no client invocation. Add the following result tests:

```python
def test_download_history_data_stock_hk_yf_empty_result_uses_canonical_schema(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame()
    result = module.download_history_data_stock_hk_yf("00700", "20260101", "20260102")
    assert result.empty
    assert list(result.columns) == module.hk_history_columns

def test_download_history_data_stock_hk_yf_missing_required_column_raises(downloader_yf_module):
    module, ticker = downloader_yf_module
    ticker.return_value.history.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [1.0], "Close": [2.0]}
    )
    with pytest.raises(ValueError, match="Missing required column 'Volume'"):
        module.download_history_data_stock_hk_yf("00700", "20260101", "20260102")
```

Set `Ticker.history.side_effect = RuntimeError("Yahoo unavailable")` in a final test and assert that exception propagates.

- [ ] **Step 2: Run the boundary tests to verify failure**

Run: `uv run pytest test/download/dl/test_downloader_yfinance.py -q`

Expected: failure until empty, schema, and propagation semantics are exact.

- [ ] **Step 3: Implement the minimal failure behavior**

Use these explicit rules:

```python
if raw is None or raw.empty:
    return _empty_hk_history_dataframe()

missing = {"Open", "High", "Low", "Close", "Volume"}.difference(raw.columns)
if missing:
    raise ValueError(
        f"Missing required column '{sorted(missing)[0]}' in yfinance history response"
    )
```

Do not catch `Ticker.history()` exceptions; `DownloadManager._download_hk_stock_history_with_fallback()` already logs the failure and tries the next provider.

- [ ] **Step 4: Run the complete adapter module**

Run: `uv run pytest test/download/dl/test_downloader_yfinance.py -q`

Expected: PASS for success, normalization, empty data, invalid input, missing data, and client errors.

- [ ] **Step 5: Commit**

```bash
git add download/dl/downloader_yfinance.py test/download/dl/test_downloader_yfinance.py
git commit -m "test: cover yfinance HK history failures"
```

### Task 3: Register yfinance and configure it as the first HK provider

**Files:**
- Modify: `download/dl/downloader.py:20-46`
- Modify: `download/provider_order.py:7-9`
- Modify: `test/download/dl/test_downloader.py:253-281`
- Modify: `test/download/test_provider_order.py:35-58`

**Interfaces:**
- Consumes: adapter from Task 1.
- Produces: provider dispatch accepts `"yfinance"`; `parse_hk_stock_history_provider_order()` defaults to `['yfinance', 'tushare', 'akshare']`.

- [ ] **Step 1: Write failing registry and provider-order tests**

Add this dispatcher test, following the existing stock-provider test pattern:

```python
def test_dl_history_data_stock_hk_by_provider_dispatches_to_yfinance(monkeypatch):
    calls = []
    def fake_yfinance(stock_id, start_date, end_date, period, adjust):
        calls.append((stock_id, start_date, end_date, period, adjust))
        return "ok"

    monkeypatch.setitem(downloader_module.HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS, "yfinance", fake_yfinance)
    result = Downloader().dl_history_data_stock_hk_by_provider(
        "yfinance", "00700", "20260101", "20260102", PeriodType.DAILY, AdjustType.BFQ
    )
    assert result == "ok"
    assert calls == [("00700", "20260101", "20260102", PeriodType.DAILY, AdjustType.BFQ)]
```

Change the existing default-order expectation and add:

```python
def test_parse_hk_stock_history_provider_order_accepts_yfinance():
    assert parse_hk_stock_history_provider_order(" yfinance, akshare, yfinance ") == ["yfinance", "akshare"]
```

- [ ] **Step 2: Run focused registry tests to verify failure**

Run: `uv run pytest test/download/dl/test_downloader.py test/download/test_provider_order.py -q`

Expected: failures because yfinance is not registered or allowed yet.

- [ ] **Step 3: Implement the registration and default order**

Import `download_history_data_stock_hk_yf` in `download/dl/downloader.py`, then make the mapping:

```python
HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS = {
    "yfinance": download_history_data_stock_hk_yf,
    "tushare": download_history_data_stock_hk_ts,
    "akshare": download_history_data_stock_hk_ak,
}
```

In `download/provider_order.py`, set:

```python
DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER = ("yfinance", "tushare", "akshare")
VALID_HK_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)
```

Do not change legacy `Downloader.dl_history_data_stock_hk`; provider selection already uses `dl_history_data_stock_hk_by_provider`.

- [ ] **Step 4: Run focused registry tests to verify success**

Run: `uv run pytest test/download/dl/test_downloader.py test/download/test_provider_order.py -q`

Expected: PASS for dispatch, yfinance validity, deduplication, and yfinance-first default ordering.

- [ ] **Step 5: Commit**

```bash
git add download/dl/downloader.py download/provider_order.py test/download/dl/test_downloader.py test/download/test_provider_order.py
git commit -m "feat: prefer yfinance for HK history"
```

### Task 4: Verify manager-level fallback ordering and complete focused checks

**Files:**
- Modify: `test/download/test_download_manager.py:640-781`

**Interfaces:**
- Consumes: default provider configuration from Task 3 and existing `DownloadManager._download_hk_stock_history_with_fallback()`.
- Produces: evidence that yfinance is attempted first and a failure continues to Tushare then AkShare without changing manager logic.

- [ ] **Step 1: Write the fallback-order test**

Add a test without monkeypatching `parse_hk_stock_history_provider_order`, using the neighboring storage fixture pattern:

```python
def test_download_hk_ggt_history_uses_yfinance_then_falls_back(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_hk_stock.return_value = True
    monkeypatch.setattr(dm, "get_storage", lambda: storage)
    manager = DownloadManager()
    download_mock = MagicMock(side_effect=[
        RuntimeError("Yahoo unavailable"), RuntimeError("rate limited"), _hk_stock_history_df(),
    ])
    monkeypatch.setattr(manager.downloader, "dl_history_data_stock_hk_by_provider", download_mock)

    assert manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ)
    assert [call.args[0] for call in download_mock.call_args_list] == ["yfinance", "tushare", "akshare"]
    storage.save_history_data_hk_stock.assert_called_once()
```

- [ ] **Step 2: Run the new manager test**

Run: `uv run pytest test/download/test_download_manager.py::TestDownloadHkGgtHistoryFallback::test_download_hk_ggt_history_uses_yfinance_then_falls_back -q`

Expected: PASS after Task 3. Do not change manager retry, DAG scheduling, task boundaries, or persistence logic; correct only provider configuration if it fails.

- [ ] **Step 3: Run static checks on changed paths**

Run:

```bash
uv run ruff format --check download/dl/downloader_yfinance.py download/dl/downloader.py download/provider_order.py test/download/dl/test_downloader_yfinance.py test/download/dl/test_downloader.py test/download/test_provider_order.py test/download/test_download_manager.py
uv run ruff check download/dl/downloader_yfinance.py download/dl/downloader.py download/provider_order.py test/download/dl/test_downloader_yfinance.py test/download/dl/test_downloader.py test/download/test_provider_order.py test/download/test_download_manager.py
```

Expected: both commands exit 0. If formatting fails, apply Ruff formatting only to these files and re-run both checks.

- [ ] **Step 4: Run focused behavior tests**

Run:

```bash
uv run pytest test/download/dl/test_downloader_yfinance.py test/download/dl/test_downloader.py test/download/test_provider_order.py test/download/test_download_manager.py -q
```

Expected: PASS with no live yfinance, Tushare, or AkShare request.

- [ ] **Step 5: Inspect and commit only intended changes**

Run `git diff --check` and inspect the listed files. Do not stage unrelated existing worktree changes. Then commit:

```bash
git add test/download/test_download_manager.py
git commit -m "test: verify yfinance HK fallback order"
```
