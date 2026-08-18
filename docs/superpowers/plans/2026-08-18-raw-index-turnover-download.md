# Raw Index Turnover Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement GitHub issue #67: downloadable and idempotently persistable raw close/turnover history for the pinned broad-market index set used by the ETF flow pipeline.

**Architecture:** Mirror the existing ETF share/size raw path: provider download in `download/dl/downloader_tushare.py`, facade wiring in `download/dl/downloader.py`, orchestration in `download/download_manager.py`, raw SQLAlchemy model plus storage upsert in `storage/`, and workflow coverage in `tools/db_common.sh`. Keep provider output raw except for stable local column names and date normalization.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, Tushare provider client, pytest, Ruff, mypy.

## Global Constraints

- Use `uv run` for Python commands in this repo.
- Mock external providers; do not call live Tushare in tests.
- Storage table additions must update `tools/db_common.sh` so export/import/clean workflows stay in sync.
- Fields representing finite, closed business sets must use enums rather than stringly typed values.
- Preserve existing downloader, manager, and storage patterns; do not change DAG schedules or unrelated workflows.
- Raw provider units for index turnover must be documented on persisted model fields.

---

### Task 1: Raw Index Constants, Model, and Workflow Registration

**Files:**
- Create: `download/core_indexes.py`
- Create: `storage/model/index_daily_turnover.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Modify: `tools/db_common.sh`
- Test: `test/download/test_core_indexes.py`
- Test: `test/storage/model/test_index_daily_turnover.py`
- Test: `test/tools/test_db_common.py`

**Interfaces:**
- Produces: `CoreIndexGroup(StrEnum)` and `CORE_INDEX_TS_CODES: Mapping[CoreIndexGroup, str]`.
- Produces: `IndexDailyTurnover` and `tb_name_index_daily_turnover = "index_daily_turnover"`.

- [ ] **Step 1: Write failing tests**

```python
def test_core_index_mapping_pins_broad_market_codes():
    from download.core_indexes import CORE_INDEX_TS_CODES, CoreIndexGroup

    assert CORE_INDEX_TS_CODES == {
        CoreIndexGroup.CSI_300: "000300.SH",
        CoreIndexGroup.SSE_50: "000016.SH",
        CoreIndexGroup.SSE_180: "000010.SH",
        CoreIndexGroup.CSI_500: "000905.SH",
        CoreIndexGroup.CSI_800: "000906.SH",
        CoreIndexGroup.CSI_1000: "000852.SH",
        CoreIndexGroup.CHINEXT: "399006.SZ",
        CoreIndexGroup.STAR_50: "000688.SH",
        CoreIndexGroup.SZSE_100: "399330.SZ",
    }
```

```python
def test_index_daily_turnover_table_name_primary_keys_and_comments():
    from common.const import COL_CLOSE, COL_DATE
    from storage.model import IndexDailyTurnover, tb_name_index_daily_turnover

    table = IndexDailyTurnover.__table__
    assert tb_name_index_daily_turnover == "index_daily_turnover"
    assert table.name == "index_daily_turnover"
    assert [column.name for column in table.primary_key.columns] == ["指数代码", COL_DATE]
    assert table.c[COL_CLOSE].comment == "Tushare index_daily close，原始单位"
    assert table.c["成交额"].comment == "Tushare index_daily amount，原始单位"
```

```python
def test_business_tables_include_index_daily_turnover():
    assert "index_daily_turnover" in _parse_business_tables()
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest test/download/test_core_indexes.py test/storage/model/test_index_daily_turnover.py test/tools/test_db_common.py -v`
Expected: FAIL because modules/table registration do not exist.

- [ ] **Step 3: Implement minimal model and registration**

Add the enum mapping, model with primary key `指数代码` + `日期`, fields `收盘` and `成交额`, exports, and `tools/db_common.sh` entry.

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest test/download/test_core_indexes.py test/storage/model/test_index_daily_turnover.py test/tools/test_db_common.py -v`
Expected: PASS.

---

### Task 2: Tushare Downloader and Manager Wiring

**Files:**
- Modify: `download/dl/downloader_tushare.py`
- Modify: `download/dl/downloader.py`
- Modify: `download/download_manager.py`
- Test: `test/download/dl/test_downloader_tushare.py`
- Test: `test/download/dl/test_downloader.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Consumes: `CORE_INDEX_TS_CODES` from Task 1.
- Produces: `download_index_daily_turnover(ts_code="", trade_date="", start_date="", end_date="")`.
- Produces: `Downloader.dl_index_daily_turnover`.
- Produces: `DownloadManager.download_index_daily_turnover(...)` and `DownloadManager.download_core_index_daily_turnover(...)`.

- [ ] **Step 1: Write failing downloader and manager tests**

```python
def test_download_index_daily_turnover_uses_explicit_fields_and_normalizes(downloader_ts_module, monkeypatch):
    module, ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    pro_stub.index_daily = Mock(return_value=pd.DataFrame({
        "ts_code": ["000300.SH"],
        "trade_date": ["20240105"],
        "close": [3350.5],
        "amount": [123456789.0],
    }))

    result = module.download_index_daily_turnover(ts_code="000300.SH", start_date="2024-01-01", end_date="2024-01-05")

    ts_stub.pro_api.assert_called_once_with(token="test_token_123")
    pro_stub.index_daily.assert_called_once_with(
        ts_code="000300.SH",
        trade_date="",
        start_date="20240101",
        end_date="20240105",
        fields=module.index_daily_turnover_fields,
    )
    assert result.to_dict("records") == [{"指数代码": "000300.SH", "日期": "2024-01-05", "收盘": 3350.5, "成交额": 123456789.0}]
