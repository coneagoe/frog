# A Stock History Trading Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip A 股股票历史日线 provider downloads when the incremental date range contains no A-share trading days, and shrink download ranges to actual trading days when they exist.

**Architecture:** Add one shared trading-window helper in `stock/market.py` using the existing `pandas_market_calendars` / `XSHG` convention. Use it in the single-stock `DownloadManager.download_stock_history()` path and the stock branch of `download/mp_utils.py::_history_batch_worker()` before provider fallback.

**Tech Stack:** Python 3.11+, pandas, pandas-market-calendars, pytest, Ruff, existing `uv run` workflow.

## Global Constraints

- Only cover A 股股票历史日线下载.
- Do not modify ETF、港股通、daily_basic、涨跌停、停复牌等其它下载任务.
- Do not modify DAG schedule、task boundary、依赖、重试或 SLA.
- Do not use provider APIs as the trading-calendar source.
- Keep existing provider fallback order and data-format normalization unchanged.
- No-trading-day windows return success and do not call any provider.
- Trading-day windows are returned as `YYYYMMDD` strings.
- Use `uv run` for Python commands in this repo.

---

## File Structure

- Modify `stock/market.py`: add `get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None`.
- Modify `download/download_manager.py`: call the helper before `_download_stock_history_with_fallback()`.
- Modify `download/mp_utils.py`: call the helper only for `SecurityType.STOCK` before batch fallback.
- Modify tests:
  - `test/stock/test_market.py`
  - `test/download/test_download_manager.py`
  - `test/download/test_mp_utils.py`

---

### Task 1: Trading Window Helper

**Files:**
- Modify: `stock/market.py`
- Test: `test/stock/test_market.py`

**Interfaces:**
- Produces: `get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None`

- [ ] **Step 1: Write failing tests**

Append these tests to `test/stock/test_market.py`:

```python
from stock.market import get_a_stock_trading_window


def test_get_a_stock_trading_window_returns_none_for_weekend_only_range():
    assert get_a_stock_trading_window("20260711", "2026-07-12") is None


def test_get_a_stock_trading_window_shrinks_range_to_trading_days():
    assert get_a_stock_trading_window("20260711", "2026-07-14") == ("20260713", "20260714")


def test_get_a_stock_trading_window_returns_none_when_start_after_end():
    assert get_a_stock_trading_window("20260714", "20260713") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/stock/test_market.py -q
```

Expected: FAIL because `get_a_stock_trading_window` does not exist.

- [ ] **Step 3: Implement the helper**

In `stock/market.py`, add this function near the existing A-share market helpers:

```python
def get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None:
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()

    if start_ts > end_ts:
        return None

    market = mcal.get_calendar("XSHG")
    schedule = market.schedule(start_date=start_ts, end_date=end_ts)
    if schedule.empty:
        return None

    trading_days = schedule.index
    return (
        pd.Timestamp(trading_days[0]).strftime("%Y%m%d"),
        pd.Timestamp(trading_days[-1]).strftime("%Y%m%d"),
    )
```

- [ ] **Step 4: Run tests to verify Task 1 passes**

Run:

```bash
uv run pytest test/stock/test_market.py -q
```

Expected: PASS.

---

### Task 2: DownloadManager Single-Stock Window Preprocessing

