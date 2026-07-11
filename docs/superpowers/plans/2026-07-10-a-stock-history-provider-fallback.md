# A Stock History Provider Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable fallback for A 股股票历史日线 downloads so post-close daily history downloads try the next configured provider when the current provider fails at the download/data-shape layer.

**Architecture:** Keep DAGs unchanged. Add a small provider-order parser, expose provider-specific A-share history downloader lookup through `Downloader`, and let `DownloadManager` plus multiprocessing batch workers reuse the same fallback helper before saving to storage.

**Tech Stack:** Python 3.11+, pandas, pytest, Ruff, existing `uv run` workflow, existing downloader modules for baostock/tushare/akshare.

## Global Constraints

- Scope is only A 股股票历史日线 fallback.
- Default provider order is `baostock,tushare,akshare`.
- Fallback triggers on provider exception, `None`, empty `DataFrame`, missing required fields, or fields that cannot be converted to the expected history schema.
- Storage save failure must not trigger fallback.
- Do not modify ETF, 港股通, daily_basic, 涨跌停, 停复牌, or other daily jobs.
- Do not change DAG schedule, dependencies, retries, task boundaries, SLA, `max_active_runs`, or partition strategy.
- Use `uv run` for Python commands in this repo.
- Do not commit unless the user explicitly asks for a commit.

---

## File Structure

- Create `download/provider_order.py`: owns stock-history provider order constants and parser. No downloader imports here.
- Modify `conf/global_settings.py`: parse `[download].stock_history_provider_order` into `DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER` with a default.
- Modify `config.ini`: document the default provider order next to `process_count`.
- Modify `download/dl/downloader_tushare.py`: add normalized A-share history downloader `download_history_data_stock_ts`.
- Modify `download/dl/downloader_akshare.py`: normalize existing A-share history downloader output and filter by requested date range.
- Modify `download/dl/downloader.py`: import all three A-share history provider functions and expose `dl_history_data_stock_by_provider`.
- Modify `download/download_manager.py`: add download-only fallback helper and use it from `download_stock_history`.
- Modify `download/mp_utils.py`: reuse the same fallback behavior for `SecurityType.STOCK` batch workers only.
- Add tests under `test/download/` and extend existing downloader tests.

---

### Task 1: Provider Order Configuration

**Files:**
- Create: `download/provider_order.py`
- Modify: `conf/global_settings.py:144-148`
- Modify: `config.ini`
- Test: `test/download/test_provider_order.py`
- Test: `test/conf/test_global_settings_download.py`

**Interfaces:**
- Produces: `download.provider_order.STOCK_HISTORY_PROVIDER_ENV: str`
- Produces: `download.provider_order.DEFAULT_STOCK_HISTORY_PROVIDER_ORDER: tuple[str, ...]`
- Produces: `download.provider_order.VALID_STOCK_HISTORY_PROVIDERS: frozenset[str]`
- Produces: `download.provider_order.parse_stock_history_provider_order(value: str | None = None) -> list[str]`
- Consumes: `os.getenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER")`

- [ ] **Step 1: Write failing tests for provider-order parsing**

Create `test/download/test_provider_order.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from download.provider_order import parse_stock_history_provider_order  # noqa: E402


def test_parse_stock_history_provider_order_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    assert parse_stock_history_provider_order() == ["baostock", "tushare", "akshare"]


def test_parse_stock_history_provider_order_strips_empty_items_and_deduplicates():
    assert parse_stock_history_provider_order(" tushare, baostock, tushare, , akshare ") == [
        "tushare",
        "baostock",
        "akshare",
    ]


def test_parse_stock_history_provider_order_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported stock history provider: yahoo"):
        parse_stock_history_provider_order("baostock,yahoo")


def test_parse_stock_history_provider_order_rejects_empty_provider_order():
    with pytest.raises(ValueError, match="stock history provider order is empty"):
        parse_stock_history_provider_order(" , , ")
```

Create `test/conf/test_global_settings_download.py`:

```python
import os
import sys
from configparser import ConfigParser

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from conf.global_settings import parse_download_config  # noqa: E402


def test_parse_download_config_sets_stock_history_provider_order(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)
    config = ConfigParser()
    config.read_dict({"download": {"process_count": "2", "stock_history_provider_order": "tushare,akshare"}})

    parse_download_config(config)

    assert os.environ["DOWNLOAD_PROCESS_COUNT"] == "2"
    assert os.environ["DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare,akshare"


def test_parse_download_config_uses_default_stock_history_provider_order(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)
    config = ConfigParser()
    config.read_dict({"download": {"process_count": "4"}})

    parse_download_config(config)

    assert os.environ["DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"] == "baostock,tushare,akshare"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_provider_order.py test/conf/test_global_settings_download.py -q
```

