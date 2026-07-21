# HK GGT Unadjusted Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `download_hk_ggt_history_daily` download unadjusted HK GGT daily history from 2026-01-01 with a configurable `tushare,akshare` provider fallback chain, while preserving existing HFQ data paths.

**Architecture:** Add HK-specific provider-order parsing and provider dispatch in the download layer, mirror the A-share fallback validation pattern for HK canonical columns, and route unadjusted HK daily data to a new dedicated storage table. Keep the DAG as a thin scheduler that requests `AdjustType.BFQ` from 2026-01-01 and relies on storage-backed incremental ranges.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy ORM, Airflow `PythonOperator`, pytest, Ruff, project commands through `uv run`.

## Global Constraints

- Use `uv run` for all Python commands in this repository.
- Do not change DAG schedule, dependencies, retries, task boundaries, SLA, `catchup`, or `max_active_runs`.
- Preserve current HK GGT HFQ downloader behavior and HFQ storage tables.
- Use `AdjustType.BFQ` as the internal unadjusted value because it already maps to `""`; name DAG tasks/logs/tables with `none` or `unadjusted` to avoid BFQ/HFQ confusion.
- HK fallback order is configured by `DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER`, defaulting to `tushare,akshare`.
- Fallback triggers only for provider exceptions, `None`, empty DataFrames, missing core columns, or invalid core numerics; storage-save failures must not trigger fallback.
- Add any new business table to `tools/db_common.sh`.
- Do not commit unless the user explicitly asks for a commit.

---

## File Structure

- Modify `download/provider_order.py`: add HK provider-order constants and parser beside the A-share parser.
- Modify `conf/global_settings.py`: bridge `[download].hk_stock_history_provider_order` into `DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER`.
- Modify `download/dl/downloader.py`: expose HK provider dispatch for `tushare` and `akshare`.
- Modify `download/dl/downloader_akshare.py`: ensure HK unadjusted data is normalized enough for common HK validation.
- Modify `download/download_manager.py`: add HK canonical validation and fallback helper; route HK downloads through it.
- Modify `storage/model/history_data_hk_stock.py`: add unadjusted daily table model.
- Modify `storage/model/__init__.py` and `storage/__init__.py`: export the new table/model so metadata and consumers see it.
- Modify `storage/storage_db.py`: route `HK_GGT_STOCK + DAILY + BFQ` to the new table; make HK save/load respect `adjust`.
- Modify `tools/db_common.sh`: include the new unadjusted HK daily business table.
- Modify `dags/download_hk_ggt_history_daily.py`: request unadjusted daily data from 2026-01-01 and rename HFQ-specific identifiers.
- Add/modify focused tests under `test/conf/`, `test/download/`, `test/download/dl/`, `test/storage/`, and `test/dags/`.

---

### Task 1: HK provider-order configuration

**Files:**
- Modify: `download/provider_order.py`
- Modify: `conf/global_settings.py`
- Test: `test/download/test_provider_order.py`
- Test: `test/conf/test_global_settings_download.py`

**Interfaces:**
- Produces: `HK_STOCK_HISTORY_PROVIDER_ENV: str`
- Produces: `DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER: tuple[str, ...]`
- Produces: `parse_hk_stock_history_provider_order(value: str | None = None) -> list[str]`
- Consumed by later tasks: `DownloadManager._download_hk_stock_history_with_fallback()`

- [ ] **Step 1: Write failing provider-order tests**

Append these tests to `test/download/test_provider_order.py`:

```python
import pytest

from download.provider_order import parse_hk_stock_history_provider_order


def test_parse_hk_stock_history_provider_order_defaults(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    assert parse_hk_stock_history_provider_order() == ["tushare", "akshare"]


def test_parse_hk_stock_history_provider_order_normalizes_and_dedupes():
    assert parse_hk_stock_history_provider_order(" akshare, tushare, AKSHARE ,, ") == [
        "akshare",
        "tushare",
    ]


def test_parse_hk_stock_history_provider_order_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported HK stock history provider: yahoo"):
        parse_hk_stock_history_provider_order("tushare,yahoo")


def test_parse_hk_stock_history_provider_order_rejects_empty_order():
    with pytest.raises(ValueError, match="HK stock history provider order is empty"):
        parse_hk_stock_history_provider_order(" , , ")
```