**Files:**
- Modify: `download/download_manager.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Consumes: `get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None`
- Preserves: `DownloadManager.download_stock_history(...) -> bool`

- [ ] **Step 1: Write failing tests**

Append these methods to `TestDownloadStockHistoryProviderFallback` in `test/download/test_download_manager.py`:

```python
    def test_download_stock_history_skips_when_no_trading_days_in_incremental_window(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda start_date, end_date: None)

        result = manager.download_stock_history("000026", PeriodType.DAILY, "20200101", "2026-07-12", AdjustType.HFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_not_called()
        storage.save_history_data_stock.assert_not_called()

    def test_download_stock_history_uses_trading_day_window_for_provider_calls(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock"])
        monkeypatch.setattr(dm, "get_a_stock_trading_window", lambda start_date, end_date: ("20260713", "20260714"))
        storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.return_value = fallback_df
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000026", PeriodType.DAILY, "20200101", "2026-07-14", AdjustType.HFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_called_once_with(
            "baostock", "000026", "20260713", "20260714", PeriodType.DAILY, AdjustType.HFQ
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback -q
```

Expected: FAIL because `download_stock_history` does not call `get_a_stock_trading_window` yet.

- [ ] **Step 3: Implement single-stock window preprocessing**

In `download/download_manager.py`, import:

```python
from stock.market import get_a_stock_trading_window
```

Inside `DownloadManager.download_stock_history()`, after `actual_start_date` is computed and before `_download_stock_history_with_fallback(...)`, add:

```python
            trading_window = get_a_stock_trading_window(actual_start_date, end_date)
            if trading_window is None:
                logging.info(
                    "No A-share trading days in range, skip stock history download: stock_id=%s, start_date=%s, end_date=%s",
                    stock_id,
                    actual_start_date,
                    end_date,
                )
                return True

            window_start_date, window_end_date = trading_window
            df = self._download_stock_history_with_fallback(
                stock_id,
                window_start_date,
                window_end_date,
                period,
                adjust,
            )
```

Replace the existing direct `_download_stock_history_with_fallback(stock_id, actual_start_date, end_date, period, adjust)` call with the new windowed call.

- [ ] **Step 4: Run tests to verify Task 2 passes**

Run:

```bash
uv run pytest test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback -q
```

Expected: PASS.

---

### Task 3: Multiprocessing Stock Batch Window Preprocessing

**Files:**
- Modify: `download/mp_utils.py`
- Test: `test/download/test_mp_utils.py`

**Interfaces:**
- Consumes: `get_a_stock_trading_window(start_date: str, end_date: str) -> tuple[str, str] | None`
- Preserves: ETF and HK batch paths without trading-window calls.

- [ ] **Step 1: Write failing tests**

Append to `test/download/test_mp_utils.py`:

```python
def test_history_batch_worker_skips_stock_provider_when_no_trading_days(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", lambda start_date, end_date: None)

    downloader = MagicMock()
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000026"],
        PeriodType.DAILY.value,
        AdjustType.HFQ.value,
        "20200101",
        "2026-07-12",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()


def test_history_batch_worker_uses_trading_day_window_for_stock_provider(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = {COL_DATE: "2026-07-10"}
    storage.save_history_data_stock.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(mp_utils, "parse_stock_history_provider_order", lambda: ["baostock"])
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", lambda start_date, end_date: ("20260713", "20260714"))

    downloader = MagicMock()
    fallback_df = _stock_history_df("000026")
    downloader.dl_history_data_stock_by_provider.return_value = fallback_df
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000026"],
        PeriodType.DAILY.value,
        AdjustType.HFQ.value,
        "20200101",
        "2026-07-14",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_called_once_with(
        "baostock", "000026", "20260713", "20260714", PeriodType.DAILY, AdjustType.HFQ
    )


def test_history_batch_worker_does_not_use_a_stock_window_for_etf(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_etf.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)

    get_window = MagicMock(return_value=None)
    monkeypatch.setattr(mp_utils, "get_a_stock_trading_window", get_window)

    downloader = MagicMock()
    downloader.dl_history_data_etf.return_value = pd.DataFrame({COL_DATE: [pd.Timestamp("2026-07-13")]})
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.ETF,
        ["510300"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20260711",
        "2026-07-14",
    )

    assert result.success == 1
    assert result.failed == 0
    get_window.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_mp_utils.py -q
```

Expected: FAIL because `mp_utils` does not expose/use `get_a_stock_trading_window` yet.

- [ ] **Step 3: Implement batch window preprocessing**

In `download/mp_utils.py`, import:

```python
from stock.market import get_a_stock_trading_window
```

In `_history_batch_worker()`, immediately before the stock fallback call, replace the stock branch with:

```python
            if security_type == SecurityType.STOCK:
                trading_window = get_a_stock_trading_window(actual_start_date, end_date)
                if trading_window is None:
                    logging.info(
                        "[A股] No trading days in range, skip: security_id=%s, start_date=%s, end_date=%s",
                        security_id,
                        actual_start_date,
                        end_date,
                    )
                    success += 1
                    continue

                window_start_date, window_end_date = trading_window
                df = _download_stock_history_with_fallback(
                    downloader,
                    security_id,
                    window_start_date,
                    window_end_date,
                    period,
                    adjust,
                )
            else:
                df = downloader_func(security_id, actual_start_date, end_date, period, adjust)
```

Keep the existing post-download `if df is None or df.empty` block and save block below this unchanged.

- [ ] **Step 4: Run tests to verify Task 3 passes**

Run:

```bash
uv run pytest test/download/test_mp_utils.py -q
```

Expected: PASS.

---

### Task 4: Focused Verification and Commit

**Files:**
- Modify only if checks reveal issues: files touched in Tasks 1-3.

**Interfaces:**
- Consumes all interfaces from Tasks 1-3.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run pytest \
  test/stock/test_market.py \
  test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback \
  test/download/test_mp_utils.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run existing adjacent regression tests**

Run:

```bash
uv run pytest \
  test/download/test_download_manager.py::TestDownloadManager \
  test/dags/test_common_dags.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run Ruff on touched files**

Run:

```bash
uv run ruff format stock/market.py download/download_manager.py download/mp_utils.py test/stock/test_market.py test/download/test_download_manager.py test/download/test_mp_utils.py
uv run ruff check stock/market.py download/download_manager.py download/mp_utils.py test/stock/test_market.py test/download/test_download_manager.py test/download/test_mp_utils.py
```

Expected: both commands exit 0.

- [ ] **Step 4: Commit**

Run:

```bash
git add stock/market.py download/download_manager.py download/mp_utils.py test/stock/test_market.py test/download/test_download_manager.py test/download/test_mp_utils.py docs/superpowers/specs/2026-07-12-a-stock-history-trading-window-design.md docs/superpowers/plans/2026-07-12-a-stock-history-trading-window.md
git commit -m "fix: skip A-share history downloads without trading days"
```

Expected: commit succeeds.

---

## Self-Review Notes

- Spec coverage: helper, single-stock path, batch path, no-trading-day success behavior, window shrinking, non-A-share paths unchanged, and verification are covered.
- Placeholder scan: no placeholder markers or unspecified “write tests” steps remain.
- Type consistency: `get_a_stock_trading_window` returns `tuple[str, str] | None` and both consumers use the same contract.
