# Issue 66 Raw ETF Share/Size Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a raw ETF share/size Tushare download path that normalizes provider ETF code/date fields and idempotently persists rows by ETF code and date.

**Architecture:** Keep the feature as a narrow raw-data layer. `downloader_tushare.py` owns provider parameters and normalized DataFrame shape, `storage/model/etf_share_size.py` owns the SQLAlchemy table definition and unit comments, `StorageDb.save_etf_share_size()` owns conflict-update persistence, and `DownloadManager.download_etf_share_size()` orchestrates downloader-to-storage flow.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, Tushare pro client wrapper, pytest, uv.

## Global Constraints

- Use `uv run` for Python commands in this repo. Do not use bare `python` or `python3` for project tasks.
- Scope is issue #66 only: raw ETF share/size download, normalization, idempotent persistence, DB script coverage, and offline tests.
- Do not implement index turnover, derived ETF flow calculations, UI, holder-disclosure parsing, or ETF share adjustment.
- Provider fields must explicitly cover `ts_code`, `trade_date`, `close`, `nav`, `total_share`, and `total_size`.
- Provider ETF identifiers must normalize to bare six-digit ETF codes.
- Empty provider responses must return a stable normalized DataFrame shape.
- Raw provider units for `total_share` and `total_size` must be documented on persisted model fields.
- Upsert behavior must support PostgreSQL and SQLite dialects.

---

## File Structure

- Create `storage/model/etf_share_size.py`: SQLAlchemy model/table name for raw ETF share/size.
- Modify `common/const.py`: add `COL_NAV`, `COL_ETF_TOTAL_SHARE`, `COL_ETF_TOTAL_SIZE`.
- Modify `storage/model/__init__.py` and `storage/__init__.py`: export model/table constants.
- Modify `download/dl/downloader_tushare.py`: add `etf_share_size_fields`, stable normalized columns, and `download_etf_share_size()`.
- Modify `download/dl/downloader.py`: expose `Downloader.dl_etf_share_size`.
- Modify `storage/storage_db.py`: add column mapping and `save_etf_share_size()` with PostgreSQL/SQLite `on_conflict_do_update`.
- Modify `download/download_manager.py`: add `download_etf_share_size()` orchestration.
- Modify `tools/db_common.sh`: add `etf_share_size` to `BUSINESS_TABLES`.
- Add/update tests in `test/download`, `test/storage`, and `test/tools`.

---

### Task 1: Storage Model and Exports

**Files:**
- Modify: `common/const.py`
- Create: `storage/model/etf_share_size.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Test: `test/storage/model/test_etf_share_size.py`

**Interfaces:**
- Produces constants: `COL_NAV`, `COL_ETF_TOTAL_SHARE`, `COL_ETF_TOTAL_SIZE`.
- Produces model: `ETFShareSize` with `tb_name_etf_share_size = "etf_share_size"`.

- [ ] **Step 1: Write failing model tests**

Create `test/storage/model/test_etf_share_size.py`:

```python
from common.const import COL_CLOSE, COL_DATE, COL_ETF_ID
from storage.model import ETFShareSize, tb_name_etf_share_size


def test_etf_share_size_table_name_and_primary_keys():
    table = ETFShareSize.__table__
    assert tb_name_etf_share_size == "etf_share_size"
    assert table.name == "etf_share_size"
    assert list(table.primary_key.columns.keys()) == [COL_ETF_ID, COL_DATE]


def test_etf_share_size_documents_raw_provider_units():
    table = ETFShareSize.__table__
    assert table.c[COL_CLOSE].comment == "Tushare etf_share_size close，原始单位"
    assert "Tushare etf_share_size total_share" in table.c["总份额"].comment
    assert "原始单位" in table.c["总份额"].comment
    assert "Tushare etf_share_size total_size" in table.c["总规模"].comment
    assert "原始单位" in table.c["总规模"].comment