- [ ] **Step 2: Write failing config bridge tests**

In `test/conf/test_global_settings_download.py`, add tests matching the existing `parse_download_config` style:

```python
from configparser import ConfigParser

from conf.global_settings import parse_download_config


def test_parse_download_config_sets_default_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {}
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare,akshare"


def test_parse_download_config_sets_configured_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {"hk_stock_history_provider_order": "akshare,tushare"}
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "akshare,tushare"


def test_parse_download_config_preserves_existing_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {"hk_stock_history_provider_order": "akshare,tushare"}
    monkeypatch.setenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", "tushare")

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare"
```

If the file does not already import `os`, add `import os` at the top.

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/test_provider_order.py test/conf/test_global_settings_download.py -q
```

Expected: FAIL because `parse_hk_stock_history_provider_order` and the HK env bridge do not exist.

- [ ] **Step 4: Implement provider parser**

Update `download/provider_order.py` to keep the existing A-share parser and add HK parser:

```python
HK_STOCK_HISTORY_PROVIDER_ENV = "DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"
DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER = ("tushare", "akshare")
VALID_HK_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)


def _parse_provider_order(
    *,
    raw_value: str,
    valid_providers: frozenset[str],
    unsupported_message: str,
    empty_message: str,
) -> list[str]:
    providers: list[str] = []
    seen: set[str] = set()
    for raw_provider in raw_value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in valid_providers:
            raise ValueError(unsupported_message.format(provider=provider))
        if provider in seen:
            continue
        seen.add(provider)
        providers.append(provider)

    if not providers:
        raise ValueError(empty_message)
    return providers


def parse_hk_stock_history_provider_order(value: str | None = None) -> list[str]:
    raw_value = value if value is not None else os.getenv(HK_STOCK_HISTORY_PROVIDER_ENV)
    if raw_value is None:
        raw_value = ",".join(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)

    return _parse_provider_order(
        raw_value=raw_value,
        valid_providers=VALID_HK_STOCK_HISTORY_PROVIDERS,
        unsupported_message="Unsupported HK stock history provider: {provider}",
        empty_message="HK stock history provider order is empty",
    )