Expected: FAIL because `download.provider_order` does not exist and `parse_download_config` does not set `DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER`.

- [ ] **Step 3: Implement provider-order parser**

Create `download/provider_order.py`:

```python
import os

STOCK_HISTORY_PROVIDER_ENV = "DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"
DEFAULT_STOCK_HISTORY_PROVIDER_ORDER = ("baostock", "tushare", "akshare")
VALID_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)


def parse_stock_history_provider_order(value: str | None = None) -> list[str]:
    raw_value = value if value is not None else os.getenv(STOCK_HISTORY_PROVIDER_ENV)
    if raw_value is None:
        raw_value = ",".join(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)

    providers: list[str] = []
    seen: set[str] = set()
    for raw_provider in raw_value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in VALID_STOCK_HISTORY_PROVIDERS:
            raise ValueError(f"Unsupported stock history provider: {provider}")
        if provider in seen:
            continue
        seen.add(provider)
        providers.append(provider)

    if not providers:
        raise ValueError("stock history provider order is empty")
    return providers
```

- [ ] **Step 4: Wire config parsing**

Modify `conf/global_settings.py` import section and `parse_download_config`:

```python
from download.provider_order import DEFAULT_STOCK_HISTORY_PROVIDER_ORDER, STOCK_HISTORY_PROVIDER_ENV
```

Replace `parse_download_config` with:

```python
def parse_download_config(config: ConfigParser):
    try:
        os.environ["DOWNLOAD_PROCESS_COUNT"] = config["download"]["process_count"]
    except KeyError:
        os.environ["DOWNLOAD_PROCESS_COUNT"] = "4"

    try:
        os.environ[STOCK_HISTORY_PROVIDER_ENV] = config["download"]["stock_history_provider_order"]
    except KeyError:
        os.environ[STOCK_HISTORY_PROVIDER_ENV] = ",".join(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)
```

Modify `config.ini` `[download]` section to include:

```ini
stock_history_provider_order = baostock,tushare,akshare
```

- [ ] **Step 5: Run tests to verify Task 1 passes**

Run:

```bash
uv run pytest test/download/test_provider_order.py test/conf/test_global_settings_download.py -q
```

Expected: PASS.

---

### Task 2: Provider-Specific A-Share History Downloaders

**Files:**
- Modify: `download/dl/downloader_tushare.py`
- Modify: `download/dl/downloader_akshare.py`
- Modify: `download/dl/downloader.py`
- Test: `test/download/dl/test_downloader_tushare.py`
- Test: `test/download/dl/test_downloader_akshare.py`
- Test: `test/download/dl/test_downloader.py`

**Interfaces:**
- Consumes: `download_history_data_stock_bs(stock_id, start_date, end_date, period, adjust)`
- Produces: `download.dl.downloader_tushare.download_history_data_stock_ts(stock_id: str, start_date: str, end_date: str, period: PeriodType = PeriodType.DAILY, adjust: AdjustType = AdjustType.QFQ) -> pd.DataFrame`
- Produces: `Downloader.dl_history_data_stock_by_provider(provider: str, stock_id: str, start_date: str, end_date: str, period: PeriodType, adjust: AdjustType) -> pd.DataFrame`

- [ ] **Step 1: Write failing tests for TuShare A-share history normalization**

Append to `test/download/dl/test_downloader_tushare.py`:

```python
from unittest.mock import MagicMock

import pandas as pd

from common.const import COL_AMOUNT, COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_STOCK_ID, COL_VOLUME, AdjustType, PeriodType
from download.dl import downloader_tushare as dt


def test_download_history_data_stock_ts_normalizes_pro_bar(monkeypatch):
    pro_client = MagicMock(name="pro_client")
    monkeypatch.setattr(dt, "_create_pro_client", lambda: pro_client)

    def fake_pro_bar(**kwargs):
        assert kwargs["api"] is pro_client
        assert kwargs["ts_code"] == "000001.SZ"
        assert kwargs["start_date"] == "20240101"
        assert kwargs["end_date"] == "20240102"
        assert kwargs["adj"] == "qfq"
        assert kwargs["freq"] == "D"
        return pd.DataFrame(
            {
                "trade_date": ["20240102", "20240101"],
                "ts_code": ["000001.SZ", "000001.SZ"],
                "open": [10.0, 9.0],
                "high": [11.0, 10.0],
                "low": [9.5, 8.8],
                "close": [10.5, 9.5],
                "vol": [100.0, 90.0],
                "amount": [1000.0, 900.0],
            }
        )

    monkeypatch.setattr(dt.ts, "pro_bar", fake_pro_bar)

    df = dt.download_history_data_stock_ts("000001", "2024-01-01", "2024-01-02", PeriodType.DAILY, AdjustType.QFQ)

    assert df[COL_DATE].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert df[COL_STOCK_ID].tolist() == ["000001", "000001"]
    assert df[[COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME, COL_AMOUNT]].notna().all().all()


def test_download_history_data_stock_ts_uses_none_adj_for_bfq(monkeypatch):
    monkeypatch.setattr(dt, "_create_pro_client", lambda: MagicMock(name="pro_client"))
    captured = {}

    def fake_pro_bar(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            {
                "trade_date": ["20240101"],
                "ts_code": ["600000.SH"],
                "open": [1],
                "high": [1],
                "low": [1],
                "close": [1],
                "vol": [1],
                "amount": [1],
            }
        )

    monkeypatch.setattr(dt.ts, "pro_bar", fake_pro_bar)

    dt.download_history_data_stock_ts("600000", "20240101", "20240101", PeriodType.DAILY, AdjustType.BFQ)

    assert captured["adj"] is None
```

- [ ] **Step 2: Write failing tests for AkShare date filtering and stock id normalization**

Append to `test/download/dl/test_downloader_akshare.py`:

```python
import pandas as pd

from common.const import COL_DATE, COL_STOCK_ID, AdjustType, PeriodType
from download.dl import downloader_akshare as da


def test_download_history_data_stock_ak_filters_dates_and_sets_stock_id(monkeypatch):
    def fake_stock_zh_a_hist(**kwargs):
        assert kwargs["symbol"] == "000001"
        return pd.DataFrame(
            {
                COL_DATE: ["2024-01-01", "2024-01-02", "2024-01-03"],
                "开盘": [1.0, 2.0, 3.0],
                "最高": [1.0, 2.0, 3.0],
                "最低": [1.0, 2.0, 3.0],
                "收盘": [1.0, 2.0, 3.0],
                "成交量": [10, 20, 30],
                "成交额": [100, 200, 300],
            }
        )

    monkeypatch.setattr(da.ak, "stock_zh_a_hist", fake_stock_zh_a_hist)

    df = da.download_history_data_stock_ak("000001", "20240102", "20240103", PeriodType.DAILY, AdjustType.QFQ)

    assert df[COL_DATE].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert df[COL_STOCK_ID].tolist() == ["000001", "000001"]
```

- [ ] **Step 3: Write failing tests for Downloader provider lookup**

Append to `test/download/dl/test_downloader.py`:

```python
import pytest

from common.const import AdjustType, PeriodType
from download.dl import downloader as downloader_module
from download.dl.downloader import Downloader


def test_dl_history_data_stock_by_provider_dispatches_to_named_provider(monkeypatch):
    calls = []

    def fake_tushare(stock_id, start_date, end_date, period, adjust):
        calls.append((stock_id, start_date, end_date, period, adjust))
        return "ok"

    monkeypatch.setitem(downloader_module.STOCK_HISTORY_PROVIDER_DOWNLOADERS, "tushare", fake_tushare)

    result = Downloader().dl_history_data_stock_by_provider(
        "tushare", "000001", "20240101", "20240102", PeriodType.DAILY, AdjustType.QFQ
    )

    assert result == "ok"
    assert calls == [("000001", "20240101", "20240102", PeriodType.DAILY, AdjustType.QFQ)]


def test_dl_history_data_stock_by_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported stock history provider: yahoo"):
        Downloader().dl_history_data_stock_by_provider(
            "yahoo", "000001", "20240101", "20240102", PeriodType.DAILY, AdjustType.QFQ
        )
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader_akshare.py test/download/dl/test_downloader.py -q
```

Expected: FAIL because `download_history_data_stock_ts`, AkShare normalization, and `dl_history_data_stock_by_provider` are not implemented.

- [ ] **Step 5: Implement TuShare A-share history downloader**

Modify `download/dl/downloader_tushare.py` by adding helper functions near `_to_hk_ts_code`:

```python
def _to_a_stock_ts_code(stock_id: str) -> str:
    if not re.fullmatch(r"\d{6}", stock_id):
        raise ValueError("Stock ID must be 6 digits.")
    suffix = "SH" if stock_id.startswith("6") else "SZ"
    return f"{stock_id}.{suffix}"


def _pro_bar_freq(period: PeriodType) -> str:
    freq_map = {
        PeriodType.DAILY: "D",
        PeriodType.WEEKLY: "W",
        PeriodType.MONTHLY: "M",
    }
    return freq_map[period]


def _normalize_a_stock_history_ts(df: pd.DataFrame, stock_id: str) -> pd.DataFrame:
    column_mapping = {
        "trade_date": COL_DATE,
        "ts_code": COL_STOCK_ID,
        "open": COL_OPEN,
        "high": COL_HIGH,
        "low": COL_LOW,
        "close": COL_CLOSE,
        "vol": COL_VOLUME,
        "amount": COL_AMOUNT,
        "pct_chg": COL_CHANGE_RATE,
        "change": COL_CHANGE,
    }
    normalized = df.rename(columns=column_mapping).copy()
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], format="%Y%m%d")
    normalized[COL_STOCK_ID] = stock_id
    numeric_columns = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME, COL_AMOUNT, COL_CHANGE_RATE, COL_CHANGE]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)
    return normalized.sort_values(COL_DATE).reset_index(drop=True)
```

Add the public function after `download_daily_basic_a_stock_ts`:

```python
@retrying.retry(
    wait_exponential_multiplier=2000,
    wait_exponential_max=60000,
    stop_max_attempt_number=3,
    retry_on_exception=retry_on_non_validation_errors,
)
def download_history_data_stock_ts(
    stock_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType = PeriodType.DAILY,
    adjust: AdjustType = AdjustType.QFQ,
) -> pd.DataFrame:
    client = _create_pro_client()
    df = ts.pro_bar(
        api=client,
        ts_code=_to_a_stock_ts_code(stock_id),
        start_date=convert_date(start_date),
        end_date=convert_date(end_date),
        freq=_pro_bar_freq(period),
        adj=adjust.value or None,
    )
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected DataFrame, got {type(df)}")
    if df.empty:
        return df
    return _normalize_a_stock_history_ts(df, stock_id)
```

- [ ] **Step 6: Normalize AkShare A-share history downloader**

Modify `download/dl/downloader_akshare.py` inside `download_history_data_stock_ak` after the `assert not df.empty` line:

```python
    df[COL_DATE] = pd.to_datetime(df[COL_DATE])
    mask = (df[COL_DATE] >= pd.to_datetime(start_date)) & (df[COL_DATE] <= pd.to_datetime(end_date))
    df = df.loc[mask].copy()
    df[COL_STOCK_ID] = stock_id

    numeric_columns = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME, "成交额", COL_TURNOVER_RATE, COL_CHANGE_RATE]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    return df.reset_index(drop=True)
```

Keep the existing `return df` only as the last line after this block; remove the old earlier return if needed.

- [ ] **Step 7: Add Downloader provider dispatch**

Modify `download/dl/downloader.py` imports:

```python
from .downloader_akshare import (
    download_general_info_etf_ak,
    download_general_info_hk_ggt_stock_ak,
    download_general_info_stock_ak,
    download_history_data_stock_ak,
    download_history_data_us_index_ak,
)
from .downloader_tushare import (
    download_a_stock_basic,
    download_daily_basic_a_stock_ts,
    download_etf_basic,
    download_etf_daily,
    download_history_data_etf_ts,
    download_history_data_stock_hk_ts,
    download_history_data_stock_ts,
    download_stk_holdernumber,
    download_stk_limit,
    download_suspend_d,
    download_top10_floatholders,
)
```

Add module-level mapping before `class Downloader`:

```python
STOCK_HISTORY_PROVIDER_DOWNLOADERS = {
    "baostock": download_history_data_stock_bs,
    "tushare": download_history_data_stock_ts,
    "akshare": download_history_data_stock_ak,
}
```

Add method inside `Downloader`:

```python
    def dl_history_data_stock_by_provider(
        self,
        provider: str,
        stock_id: str,
        start_date: str,
        end_date: str,
        period: PeriodType,
        adjust: AdjustType,
    ):
        try:
            downloader_func = STOCK_HISTORY_PROVIDER_DOWNLOADERS[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported stock history provider: {provider}") from exc
        return downloader_func(stock_id, start_date, end_date, period, adjust)
```

Also import `AdjustType` and `PeriodType` at the top of `download/dl/downloader.py`:

```python
from common.const import AdjustType, PeriodType
```

- [ ] **Step 8: Run tests to verify Task 2 passes**

Run:

```bash
uv run pytest test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader_akshare.py test/download/dl/test_downloader.py -q
```

Expected: PASS.

---

### Task 3: DownloadManager Fallback Before Save

**Files:**
- Modify: `download/download_manager.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Consumes: `parse_stock_history_provider_order(value: str | None = None) -> list[str]`
- Consumes: `Downloader.dl_history_data_stock_by_provider(provider, stock_id, start_date, end_date, period, adjust)`
- Produces: `REQUIRED_STOCK_HISTORY_COLUMNS: tuple[str, ...]`
- Produces: `_validate_stock_history_data(df: Any) -> pd.DataFrame`
- Produces: `DownloadManager._download_stock_history_with_fallback(stock_id: str, start_date: str, end_date: str, period: PeriodType, adjust: AdjustType) -> pd.DataFrame | None`

- [ ] **Step 1: Write failing tests for fallback behavior**

Append to `test/download/test_download_manager.py`:

```python
from common.const import COL_AMOUNT, COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_STOCK_ID, COL_VOLUME, SecurityType


def _stock_history_df(stock_id="000001"):
    return pd.DataFrame(
        {
            COL_DATE: [pd.Timestamp("2024-01-01")],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [10.0],
            COL_HIGH: [11.0],
            COL_LOW: [9.0],
            COL_CLOSE: [10.5],
            COL_VOLUME: [1000.0],
            COL_AMOUNT: [10000.0],
        }
    )