```

- [ ] **Step 2: Run failing test**

Run: `uv run pytest test/storage/model/test_etf_share_size.py -v`

Expected: FAIL because `ETFShareSize` does not exist.

- [ ] **Step 3: Implement model and exports**

Add constants in `common/const.py` after `COL_AMOUNT`:

```python
COL_NAV = "单位净值"
COL_ETF_TOTAL_SHARE = "总份额"
COL_ETF_TOTAL_SIZE = "总规模"
```

Create `storage/model/etf_share_size.py`:

```python
from sqlalchemy import Column, Date, Float, String

from common.const import COL_CLOSE, COL_DATE, COL_ETF_ID, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE, COL_NAV

from .base import Base

tb_name_etf_share_size = "etf_share_size"


class ETFShareSize(Base):
    __tablename__ = tb_name_etf_share_size

    基金代码 = Column(COL_ETF_ID, String(6), primary_key=True, nullable=False, comment="ETF代码")
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    收盘价 = Column(COL_CLOSE, Float, nullable=True, comment="Tushare etf_share_size close，原始单位")
    单位净值 = Column(COL_NAV, Float, nullable=True, comment="Tushare etf_share_size nav，原始单位")
    总份额 = Column(COL_ETF_TOTAL_SHARE, Float, nullable=True, comment="Tushare etf_share_size total_share，原始单位")
    总规模 = Column(COL_ETF_TOTAL_SIZE, Float, nullable=True, comment="Tushare etf_share_size total_size，原始单位")
```

Export `ETFShareSize` and `tb_name_etf_share_size` from `storage/model/__init__.py`; export `tb_name_etf_share_size` from `storage/__init__.py`.

- [ ] **Step 4: Verify model tests pass**

Run: `uv run pytest test/storage/model/test_etf_share_size.py -v`

Expected: PASS.

---

### Task 2: Downloader Normalization

**Files:**
- Modify: `download/dl/downloader_tushare.py`
- Modify: `download/dl/downloader.py`
- Test: `test/download/dl/test_downloader_tushare.py`

**Interfaces:**
- Produces `download_etf_share_size(ts_code="", trade_date="", start_date="", end_date="", pro=None) -> pd.DataFrame`.
- Produces `Downloader.dl_etf_share_size`.
- Output columns: `基金代码`, `日期`, `收盘`, `单位净值`, `总份额`, `总规模`.

- [ ] **Step 1: Add failing downloader tests**

Append tests to `test/download/dl/test_downloader_tushare.py` that assert:

```python
def test_download_etf_share_size_uses_explicit_fields_and_normalizes(downloader_ts_module, monkeypatch):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    pro_stub.etf_share_size = Mock(return_value=pd.DataFrame({
        "ts_code": ["510300.SH"],
        "trade_date": ["20240105"],
        "close": [3.5],
        "nav": [3.48],
        "total_share": [123.4],
        "total_size": [432.1],
    }))
    result = module.download_etf_share_size(ts_code="510300", start_date="2024-01-01", end_date="2024-01-05")
    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.etf_share_size.assert_called_once_with(
        ts_code="510300.SH", trade_date="", start_date="20240101", end_date="20240105", fields=module.etf_share_size_fields
    )
    assert result.to_dict("records") == [{"基金代码": "510300", "日期": "2024-01-05", "收盘": 3.5, "单位净值": 3.48, "总份额": 123.4, "总规模": 432.1}]


def test_download_etf_share_size_provider_code_passthrough(downloader_ts_module, monkeypatch):
    module, _ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    pro_stub.etf_share_size = Mock(return_value=pd.DataFrame(columns=module.etf_share_size_fields))
    module.download_etf_share_size(ts_code="159915.SZ", trade_date="20240105")
    pro_stub.etf_share_size.assert_called_once_with(
        ts_code="159915.SZ", trade_date="20240105", start_date="", end_date="", fields=module.etf_share_size_fields
    )


def test_download_etf_share_size_empty_result_has_stable_shape(downloader_ts_module, monkeypatch):
    module, _ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    pro_stub.etf_share_size = Mock(return_value=pd.DataFrame())
    result = module.download_etf_share_size(trade_date="2024-01-05")
    assert list(result.columns) == module.etf_share_size_columns
    assert result.empty