```

```python
def test_download_index_daily_turnover_empty_result_has_stable_shape(downloader_ts_module, monkeypatch):
    module, _ts_stub, pro_stub = downloader_ts_module
    monkeypatch.setenv("TUSHARE_TOKEN", "test_token_123")
    pro_stub.index_daily = Mock(return_value=pd.DataFrame())
    result = module.download_index_daily_turnover(trade_date="2024-01-05")
    assert list(result.columns) == module.index_daily_turnover_columns
    assert result.empty
```

```python
def test_download_core_index_daily_turnover_requests_pinned_indexes(monkeypatch):
    manager = DownloadManager()
    downloader = Mock()
    storage = Mock()
    rows = pd.DataFrame([{"指数代码": "000300.SH", "日期": "2024-01-05", "收盘": 1.0, "成交额": 2.0}])
    downloader.dl_index_daily_turnover.return_value = rows
    storage.save_index_daily_turnover.return_value = True
    manager.downloader = downloader
    monkeypatch.setattr("download.download_manager.get_storage", lambda: storage)

    assert manager.download_core_index_daily_turnover(start_date="20240101", end_date="20240105") is True
    assert downloader.dl_index_daily_turnover.call_count == len(CORE_INDEX_TS_CODES)
    assert storage.save_index_daily_turnover.call_count == len(CORE_INDEX_TS_CODES)
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader.py test/download/test_download_manager.py -k 'index_daily_turnover or core_index' -v`
Expected: FAIL because downloader and manager methods are missing.

- [ ] **Step 3: Implement downloader and manager wiring**

Use `pro.index_daily` with explicit fields `ts_code,trade_date,close,amount`, normalize `trade_date` with `convert_date`, return stable empty columns, keep full provider-style index codes, and make empty responses successful no-ops.

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader.py test/download/test_download_manager.py -k 'index_daily_turnover or core_index' -v`
Expected: PASS.

---

### Task 3: Idempotent Storage Persistence

**Files:**
- Modify: `storage/storage_db.py`
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: `IndexDailyTurnover` and `tb_name_index_daily_turnover` from Task 1.
- Produces: `StorageDB.save_index_daily_turnover(df: pd.DataFrame) -> bool`.

- [ ] **Step 1: Write failing storage tests**

```python
def test_save_index_daily_turnover_is_idempotent_for_same_primary_key(self, sqlite_storage):
    db = sqlite_storage
    initial_df = pd.DataFrame([{"指数代码": "000300.SH", "日期": "2024-01-05", "收盘": 3350.5, "成交额": 100.0}])
    updated_df = pd.DataFrame([{"指数代码": "000300.SH", "日期": "2024-01-05", "收盘": 3360.0, "成交额": 200.0}])

    assert db.save_index_daily_turnover(initial_df) is True
    assert db.save_index_daily_turnover(updated_df) is True

    with db.engine.connect() as conn:
        rows = conn.execute(text('SELECT * FROM index_daily_turnover WHERE "指数代码" = "000300.SH"')).mappings().all()
    assert len(rows) == 1
    assert rows[0]["收盘"] == 3360.0
    assert rows[0]["成交额"] == 200.0
```

```python
def test_save_index_daily_turnover_rejects_missing_required_columns(self, sqlite_storage):
    assert sqlite_storage.save_index_daily_turnover(pd.DataFrame([{"指数代码": "000300.SH"}])) is False
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest test/storage/test_storage_db.py -k index_daily_turnover -v`
Expected: FAIL because storage method is missing.

- [ ] **Step 3: Implement minimal upsert**

Mirror `save_etf_share_size`: validate required columns, convert date to Python date, numeric-coerce close/amount, and use PostgreSQL/SQLite `on_conflict_do_update` over primary keys.

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest test/storage/test_storage_db.py -k index_daily_turnover -v`
Expected: PASS.

---

### Task 4: Focused Integration Verification and Cleanup

**Files:**
- Modify only files touched by Tasks 1-3 if verification reveals scoped defects.

**Interfaces:**
- Confirms all issue #67 acceptance criteria.

- [ ] **Step 1: Run focused issue suite**

Run: `uv run pytest test/download/test_core_indexes.py test/download/dl/test_downloader_tushare.py test/download/dl/test_downloader.py test/download/test_download_manager.py test/storage/model/test_index_daily_turnover.py test/storage/test_storage_db.py test/tools/test_db_common.py -k 'index_daily_turnover or core_index or business_tables_include_index_daily_turnover' -v`
Expected: PASS.

- [ ] **Step 2: Run style/type checks proportionately**

Run: `uv run ruff check download storage test tools`
Expected: PASS.

- [ ] **Step 3: Self-review acceptance criteria**

Confirm pinned mapping, explicit provider fields, documented raw units, idempotent upsert, stable empty shape, db workflow registration, and offline tests.