class TestDownloadStockHistoryProviderFallback:
    def test_download_stock_history_falls_back_after_provider_exception(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        fallback_df = _stock_history_df()

        def fake_provider(provider, stock_id, start_date, end_date, period, adjust):
            if provider == "baostock":
                raise RuntimeError("baostock unavailable")
            return fallback_df

        downloader.dl_history_data_stock_by_provider.side_effect = fake_provider
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        assert [call.args[0] for call in downloader.dl_history_data_stock_by_provider.call_args_list] == [
            "baostock",
            "tushare",
        ]
        storage.save_history_data_stock.assert_called_once_with(fallback_df, PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_falls_back_after_empty_dataframe(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.side_effect = [pd.DataFrame(), fallback_df]
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        storage.save_history_data_stock.assert_called_once_with(fallback_df, PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_falls_back_after_missing_required_field(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        invalid_df = _stock_history_df().drop(columns=[COL_CLOSE])
        fallback_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.side_effect = [invalid_df, fallback_df]
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        storage.save_history_data_stock.assert_called_once_with(fallback_df, PeriodType.DAILY, AdjustType.QFQ)

    def test_download_stock_history_short_circuits_after_first_success(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare", "akshare"])
        storage.get_last_record.return_value = None
        first_df = _stock_history_df()
        downloader.dl_history_data_stock_by_provider.return_value = first_df
        storage.save_history_data_stock.return_value = True

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_called_once()

    def test_download_stock_history_save_failure_does_not_try_next_provider(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        downloader.dl_history_data_stock_by_provider.return_value = _stock_history_df()
        storage.save_history_data_stock.return_value = False

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is False
        downloader.dl_history_data_stock_by_provider.assert_called_once()

    def test_download_stock_history_all_providers_fail_returns_false(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = None
        downloader.dl_history_data_stock_by_provider.side_effect = RuntimeError("provider failed")

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is False
        storage.save_history_data_stock.assert_not_called()

    def test_download_stock_history_up_to_date_does_not_download(self, monkeypatch):
        dm = importlib.import_module("download.download_manager")
        manager, storage, downloader = _make_manager(monkeypatch)
        monkeypatch.setattr(dm, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])
        storage.get_last_record.return_value = {COL_DATE: "2024-01-03"}

        result = manager.download_stock_history("000001", PeriodType.DAILY, "20240101", "20240102", AdjustType.QFQ)

        assert result is True
        downloader.dl_history_data_stock_by_provider.assert_not_called()
        storage.save_history_data_stock.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback -q
```

Expected: FAIL because `download_stock_history` still calls `dl_history_data_stock` directly and no fallback helper exists.

- [ ] **Step 3: Add required imports and validation helper**

Modify `download/download_manager.py` imports to include constants and parser:

```python
from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
    SecurityType,
)
from download.provider_order import parse_stock_history_provider_order
```

Add near the existing top-level helper functions:

```python
REQUIRED_STOCK_HISTORY_COLUMNS = (
    COL_DATE,
    COL_STOCK_ID,
    COL_OPEN,
    COL_HIGH,
    COL_LOW,
    COL_CLOSE,
    COL_VOLUME,
    COL_AMOUNT,
)


def _validate_stock_history_data(df: Any) -> pd.DataFrame:
    if df is None:
        raise ValueError("provider returned None")
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"provider returned {type(df)}, expected DataFrame")
    if df.empty:
        raise ValueError("provider returned empty DataFrame")

    missing_columns = [column for column in REQUIRED_STOCK_HISTORY_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"provider result missing required columns: {missing_columns}")

    validated = df.copy()
    validated[COL_DATE] = pd.to_datetime(validated[COL_DATE])
    numeric_columns = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME, COL_AMOUNT]
    for column in numeric_columns:
        validated[column] = pd.to_numeric(validated[column], errors="raise")
    return validated
```

- [ ] **Step 4: Add DownloadManager fallback helper**

Add this method inside `DownloadManager` before `download_stock_history`:

```python
    def _download_stock_history_with_fallback(
        self,
        stock_id: str,
        start_date: str,
        end_date: str,
        period: PeriodType,
        adjust: AdjustType,
    ) -> pd.DataFrame | None:
        provider_errors: dict[str, str] = {}
        for provider in parse_stock_history_provider_order():
            try:
                logging.info(
                    "Downloading stock history via %s: stock_id=%s, start_date=%s, end_date=%s, period=%s, adjust=%s",
                    provider,
                    stock_id,
                    start_date,
                    end_date,
                    period.value,
                    adjust.value,
                )
                df = self.downloader.dl_history_data_stock_by_provider(
                    provider,
                    stock_id,
                    start_date,
                    end_date,
                    period,
                    adjust,
                )
                validated = _validate_stock_history_data(df)
                logging.info(
                    "Downloaded stock history via %s: stock_id=%s, rows=%d",
                    provider,
                    stock_id,
                    len(validated),
                )
                return validated
            except Exception as exc:  # noqa: BLE001
                provider_errors[provider] = str(exc)
                logging.warning(
                    "Stock history provider failed: provider=%s, stock_id=%s, start_date=%s, end_date=%s, period=%s, adjust=%s, error=%s",
                    provider,
                    stock_id,
                    start_date,
                    end_date,
                    period.value,
                    adjust.value,
                    exc,
                )

        logging.error("All stock history providers failed for %s: %s", stock_id, provider_errors)
        return None
```

- [ ] **Step 5: Route `download_stock_history` through fallback**

Replace `download_stock_history` body with explicit incremental logic so storage-save failures are outside fallback:

```python
    def download_stock_history(
        self,
        stock_id: str,
        period: PeriodType,
        start_date: str,
        end_date: str,
        adjust: AdjustType = AdjustType.QFQ,
    ) -> bool:
        table_name = get_table_name(SecurityType.STOCK, period, adjust)

        try:
            last_record = get_storage().get_last_record(table_name, stock_id)

            if last_record is not None:
                latest_date = pd.Timestamp(last_record[COL_DATE])
                actual_start_ts = latest_date + pd.Timedelta(days=1)
                actual_start_date = actual_start_ts.strftime("%Y%m%d")

                if actual_start_ts > pd.to_datetime(end_date):
                    logging.info(f"Data for {stock_id} is already up to date")
                    return True
            else:
                actual_start_date = start_date

            df = self._download_stock_history_with_fallback(stock_id, actual_start_date, end_date, period, adjust)
            if df is None:
                return False

            return get_storage().save_history_data_stock(df, period, adjust)

        except Exception as e:  # noqa: BLE001
            logging.error(f"Error processing history for {stock_id}: {e}")
            return False
```

- [ ] **Step 6: Run tests to verify Task 3 passes**

Run:

```bash
uv run pytest test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback -q
```

Expected: PASS.

Run existing nearby tests to confirm ETF behavior was not changed:

```bash
uv run pytest test/download/test_download_manager.py::TestDownloadManager -q
```

Expected: PASS.

---

### Task 4: Multiprocessing Batch Fallback

**Files:**
- Modify: `download/mp_utils.py`
- Test: `test/download/test_mp_utils.py`

**Interfaces:**
- Consumes: `parse_stock_history_provider_order() -> list[str]`
- Consumes: `Downloader.dl_history_data_stock_by_provider(provider, security_id, actual_start_date, end_date, period, adjust)`
- Produces: `_download_stock_history_with_fallback(downloader: Downloader, security_id: str, start_date: str, end_date: str, period: PeriodType, adjust: AdjustType) -> pd.DataFrame | None`

- [ ] **Step 1: Write failing multiprocessing worker tests**

Create `test/download/test_mp_utils.py` if it does not exist, or append to it if it exists:

```python
import os
import sys
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from common.const import COL_AMOUNT, COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_STOCK_ID, COL_VOLUME, AdjustType, PeriodType, SecurityType  # noqa: E402
from download import mp_utils  # noqa: E402


def _stock_history_df(stock_id="000001"):
    return pd.DataFrame(
        {
            COL_DATE: [pd.Timestamp("2024-01-01")],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [10.0],
            COL_HIGH: [11.0],
            COL_LOW: [9.0],
            COL_CLOSE: [10.5],
            COL_VOLUME: [1000.0],
            COL_AMOUNT: [10000.0],
        }
    )


def test_history_batch_worker_falls_back_for_stock_download(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_stock.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(mp_utils, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])

    downloader = MagicMock()
    fallback_df = _stock_history_df()

    def fake_provider(provider, security_id, start_date, end_date, period, adjust):
        if provider == "baostock":
            raise RuntimeError("baostock unavailable")
        return fallback_df

    downloader.dl_history_data_stock_by_provider.side_effect = fake_provider
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000001"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 1
    assert result.failed == 0
    assert [call.args[0] for call in downloader.dl_history_data_stock_by_provider.call_args_list] == [
        "baostock",
        "tushare",
    ]
    storage.save_history_data_stock.assert_called_once_with(fallback_df, PeriodType.DAILY, AdjustType.QFQ)


def test_history_batch_worker_save_failure_does_not_try_next_stock_provider(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_stock.return_value = False
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)
    monkeypatch.setattr(mp_utils, "parse_stock_history_provider_order", lambda: ["baostock", "tushare"])

    downloader = MagicMock()
    downloader.dl_history_data_stock_by_provider.return_value = _stock_history_df()
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.STOCK,
        ["000001"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 0
    assert result.failed == 1
    downloader.dl_history_data_stock_by_provider.assert_called_once()


def test_history_batch_worker_keeps_etf_single_provider_path(monkeypatch):
    storage = MagicMock()
    storage.get_last_record.return_value = None
    storage.save_history_data_etf.return_value = True
    monkeypatch.setattr(mp_utils, "get_storage", lambda: storage)

    downloader = MagicMock()
    downloader.dl_history_data_etf.return_value = pd.DataFrame({COL_DATE: [pd.Timestamp("2024-01-01")]})
    monkeypatch.setattr(mp_utils, "Downloader", lambda: downloader)

    result = mp_utils._history_batch_worker(
        SecurityType.ETF,
        ["510300"],
        PeriodType.DAILY.value,
        AdjustType.QFQ.value,
        "20240101",
        "20240102",
    )

    assert result.success == 1
    assert result.failed == 0
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    downloader.dl_history_data_etf.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_mp_utils.py -q
```

Expected: FAIL because multiprocessing workers still call `dl_history_data_stock` directly and do not import the provider-order parser.

- [ ] **Step 3: Add shared validation and fallback in mp_utils**

Modify `download/mp_utils.py` imports:

```python
from download.download_manager import _validate_stock_history_data
from download.provider_order import parse_stock_history_provider_order
```

Add this helper above `_history_batch_worker`:

```python
def _download_stock_history_with_fallback(
    downloader: Downloader,
    security_id: str,
    start_date: str,
    end_date: str,
    period: PeriodType,
    adjust: AdjustType,
) -> pd.DataFrame | None:
    provider_errors: Dict[str, str] = {}
    for provider in parse_stock_history_provider_order():
        try:
            df = downloader.dl_history_data_stock_by_provider(
                provider,
                security_id,
                start_date,
                end_date,
                period,
                adjust,
            )
            validated = _validate_stock_history_data(df)
            logging.info("[A股] provider=%s security_id=%s rows=%d", provider, security_id, len(validated))
            return validated
        except Exception as exc:  # noqa: BLE001
            provider_errors[provider] = str(exc)
            logging.warning("[A股] provider=%s security_id=%s failed: %s", provider, security_id, exc)

    logging.error("[A股] all providers failed for %s: %s", security_id, provider_errors)
    return None
```

- [ ] **Step 4: Route only stock workers through fallback**

In `_history_batch_worker`, keep the current `saver_attr` setup, but replace the single `downloader_func` call section:

```python
            if security_type == SecurityType.STOCK:
                df = _download_stock_history_with_fallback(
                    downloader,
                    security_id,
                    actual_start_date,
                    end_date,
                    period,
                    adjust,
                )
            else:
                df = downloader_func(security_id, actual_start_date, end_date, period, adjust)

            if df is None or df.empty:
                if security_type == SecurityType.STOCK:
                    failed += 1
                    failed_ids.append(security_id)
                    errors[security_id] = "all stock history providers failed"
                else:
                    success += 1
                continue
```

Keep the existing save block unchanged after this replacement:

```python
            ok = bool(save_func(df, period, adjust))
            if ok:
                success += 1
            else:
                failed += 1
                failed_ids.append(security_id)
                errors[security_id] = "save returned False"
```

- [ ] **Step 5: Run tests to verify Task 4 passes**

Run:

```bash
uv run pytest test/download/test_mp_utils.py -q
```

Expected: PASS.

---

### Task 5: Focused Regression and Formatting

**Files:**
- Modify only if checks reveal issues: files touched by Tasks 1-4.

**Interfaces:**
- Consumes all interfaces produced by Tasks 1-4.
- Produces verified A 股历史日线 provider fallback behavior across single-stock and batch download paths.

- [ ] **Step 1: Run all focused fallback tests**

Run:

```bash
uv run pytest \
  test/download/test_provider_order.py \
  test/conf/test_global_settings_download.py \
  test/download/dl/test_downloader.py \
  test/download/dl/test_downloader_tushare.py \
  test/download/dl/test_downloader_akshare.py \
  test/download/test_download_manager.py::TestDownloadStockHistoryProviderFallback \
  test/download/test_mp_utils.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run existing related regression tests**

Run:

```bash
uv run pytest \
  test/download/test_download_manager.py::TestDownloadManager \
  test/dags/test_common_dags.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Run Ruff format on touched Python files**

Run:

```bash
uv run ruff format \
  conf/global_settings.py \
  download/provider_order.py \
  download/dl/downloader.py \
  download/dl/downloader_tushare.py \
  download/dl/downloader_akshare.py \
  download/download_manager.py \
  download/mp_utils.py \
  test/download/test_provider_order.py \
  test/conf/test_global_settings_download.py \
  test/download/dl/test_downloader.py \
  test/download/dl/test_downloader_tushare.py \
  test/download/dl/test_downloader_akshare.py \
  test/download/test_download_manager.py \
  test/download/test_mp_utils.py
```

Expected: command exits 0.

- [ ] **Step 4: Run Ruff lint on touched Python files**

Run:

```bash
uv run ruff check \
  conf/global_settings.py \
  download/provider_order.py \
  download/dl/downloader.py \
  download/dl/downloader_tushare.py \
  download/dl/downloader_akshare.py \
  download/download_manager.py \
  download/mp_utils.py \
  test/download/test_provider_order.py \
  test/conf/test_global_settings_download.py \
  test/download/dl/test_downloader.py \
  test/download/dl/test_downloader_tushare.py \
  test/download/dl/test_downloader_akshare.py \
  test/download/test_download_manager.py \
  test/download/test_mp_utils.py
```

Expected: PASS.

- [ ] **Step 5: Inspect git diff for scope**

Run:

```bash
git diff -- conf/global_settings.py config.ini download/provider_order.py download/dl/downloader.py download/dl/downloader_tushare.py download/dl/downloader_akshare.py download/download_manager.py download/mp_utils.py test/download/test_provider_order.py test/conf/test_global_settings_download.py test/download/dl/test_downloader.py test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py test/download/test_mp_utils.py docs/superpowers/specs/2026-07-10-a-stock-history-provider-fallback-design.md docs/superpowers/plans/2026-07-10-a-stock-history-provider-fallback.md
```

Expected: diff contains only A 股历史日线 provider fallback changes, tests, config documentation, spec, and this plan.

---

## Self-Review Notes

- Spec coverage: configuration, fallback trigger conditions, storage-save boundary, single-stock path, batch path, logging/error behavior, DAG non-change constraint, and tests are covered by Tasks 1-5.
- Placeholder scan: no placeholder markers or unspecified “add tests” steps remain.
- Type consistency: provider-order parser returns `list[str]`; downloader provider dispatch accepts provider name plus existing downloader arguments; manager and batch fallback helpers return `pd.DataFrame | None` and save only after successful validation.