```

- [ ] **Step 2: Run failing downloader tests**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py -k etf_share_size -v`

Expected: FAIL because downloader function/constants do not exist.

- [ ] **Step 3: Implement downloader**

In `download/dl/downloader_tushare.py`, import `COL_ETF_ID`, `COL_ETF_TOTAL_SHARE`, `COL_ETF_TOTAL_SIZE`, and `COL_NAV`. Add:

```python
etf_share_size_fields = ["ts_code", "trade_date", "close", "nav", "total_share", "total_size"]
etf_share_size_columns = [COL_ETF_ID, COL_DATE, COL_CLOSE, COL_NAV, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE]


def _to_etf_ts_code(etf_id_or_ts_code: str) -> str:
    if not etf_id_or_ts_code:
        return ""
    if re.fullmatch(r"\d{6}\.(SH|SZ)", etf_id_or_ts_code):
        return etf_id_or_ts_code
    if not re.fullmatch(r"\d{6}", etf_id_or_ts_code):
        raise ValueError("ETF code must be 6 digits or provider-style ts_code.")
    return etf_id_or_ts_code + _get_etf_suffix(etf_id_or_ts_code)


def _empty_etf_share_size_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=etf_share_size_columns)
```

Add decorated function near `download_etf_daily()`:

```python
@retrying.retry(wait_exponential_multiplier=2000, wait_exponential_max=60000, stop_max_attempt_number=3)
@get_pro
def download_etf_share_size(ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "", pro: Any | None = None) -> pd.DataFrame | Any:
    normalized_trade_date = convert_date(trade_date) if trade_date else ""
    normalized_start_date = convert_date(start_date) if start_date else ""
    normalized_end_date = convert_date(end_date) if end_date else ""
    client = require_pro_client(pro)
    df = client.etf_share_size(
        ts_code=_to_etf_ts_code(ts_code),
        trade_date=normalized_trade_date,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        fields=etf_share_size_fields,
    )
    if df.empty:
        return _empty_etf_share_size_dataframe()
    normalized = df.rename(columns={"ts_code": COL_ETF_ID, "trade_date": COL_DATE, "close": COL_CLOSE, "nav": COL_NAV, "total_share": COL_ETF_TOTAL_SHARE, "total_size": COL_ETF_TOTAL_SIZE}).copy()
    normalized[COL_ETF_ID] = normalized[COL_ETF_ID].astype(str).str.split(".").str[0]
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    return normalized.reindex(columns=etf_share_size_columns).dropna(subset=[COL_DATE])
```

In `download/dl/downloader.py`, import and expose `download_etf_share_size` as `Downloader.dl_etf_share_size`.

- [ ] **Step 4: Verify downloader tests pass**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py -k etf_share_size -v`

Expected: PASS.

---

### Task 3: Storage Upsert and DB Script Coverage

**Files:**
- Modify: `storage/storage_db.py`
- Modify: `tools/db_common.sh`
- Test: `test/storage/test_storage_db.py`
- Test: `test/tools/test_db_common.py`

**Interfaces:**
- Produces `StorageDb.save_etf_share_size(df: pd.DataFrame) -> bool`.
- Consumes normalized or provider-style columns and persists to `etf_share_size`.

- [ ] **Step 1: Add failing storage tests**

Add tests near ETF storage tests in `test/storage/test_storage_db.py`:

```python
def test_save_etf_share_size_is_idempotent_for_same_primary_key(sqlite_storage):
    db, engine = sqlite_storage
    first = pd.DataFrame({"ts_code": ["510300.SH"], "trade_date": ["20240105"], "close": [3.5], "nav": [3.48], "total_share": [123.4], "total_size": [432.1]})
    second = pd.DataFrame({"ts_code": ["510300.SH"], "trade_date": ["20240105"], "close": [3.6], "nav": [3.58], "total_share": [125.0], "total_size": [450.0]})
    assert db.save_etf_share_size(first) is True
    assert db.save_etf_share_size(second) is True
    saved = pd.read_sql('SELECT * FROM etf_share_size WHERE "基金代码" = "510300"', engine)
    assert len(saved) == 1
    assert saved.iloc[0]["收盘"] == 3.6
    assert saved.iloc[0]["总份额"] == 125.0