```

Refactor `parse_stock_history_provider_order()` to call `_parse_provider_order()` with the existing messages so current A-share tests continue to pass.

- [ ] **Step 5: Implement config bridge**

Update imports in `conf/global_settings.py`:

```python
from download.provider_order import (
    DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER,
    DEFAULT_STOCK_HISTORY_PROVIDER_ORDER,
    HK_STOCK_HISTORY_PROVIDER_ENV,
    STOCK_HISTORY_PROVIDER_ENV,
)
```

Then extend `parse_download_config()` after the existing A-share provider-order block:

```python
    if HK_STOCK_HISTORY_PROVIDER_ENV not in os.environ:
        try:
            os.environ[HK_STOCK_HISTORY_PROVIDER_ENV] = config["download"]["hk_stock_history_provider_order"]
        except KeyError:
            os.environ[HK_STOCK_HISTORY_PROVIDER_ENV] = ",".join(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest test/download/test_provider_order.py test/conf/test_global_settings_download.py -q
```

Expected: PASS.

---

### Task 2: HK unadjusted storage table and routing

**Files:**
- Modify: `storage/model/history_data_hk_stock.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Modify: `storage/storage_db.py`
- Modify: `tools/db_common.sh`
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Produces: `tb_name_history_data_daily_hk_stock_bfq = "history_data_daily_hk_stock_none"`
- Produces: `HistoryDataDailyHkStockBFQ(Base)`
- Produces: `get_table_name(SecurityType.HK_GGT_STOCK, PeriodType.DAILY, AdjustType.BFQ) -> "history_data_daily_hk_stock_none"`
- Produces: `StorageDb.save_history_data_hk_stock(df, PeriodType.DAILY, AdjustType.BFQ) -> bool`
- Produces: `StorageDb.load_history_data_stock_hk_ggt(..., adjust=AdjustType.BFQ)` support

- [ ] **Step 1: Write failing table-name test**

Add to `test/storage/test_storage_db.py` near other table routing tests:

```python
from common.const import AdjustType, PeriodType, SecurityType
from storage import get_table_name
from storage.model import tb_name_history_data_daily_hk_stock_bfq


def test_get_table_name_returns_hk_stock_bfq_daily_table():
    assert (
        get_table_name(SecurityType.HK_GGT_STOCK, PeriodType.DAILY, AdjustType.BFQ)
        == tb_name_history_data_daily_hk_stock_bfq
    )
```

- [ ] **Step 2: Write failing save/load routing tests**

Add tests that patch `_get_history_table_name`, `_write_dataframe`, and `query_data` rather than requiring a live database:

```python
import pandas as pd

from common.const import AdjustType, PeriodType, SecurityType


def test_save_history_data_hk_stock_uses_requested_bfq_table(mocker, storage_db):
    df = pd.DataFrame(
        {
            "日期": [pd.Timestamp("2026-01-02")],
            "股票代码": ["00700"],
            "开盘": [300.0],
            "收盘": [301.0],
            "最高": [302.0],
            "最低": [299.0],
            "成交量": [1000],
            "成交额": [300000.0],
        }
    )
    get_table = mocker.patch.object(storage_db, "_get_history_table_name", return_value="history_data_daily_hk_stock_none")
    write_dataframe = mocker.patch.object(storage_db, "_write_dataframe")

    assert storage_db.save_history_data_hk_stock(df, PeriodType.DAILY, AdjustType.BFQ) is True

    get_table.assert_called_once_with(SecurityType.HK_GGT_STOCK, PeriodType.DAILY, AdjustType.BFQ)
    write_dataframe.assert_called_once()
    assert write_dataframe.call_args.args[1] == "history_data_daily_hk_stock_none"
```

For load routing, match the existing signature of `load_history_data_stock_hk_ggt()` in the file before adding the test. The assertion must verify that `AdjustType.BFQ` reaches `get_table_name()` and no HFQ-only rejection occurs.

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest test/storage/test_storage_db.py -q
```

Expected: FAIL because the BFQ HK table and routing do not exist.

- [ ] **Step 4: Add ORM table**

In `storage/model/history_data_hk_stock.py`, add the table constant after line 18:

```python
tb_name_history_data_daily_hk_stock_bfq = "history_data_daily_hk_stock_none"
```

Add model mirroring `HistoryDataDailyHkStockHFQ`:

```python
class HistoryDataDailyHkStockBFQ(Base):
    __tablename__ = tb_name_history_data_daily_hk_stock_bfq

    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    股票代码 = Column(COL_STOCK_ID, String(10), primary_key=True, nullable=False, comment="股票代码")
    开盘 = Column(COL_OPEN, Float, nullable=True, comment="开盘价")
    收盘 = Column(COL_CLOSE, Float, nullable=True, comment="收盘价")
    最高 = Column(COL_HIGH, Float, nullable=True, comment="最高价")
    最低 = Column(COL_LOW, Float, nullable=True, comment="最低价")
    成交量 = Column(COL_VOLUME, BigInteger, nullable=True, comment="成交量")
    成交额 = Column(COL_AMOUNT, Float, nullable=True, comment="成交额")
    振幅 = Column("振幅", Float, nullable=True, comment="振幅百分比")
    涨跌幅 = Column(COL_CHANGE_RATE, Float, nullable=True, comment="涨跌幅百分比")
    涨跌额 = Column("涨跌额", Float, nullable=True, comment="涨跌额")
    换手率 = Column(COL_TURNOVER_RATE, Float, nullable=True, comment="换手率百分比")
```

- [ ] **Step 5: Export model and table name**

Update `storage/model/__init__.py` imports:

```python
from .history_data_hk_stock import (
    HistoryDataDailyHkStockBFQ,
    tb_name_history_data_daily_hk_stock_bfq,
    tb_name_history_data_daily_hk_stock_hfq,
    tb_name_history_data_monthly_hk_stock_hfq,
    tb_name_history_data_weekly_hk_stock_hfq,
)
```

Add both names to `__all__`:

```python
"HistoryDataDailyHkStockBFQ",
"tb_name_history_data_daily_hk_stock_bfq",
```

Update `storage/__init__.py` to import/export `tb_name_history_data_daily_hk_stock_bfq`.

- [ ] **Step 6: Route storage by adjust**

Update `get_table_name()` in `storage/storage_db.py` under `SecurityType.HK_GGT_STOCK`:

```python
    elif security_type == SecurityType.HK_GGT_STOCK:
        if period == PeriodType.DAILY and adjust == AdjustType.BFQ:
            return tb_name_history_data_daily_hk_stock_bfq
        if period == PeriodType.DAILY and adjust == AdjustType.HFQ:
            return tb_name_history_data_daily_hk_stock_hfq
        elif period == PeriodType.WEEKLY and adjust == AdjustType.HFQ:
            return tb_name_history_data_weekly_hk_stock_hfq
        elif period == PeriodType.MONTHLY and adjust == AdjustType.HFQ:
            return tb_name_history_data_monthly_hk_stock_hfq
```

Update `save_history_data_hk_stock()` to pass the requested `adjust`:

```python
table_name = self._get_history_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
```

Keep the existing `try/except` and logging structure.

- [ ] **Step 7: Update HK load routing**

Find `load_history_data_stock_hk_ggt()` in `storage/storage_db.py`. Remove the HFQ-only rejection for daily BFQ and route through `_get_history_table_name(SecurityType.HK_GGT_STOCK, period, adjust)`. Preserve existing behavior for unsupported weekly/monthly non-HFQ combinations.

The core routing should be:

```python
table_name = self._get_history_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
```

Then reuse the existing query-building logic unchanged.

- [ ] **Step 8: Update DB export/import table list**

Add `history_data_daily_hk_stock_none` after `history_data_daily_hk_stock_hfq` in `tools/db_common.sh`:

```bash
  history_data_daily_hk_stock_hfq
  history_data_daily_hk_stock_none
  history_data_weekly_hk_stock_hfq
```

- [ ] **Step 9: Run focused storage tests**

Run:

```bash
uv run pytest test/storage/test_storage_db.py -q
```

Expected: PASS, or unrelated pre-existing DB integration skips/failures clearly separated from the new focused tests.

---

### Task 3: HK provider dispatch, AkShare normalization, and fallback

**Files:**
- Modify: `download/dl/downloader.py`
- Modify: `download/dl/downloader_akshare.py`
- Modify: `download/download_manager.py`
- Test: `test/download/dl/test_downloader.py`
- Test: `test/download/dl/test_downloader_akshare.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Produces: `HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS: dict[str, StockHistoryDownloader]`
- Produces: `Downloader.dl_history_data_stock_hk_by_provider(provider, stock_id, start_date, end_date, period, adjust) -> pd.DataFrame`
- Produces: `_validate_hk_stock_history_data(df: Any) -> pd.DataFrame`
- Produces: `DownloadManager._download_hk_stock_history_with_fallback(...) -> pd.DataFrame | None`

- [ ] **Step 1: Write failing dispatcher tests**

In `test/download/dl/test_downloader.py`, add:

```python
import pytest

from common.const import AdjustType, PeriodType
from download.dl.downloader import Downloader


def test_dl_history_data_stock_hk_by_provider_rejects_unknown_provider():
    downloader = Downloader()

    with pytest.raises(ValueError, match="Unsupported HK stock history provider: yahoo"):
        downloader.dl_history_data_stock_hk_by_provider(
            "yahoo", "00700", "20260101", "20260102", PeriodType.DAILY, AdjustType.BFQ
        )
```

- [ ] **Step 2: Write failing AkShare unadjusted normalization test**

In `test/download/dl/test_downloader_akshare.py`, add or extend an HK test by patching `ak.stock_hk_hist`:

```python
import pandas as pd

from common.const import AdjustType, COL_AMOUNT, COL_CLOSE, COL_DATE, COL_HIGH, COL_LOW, COL_OPEN, COL_STOCK_ID, COL_VOLUME, PeriodType
from download.dl.downloader_akshare import download_history_data_stock_hk_ak


def test_download_history_data_stock_hk_ak_uses_unadjusted_adjust_value(mocker):
    stock_hk_hist = mocker.patch(
        "download.dl.downloader_akshare.ak.stock_hk_hist",
        return_value=pd.DataFrame(
            {
                "日期": ["2026-01-02"],
                "开盘": [300.0],
                "收盘": [301.0],
                "最高": [302.0],
                "最低": [299.0],
                "成交量": [1000],
                "成交额": [300000.0],
                "涨跌幅": [1.0],
                "换手率": [0.5],
            }
        ),
    )

    df = download_history_data_stock_hk_ak("00700", "2026-01-01", "2026-01-03", PeriodType.DAILY, AdjustType.BFQ)

    stock_hk_hist.assert_called_once_with(
        symbol="00700", period="daily", start_date="20260101", end_date="20260103", adjust=""
    )
    assert list(df[[COL_DATE, COL_STOCK_ID, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME, COL_AMOUNT]].columns) == [
        COL_DATE,
        COL_STOCK_ID,
        COL_OPEN,
        COL_CLOSE,
        COL_HIGH,
        COL_LOW,
        COL_VOLUME,
        COL_AMOUNT,
    ]
    assert df.loc[0, COL_STOCK_ID] == "00700"
```

- [ ] **Step 3: Write failing HK fallback manager tests**

In `test/download/test_download_manager.py`, add tests mirroring A-share fallback tests. Use `mocker.patch("download.download_manager.parse_hk_stock_history_provider_order", return_value=["tushare", "akshare"])`, patch `manager.downloader.dl_history_data_stock_hk_by_provider`, and patch `get_storage()`.

Core success-after-fallback test:

```python
def test_download_hk_ggt_history_falls_back_to_akshare_on_tushare_exception(mocker):
    manager = DownloadManager()
    mocker.patch("download.download_manager.parse_hk_stock_history_provider_order", return_value=["tushare", "akshare"])
    hk_df = pd.DataFrame(
        {
            COL_DATE: [pd.Timestamp("2026-01-02")],
            COL_STOCK_ID: ["00700"],
            COL_OPEN: [300.0],
            COL_HIGH: [302.0],
            COL_LOW: [299.0],
            COL_CLOSE: [301.0],
            COL_VOLUME: [1000],
            COL_AMOUNT: [300000.0],
        }
    )
    download = mocker.patch.object(
        manager.downloader,
        "dl_history_data_stock_hk_by_provider",
        side_effect=[RuntimeError("unsupported adjust"), hk_df],
    )
    storage = mocker.Mock()
    storage.get_last_record.return_value = None
    storage.save_history_data_hk_stock.return_value = True
    mocker.patch("download.download_manager.get_storage", return_value=storage)

    assert manager.download_hk_ggt_history("00700", PeriodType.DAILY, "2026-01-01", "2026-01-03", AdjustType.BFQ) is True

    assert [call.args[0] for call in download.call_args_list] == ["tushare", "akshare"]
    storage.save_history_data_hk_stock.assert_called_once()
```

Add separate tests for empty DataFrame, missing core column, bad numeric value, first provider success short-circuit, all providers fail returning `False`, and save failure not calling the second provider.

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
uv run pytest test/download/dl/test_downloader.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py -q
```

Expected: FAIL because HK provider dispatch and fallback do not exist.

- [ ] **Step 5: Implement HK dispatch**

Update imports in `download/dl/downloader.py` to import `download_history_data_stock_hk_ak`. Add:

```python
HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS: dict[str, StockHistoryDownloader] = {
    "tushare": download_history_data_stock_hk_ts,
    "akshare": download_history_data_stock_hk_ak,
}
```

Add method to `Downloader`:

```python
    def dl_history_data_stock_hk_by_provider(
        self,
        provider: str,
        stock_id: str,
        start_date: str,
        end_date: str,
        period: PeriodType,
        adjust: AdjustType,
    ) -> pd.DataFrame:
        try:
            downloader_func = HK_STOCK_HISTORY_PROVIDER_DOWNLOADERS[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported HK stock history provider: {provider}") from exc
        return downloader_func(stock_id, start_date, end_date, period, adjust)
```

- [ ] **Step 6: Harden AkShare HK downloader normalization**

In `download/dl/downloader_akshare.py`, update `download_history_data_stock_hk_ak()` after assigning `COL_STOCK_ID`:

```python
    df = df.rename(columns={"涨跌幅": COL_CHANGE_RATE, "换手率": COL_TURNOVER_RATE})

    required_columns = [COL_DATE, COL_STOCK_ID, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME, COL_AMOUNT]
    for column in required_columns:
        if column not in df.columns:
            raise ValueError(f"Missing required column '{column}' in AkShare stock_hk_hist response")

    required_numeric = [COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME, COL_AMOUNT]
    for column in required_numeric:
        df[column] = pd.to_numeric(df[column], errors="raise")

    optional_numeric = [COL_CHANGE_RATE, COL_TURNOVER_RATE, "涨跌额", "振幅"]
    for column in optional_numeric:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df.reset_index(drop=True)
```

- [ ] **Step 7: Implement HK validation and fallback**

In `download/download_manager.py`, import `parse_hk_stock_history_provider_order` and add:

```python
REQUIRED_HK_STOCK_HISTORY_COLUMNS = REQUIRED_STOCK_HISTORY_COLUMNS


def _validate_hk_stock_history_data(df: Any) -> pd.DataFrame:
    if df is None:
        raise ValueError("provider returned None")
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"provider returned {type(df)}, expected DataFrame")
    if df.empty:
        raise ValueError("provider returned empty DataFrame")

    missing_columns = [column for column in REQUIRED_HK_STOCK_HISTORY_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"provider result missing required columns: {missing_columns}")

    validated = df.copy()
    validated[COL_DATE] = pd.to_datetime(validated[COL_DATE])
    numeric_columns = [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME, COL_AMOUNT]
    for column in numeric_columns:
        validated[column] = pd.to_numeric(validated[column], errors="raise")
    return validated
```

Add `DownloadManager._download_hk_stock_history_with_fallback()` mirroring `_download_stock_history_with_fallback()` but using `parse_hk_stock_history_provider_order()`, `dl_history_data_stock_hk_by_provider()`, `_validate_hk_stock_history_data()`, and HK-specific log messages.

- [ ] **Step 8: Route HK manager method through fallback**

Update `DownloadManager.download_hk_ggt_history()` so it no longer calls `_download_history_data()` with `self.downloader.dl_history_data_stock_hk`. It should mirror `download_stock_history()` incremental structure:

```python
table_name = get_table_name(SecurityType.HK_GGT_STOCK, period, adjust)
last_record = get_storage().get_last_record(table_name, stock_id)
...
df = self._download_hk_stock_history_with_fallback(stock_id, actual_start_date, end_date, period, adjust)
if df is None:
    return False
return get_storage().save_history_data_hk_stock(df, period, adjust)
```

Keep `None`/empty results as fallback failures inside the helper. If the helper returns `None`, all providers failed and the method returns `False`.

- [ ] **Step 9: Run focused download tests**

Run:

```bash
uv run pytest test/download/dl/test_downloader.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py -q
```

Expected: PASS.

---

### Task 4: Switch HK GGT DAG to unadjusted daily from 2026-01-01

**Files:**
- Modify: `dags/download_hk_ggt_history_daily.py`
- Test: `test/dags/test_partition_dag_sources.py`

**Interfaces:**
- Consumes: `DownloadManager.download_hk_ggt_history(... adjust=AdjustType.BFQ)` from Task 3
- Produces: DAG task ids `download_hk_ggt_history_none_p{pid:02d}`

- [ ] **Step 1: Write/update failing DAG source assertions**

Update `test/dags/test_partition_dag_sources.py` assertions for `download_hk_ggt_history_daily.py` so they expect:

```python
assert 'DEFAULT_START_DATE: Final = "2026-01-01"' in source
assert "AdjustType.BFQ" in source
assert "download_hk_ggt_history_none_p" in source
assert "download_hk_ggt_history_hfq_p" not in source
```

Preserve any existing assertions for `PARTITION_COUNT = 1`, schedule, dependency shape, and Redis key.

- [ ] **Step 2: Run DAG test to verify failure**

Run:

```bash
uv run pytest test/dags/test_partition_dag_sources.py -q
```

Expected: FAIL because the DAG still references 2010/HFQ/HFQ task IDs.

- [ ] **Step 3: Update DAG constants and function names**

In `dags/download_hk_ggt_history_daily.py`:

```python
"""DAG for downloading HK GGT stock unadjusted daily history on weekdays."""

DEFAULT_START_DATE: Final = "2026-01-01"
```

Rename `download_hk_ggt_history_hfq_partition_task` to `download_hk_ggt_history_none_partition_task`.

- [ ] **Step 4: Update DAG download call and progress logs**

Change the manager call:

```python
success = manager.download_hk_ggt_history(
    stock_id=stock_id,
    period=PeriodType.DAILY,
    start_date=start_date,
    end_date=end_date,
    adjust=AdjustType.BFQ,
)
```

Change log/error text from `HK HFQ` to `HK unadjusted` or `HK NONE`.

- [ ] **Step 5: Update task IDs and aggregation**

Change task id construction in both places:

```python
task_id = f"download_hk_ggt_history_none_p{pid:02d}"
```

In `partition_tasks`, use `python_callable=download_hk_ggt_history_none_partition_task`.

- [ ] **Step 6: Run DAG test**

Run:

```bash
uv run pytest test/dags/test_partition_dag_sources.py -q
```

Expected: PASS.

---

### Task 5: Integrated verification and cleanup

**Files:**
- Review all changed files from Tasks 1-4
- Modify docs only if implementation materially differs from `docs/superpowers/specs/2026-07-21-hk-ggt-unadjusted-fallback-design.md`

**Interfaces:**
- Consumes all interfaces from prior tasks
- Produces verified implementation ready for user review

- [ ] **Step 1: Run focused test suite**

Run:

```bash
uv run pytest \
  test/download/test_provider_order.py \
  test/conf/test_global_settings_download.py \
  test/storage/test_storage_db.py \
  test/download/dl/test_downloader.py \
  test/download/dl/test_downloader_akshare.py \
  test/download/test_download_manager.py \
  test/dags/test_partition_dag_sources.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run formatting/linting for touched Python files**

Run:

```bash
uv run ruff format download/provider_order.py conf/global_settings.py download/dl/downloader.py download/dl/downloader_akshare.py download/download_manager.py storage/model/history_data_hk_stock.py storage/model/__init__.py storage/__init__.py storage/storage_db.py dags/download_hk_ggt_history_daily.py test/download/test_provider_order.py test/conf/test_global_settings_download.py test/storage/test_storage_db.py test/download/dl/test_downloader.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py test/dags/test_partition_dag_sources.py
uv run ruff check download/provider_order.py conf/global_settings.py download/dl/downloader.py download/dl/downloader_akshare.py download/download_manager.py storage/model/history_data_hk_stock.py storage/model/__init__.py storage/__init__.py storage/storage_db.py dags/download_hk_ggt_history_daily.py test/download/test_provider_order.py test/conf/test_global_settings_download.py test/storage/test_storage_db.py test/download/dl/test_downloader.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py test/dags/test_partition_dag_sources.py
```

Expected: both commands PASS.

- [ ] **Step 3: Inspect diff for scope control**

Run:

```bash
git diff -- download/provider_order.py conf/global_settings.py download/dl/downloader.py download/dl/downloader_akshare.py download/download_manager.py storage/model/history_data_hk_stock.py storage/model/__init__.py storage/__init__.py storage/storage_db.py tools/db_common.sh dags/download_hk_ggt_history_daily.py test/download/test_provider_order.py test/conf/test_global_settings_download.py test/storage/test_storage_db.py test/download/dl/test_downloader.py test/download/dl/test_downloader_akshare.py test/download/test_download_manager.py test/dags/test_partition_dag_sources.py docs/superpowers/specs/2026-07-21-hk-ggt-unadjusted-fallback-design.md docs/superpowers/plans/2026-07-21-hk-ggt-unadjusted-fallback.md
```

Expected: diff only covers the HK GGT unadjusted fallback chain, its tests, `tools/db_common.sh`, and the spec/plan docs.

- [ ] **Step 4: Commit gate**

If and only if the user explicitly asks for a commit, run the repository commit workflow, including inspecting status/diff/log and using the `update_doc` skill before committing. If the user has not asked for a commit, do not commit; report changed files and verification evidence.

---

## Self-Review Notes

- Spec coverage: configuration, fallback triggers, storage isolation, DAG switch to `2026-01-01`, HFQ preservation, and focused verification are each mapped to Tasks 1-5.
- Placeholder scan: no incomplete implementation slots remain.
- Type consistency: provider parser returns `list[str]`; HK dispatch uses the same `StockHistoryDownloader` signature as A-share; storage routing uses existing `AdjustType.BFQ` as unadjusted.