```

Add a focused db-common assertion if `test_business_tables_cover_all_storage_models` failure is not specific enough:

```python
def test_business_tables_include_etf_share_size():
    assert "etf_share_size" in _parse_business_tables()
```

- [ ] **Step 2: Run failing storage/db tests**

Run: `uv run pytest test/storage/test_storage_db.py -k etf_share_size -v`

Run: `uv run pytest test/tools/test_db_common.py -v`

Expected: FAIL because save method and DB table coverage do not exist.

- [ ] **Step 3: Implement storage save method**

In `storage/storage_db.py`, import the new constants, `ETFShareSize`, and `tb_name_etf_share_size`. Add mapping near `COL_MAP_ETF_DAILY`:

```python
COL_MAP_ETF_SHARE_SIZE = {
    "ts_code": COL_ETF_ID,
    "trade_date": COL_DATE,
    "close": COL_CLOSE,
    "nav": COL_NAV,
    "total_share": COL_ETF_TOTAL_SHARE,
    "total_size": COL_ETF_TOTAL_SIZE,
}
```

Add method near `save_etf_daily()`:

```python
def save_etf_share_size(self, df: pd.DataFrame) -> bool:
    try:
        prepared = df.rename(columns=COL_MAP_ETF_SHARE_SIZE).copy()
        required = [COL_ETF_ID, COL_DATE, COL_CLOSE, COL_NAV, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE]
        missing = set(required) - set(prepared.columns)
        if missing:
            raise ValueError(f"ETF share/size 缺少字段: {sorted(missing)}")
        prepared = prepared[required]
        prepared[COL_ETF_ID] = prepared[COL_ETF_ID].astype(str).str.split(".").str[0]
        prepared[COL_DATE] = pd.to_datetime(prepared[COL_DATE], errors="raise").dt.date
        for column in [COL_CLOSE, COL_NAV, COL_ETF_TOTAL_SHARE, COL_ETF_TOTAL_SIZE]:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
        records = prepared.to_dict(orient="records")
        if not records:
            return True
        table = ETFShareSize.__table__
        if self.engine.dialect.name == "postgresql":
            insert_stmt = pg_insert(table).values(records)
        elif self.engine.dialect.name == "sqlite":
            insert_stmt = sqlite_insert(table).values(records)
        else:
            raise ConnectionError(f"Unsupported database dialect: {self.engine.dialect.name}")
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=list(table.primary_key.columns.keys()),
            set_={column.name: getattr(insert_stmt.excluded, column.name) for column in table.columns},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)
        logger.info(f"ETF份额规模数据保存成功: {tb_name_etf_share_size}, 数据条数: {len(prepared)}")
        return True
    except Exception as e:
        logger.error(f"保存ETF份额规模数据失败: {str(e)}")
        return False
```

Add `etf_share_size` to `BUSINESS_TABLES` immediately after `etf_daily` in `tools/db_common.sh`.

- [ ] **Step 4: Verify storage/db tests pass**

Run: `uv run pytest test/storage/test_storage_db.py -k etf_share_size -v`

Run: `uv run pytest test/tools/test_db_common.py -v`

Expected: PASS.

---

### Task 4: Download Manager Orchestration

**Files:**
- Modify: `download/download_manager.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Produces `DownloadManager.download_etf_share_size(ts_code="", trade_date="", start_date="", end_date="") -> bool`.

- [ ] **Step 1: Add failing manager tests**

Add tests in `test/download/test_download_manager.py`:

```python
def test_download_etf_share_size_saves_rows(monkeypatch):
    manager, storage, downloader = _make_manager(monkeypatch)
    df = pd.DataFrame([{"基金代码": "510300", "日期": "2024-01-05", "收盘": 3.5, "单位净值": 3.48, "总份额": 123.4, "总规模": 432.1}])
    downloader.dl_etf_share_size.return_value = df
    storage.save_etf_share_size.return_value = True
    assert manager.download_etf_share_size(ts_code="510300", start_date="20240101", end_date="20240105") is True
    downloader.dl_etf_share_size.assert_called_once_with(ts_code="510300", trade_date="", start_date="20240101", end_date="20240105")
    storage.save_etf_share_size.assert_called_once_with(df)


def test_download_etf_share_size_empty_response_is_successful_noop(monkeypatch):
    manager, storage, downloader = _make_manager(monkeypatch)
    downloader.dl_etf_share_size.return_value = pd.DataFrame(columns=["基金代码", "日期", "收盘", "单位净值", "总份额", "总规模"])
    assert manager.download_etf_share_size(trade_date="20240105") is True
    storage.save_etf_share_size.assert_not_called()
```

- [ ] **Step 2: Run failing manager tests**

Run: `uv run pytest test/download/test_download_manager.py -k etf_share_size -v`

Expected: FAIL because manager method/facade attribute does not exist.

- [ ] **Step 3: Implement manager method**

In `download/download_manager.py`, add:

```python
def download_etf_share_size(self, ts_code: str = "", trade_date: str = "", start_date: str = "", end_date: str = "") -> bool:
    try:
        df = self.downloader.dl_etf_share_size(ts_code=ts_code, trade_date=trade_date, start_date=start_date, end_date=end_date)
        if df is None:
            logging.warning("Failed to download ETF share/size data")
            return False
        if df.empty:
            logging.info("No ETF share/size data returned")
            return True
        return get_storage().save_etf_share_size(df)
    except Exception as exc:
        logging.error("下载ETF份额规模数据失败: %s", exc)
        return False
```

- [ ] **Step 4: Verify manager tests pass**

Run: `uv run pytest test/download/test_download_manager.py -k etf_share_size -v`

Expected: PASS.

---

### Task 5: Focused Verification and Simplify Review

**Files:**
- Review touched files only.
- Test: focused pytest suite below.

**Interfaces:**
- Consumes all previous tasks.
- Produces final verified implementation for issue #66.

- [ ] **Step 1: Run all focused tests**

Run:

```bash
uv run pytest test/storage/model/test_etf_share_size.py test/download/dl/test_downloader_tushare.py -k 'etf_share_size' test/storage/test_storage_db.py -k 'etf_share_size' test/download/test_download_manager.py -k 'etf_share_size' test/tools/test_db_common.py -v
```

Expected: PASS.

- [ ] **Step 2: Run formatter/linter on touched Python files**

Run:

```bash
uv run ruff format common/const.py download/dl/downloader.py download/dl/downloader_tushare.py download/download_manager.py storage/__init__.py storage/model/__init__.py storage/model/etf_share_size.py storage/storage_db.py test/storage/model/test_etf_share_size.py test/download/dl/test_downloader_tushare.py test/storage/test_storage_db.py test/download/test_download_manager.py test/tools/test_db_common.py
uv run ruff check common/const.py download/dl/downloader.py download/dl/downloader_tushare.py download/download_manager.py storage/__init__.py storage/model/__init__.py storage/model/etf_share_size.py storage/storage_db.py test/storage/model/test_etf_share_size.py test/download/dl/test_downloader_tushare.py test/storage/test_storage_db.py test/download/test_download_manager.py test/tools/test_db_common.py
```

Expected: PASS.

- [ ] **Step 3: Simplify review**

Invoke the `simplify` skill. Check whether the touched implementation can be made clearer without changing behavior. Apply only targeted simplifications that preserve issue scope.

- [ ] **Step 4: Final verification after any simplification**

Re-run the focused tests from Step 1. Expected: PASS.

---

## Self-Review

- Spec coverage: downloader explicit fields, identifier/date normalization, stable empty shape, model unit comments, idempotent persistence, DB script coverage, and offline tests are each covered by Tasks 1-5.
- Placeholder scan: no TBD/TODO placeholders remain; each task has concrete files, interfaces, commands, and expected outcomes.
- Type consistency: `download_etf_share_size(...)`, `save_etf_share_size(df)`, `ETFShareSize`, and `tb_name_etf_share_size` names are consistent across tasks.
