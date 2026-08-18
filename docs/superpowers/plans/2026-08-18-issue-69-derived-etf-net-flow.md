# Issue 69 Derived ETF Net-Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild and persist derived ETF net subscription/redemption metrics from persisted ETF share/size, ETF daily market data, ETF-index mapping diagnostics, and raw index turnover.

**Architecture:** Add a derived storage table plus narrow storage APIs, keep net-flow math pure and testable in `download/etf_net_flow.py`, and make `DownloadManager` an orchestration-only wrapper. No provider calls, no DAG schedule/task changes, and no fallback zeros.

**Tech Stack:** Python 3.11+, pandas, SQLAlchemy, `StrEnum`, dataclasses, pytest, Ruff, mypy, uv.

## Global Constraints

- Use `uv run` for Python commands; do not use bare `python` or `python3` for project tasks.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.
- Mock external providers; do not call live Tushare in tests.
- Raw data must already exist; `rebuild_etf_net_flow()` must not download raw inputs.
- Finite statuses and diagnostics must use enums rather than string types.
- Missing data produces diagnostics, skipped rows, or null ratios rather than fallback zeros.
- Upsert behavior must support PostgreSQL and SQLite conflict-update behavior.
- Add `etf_net_flow` to `tools/db_common.sh` so export, import, and clean workflows stay complete.

---

## Verification Plan

The main claim is that issue #69 can rebuild derived ETF net-flow rows from persisted raw data with correct share, price, and turnover units while preserving explicit diagnostics for missing inputs. The evidence path is focused offline tests: pure calculation tests prove unit math; fake-storage service tests prove lookback, skip/null diagnostics, and no provider calls; SQLite storage tests prove idempotent upsert; db script tests prove backup/import coverage. Final checks use focused pytest commands, Ruff format/check on touched files, `uv run mypy`, and a simplify review before completion.

---

## File Structure

- Create `storage/model/etf_net_flow.py`: SQLAlchemy model for the derived table.
- Modify `common/const.py`: add derived ETF net-flow column constants.
- Modify `storage/model/__init__.py`: export `ETFNetFlow` and `tb_name_etf_net_flow`.
- Modify `storage/__init__.py`: export `tb_name_etf_net_flow`.
- Modify `storage/storage_db.py`: add derived column mapping, share/index loaders, and `save_etf_net_flow()`.
- Create `download/etf_net_flow.py`: diagnostics enum/dataclasses, unit constants, pure math helpers, and rebuild service.
- Modify `download/download_manager.py`: add `DownloadManager.rebuild_etf_net_flow(...)` as an orchestration wrapper.
- Modify `tools/db_common.sh`: add `etf_net_flow` to `BUSINESS_TABLES`.
- Create `test/storage/model/test_etf_net_flow_model.py`.
- Modify `test/storage/test_storage_db.py`.
- Create `test/download/test_etf_net_flow.py`.
- Modify `test/download/test_download_manager.py`.
- Modify `test/tools/test_db_common.py`.

---

### Task 1: Derived Model, Constants, Exports, and DB Script

**Files:**
- Modify: `common/const.py`
- Create: `storage/model/etf_net_flow.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Modify: `tools/db_common.sh`
- Test: `test/storage/model/test_etf_net_flow_model.py`
- Test: `test/tools/test_db_common.py`

**Interfaces:**
- Produces constants: `COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE = "上一有效总份额"`, `COL_ETF_NET_SHARE_CHANGE = "净份额变动"`, `COL_ETF_ESTIMATED_TRADED_PRICE = "估算成交均价"`, `COL_ETF_NET_FLOW_AMOUNT = "净申赎金额"`, `COL_INDEX_TURNOVER_AMOUNT = "指数成交额"`, `COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO = "净申赎金额占指数成交额"`.
- Produces model: `tb_name_etf_net_flow = "etf_net_flow"` and `class ETFNetFlow(Base)`.

- [ ] **Step 1: Write failing model and DB script tests**

Create `test/storage/model/test_etf_net_flow_model.py`:

```python
from common.const import (
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
)
from storage.model import ETFNetFlow, tb_name_etf_net_flow


def test_etf_net_flow_table_name_primary_keys_and_columns():
    table = ETFNetFlow.__table__

    assert tb_name_etf_net_flow == "etf_net_flow"
    assert table.name == "etf_net_flow"
    assert list(table.primary_key.columns.keys()) == [COL_ETF_ID, COL_DATE]
    assert set(table.columns.keys()) == {
        COL_ETF_ID,
        COL_DATE,
        COL_ETF_TOTAL_SHARE,
        COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
        COL_ETF_NET_SHARE_CHANGE,
        COL_ETF_ESTIMATED_TRADED_PRICE,
        COL_ETF_NET_FLOW_AMOUNT,
        COL_INDEX_CODE,
        COL_INDEX_TURNOVER_AMOUNT,
        COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    }


def test_etf_net_flow_unit_comments_are_explicit():
    table = ETFNetFlow.__table__

    assert "原始" in table.c[COL_ETF_TOTAL_SHARE].comment
    assert "原始" in table.c[COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE].comment
    assert "元/份" in table.c[COL_ETF_ESTIMATED_TRADED_PRICE].comment
    assert "元" in table.c[COL_ETF_NET_FLOW_AMOUNT].comment
    assert "千元" in table.c[COL_INDEX_TURNOVER_AMOUNT].comment
```

Append to `test/tools/test_db_common.py`:

```python
def test_business_tables_include_etf_net_flow():
    assert "etf_net_flow" in _parse_business_tables()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest test/storage/model/test_etf_net_flow_model.py test/tools/test_db_common.py -k 'etf_net_flow or business_tables_cover_all_storage_models' -v
```

Expected: FAIL because `ETFNetFlow`, constants, and `etf_net_flow` script coverage do not exist.

- [ ] **Step 3: Implement constants, model, exports, and DB script coverage**

Add the constants to `common/const.py` near the ETF share/size constants. Create `storage/model/etf_net_flow.py`:

```python
from sqlalchemy import Column, Date, Float, String

from common.const import (
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
)

from .base import Base

tb_name_etf_net_flow = "etf_net_flow"


class ETFNetFlow(Base):
    __tablename__ = tb_name_etf_net_flow

    基金代码 = Column(COL_ETF_ID, String(6), primary_key=True, nullable=False, comment="ETF代码")
    日期 = Column(COL_DATE, Date, primary_key=True, nullable=False, comment="交易日期")
    总份额 = Column(COL_ETF_TOTAL_SHARE, Float, nullable=False, comment="Tushare etf_share_size total_share，原始单位")
    上一有效总份额 = Column(COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE, Float, nullable=False, comment="上一有效Tushare total_share，原始单位")
    净份额变动 = Column(COL_ETF_NET_SHARE_CHANGE, Float, nullable=False, comment="当日总份额 - 上一有效总份额，原始单位")
    估算成交均价 = Column(COL_ETF_ESTIMATED_TRADED_PRICE, Float, nullable=False, comment="ETF估算成交均价，元/份")
    净申赎金额 = Column(COL_ETF_NET_FLOW_AMOUNT, Float, nullable=False, comment="估算净申赎金额，元")
    指数代码 = Column(COL_INDEX_CODE, String(9), nullable=False, comment="映射指数Tushare代码")
    指数成交额 = Column(COL_INDEX_TURNOVER_AMOUNT, Float, nullable=True, comment="Tushare index_daily amount，成交额（千元）")
    净申赎金额占指数成交额 = Column(COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO, Float, nullable=True, comment="净申赎金额 / 指数成交额（同为元）")
```

Export `ETFNetFlow` and `tb_name_etf_net_flow` from `storage/model/__init__.py`; export `tb_name_etf_net_flow` from `storage/__init__.py`; add `etf_net_flow` near ETF raw tables in `tools/db_common.sh`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
uv run pytest test/storage/model/test_etf_net_flow_model.py test/tools/test_db_common.py -k 'etf_net_flow or business_tables_cover_all_storage_models' -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add common/const.py storage/model/etf_net_flow.py storage/model/__init__.py storage/__init__.py tools/db_common.sh test/storage/model/test_etf_net_flow_model.py test/tools/test_db_common.py
git commit -m "feat: add ETF net flow storage model"
```

---

### Task 2: Storage Loaders and Idempotent Upsert

**Files:**
- Modify: `storage/storage_db.py`
- Test: `test/storage/test_storage_db.py`

**Interfaces:**
- Consumes: `ETFNetFlow`, `ETFShareSize`, `IndexDailyTurnover`, `tb_name_etf_net_flow`, `tb_name_etf_share_size`, `tb_name_index_daily_turnover`.
- Produces: `StorageDb.load_etf_share_size(etf_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None, include_prior_effective: bool = False) -> pd.DataFrame`, `StorageDb.load_index_daily_turnover(ts_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame`, and `StorageDb.save_etf_net_flow(df: pd.DataFrame) -> bool`.

- [ ] **Step 1: Write failing storage tests**

Append tests near existing ETF share/size and index turnover storage tests in `test/storage/test_storage_db.py`:

```python
def test_load_etf_share_size_includes_prior_effective_row_before_start_date(self, sqlite_storage):
    db = sqlite_storage
    assert db.save_etf_share_size(pd.DataFrame([
        {COL_ETF_ID: "510300", COL_DATE: "2024-01-02", COL_CLOSE: 3.1, COL_NAV: 3.0, COL_ETF_TOTAL_SHARE: 1000.0, COL_ETF_TOTAL_SIZE: 3000.0},
        {COL_ETF_ID: "510300", COL_DATE: "2024-01-05", COL_CLOSE: 3.2, COL_NAV: 3.1, COL_ETF_TOTAL_SHARE: 1005.0, COL_ETF_TOTAL_SIZE: 3216.0},
        {COL_ETF_ID: "510300", COL_DATE: "2024-01-08", COL_CLOSE: 3.3, COL_NAV: 3.2, COL_ETF_TOTAL_SHARE: 1007.0, COL_ETF_TOTAL_SIZE: 3323.1},
    ])) is True

    result = db.load_etf_share_size("510300", "2024-01-05", "2024-01-08", include_prior_effective=True)

    assert result[COL_DATE].astype(str).tolist() == ["2024-01-02", "2024-01-05", "2024-01-08"]


def test_load_etf_share_size_without_prior_only_returns_requested_range(self, sqlite_storage):
    db = sqlite_storage
    assert db.save_etf_share_size(pd.DataFrame([
        {COL_ETF_ID: "510300", COL_DATE: "2024-01-02", COL_CLOSE: 3.1, COL_NAV: 3.0, COL_ETF_TOTAL_SHARE: 1000.0, COL_ETF_TOTAL_SIZE: 3000.0},
        {COL_ETF_ID: "510300", COL_DATE: "2024-01-05", COL_CLOSE: 3.2, COL_NAV: 3.1, COL_ETF_TOTAL_SHARE: 1005.0, COL_ETF_TOTAL_SIZE: 3216.0},
    ])) is True

    result = db.load_etf_share_size("510300", "2024-01-05", "2024-01-08")

    assert result[COL_DATE].astype(str).tolist() == ["2024-01-05"]


def test_load_index_daily_turnover_filters_by_code_and_date_range(self, sqlite_storage):
    db = sqlite_storage
    assert db.save_index_daily_turnover(pd.DataFrame([
        {COL_INDEX_CODE: "000300.SH", COL_DATE: "2024-01-05", COL_CLOSE: 3500.0, COL_AMOUNT: 10000.0},
        {COL_INDEX_CODE: "000905.SH", COL_DATE: "2024-01-05", COL_CLOSE: 5500.0, COL_AMOUNT: 20000.0},
        {COL_INDEX_CODE: "000300.SH", COL_DATE: "2024-01-08", COL_CLOSE: 3510.0, COL_AMOUNT: 12000.0},
    ])) is True

    result = db.load_index_daily_turnover("000300.SH", "2024-01-05", "2024-01-05")

    assert result[[COL_INDEX_CODE, COL_DATE, COL_AMOUNT]].astype({COL_DATE: str}).to_dict("records") == [
        {COL_INDEX_CODE: "000300.SH", COL_DATE: "2024-01-05", COL_AMOUNT: 10000.0}
    ]


def test_save_etf_net_flow_is_idempotent_for_same_primary_key(self, sqlite_storage):
    db = sqlite_storage
    initial_df = pd.DataFrame([{COL_ETF_ID: "510300", COL_DATE: "2024-01-05", COL_ETF_TOTAL_SHARE: 1005.0, COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE: 1000.0, COL_ETF_NET_SHARE_CHANGE: 5.0, COL_ETF_ESTIMATED_TRADED_PRICE: 5.0, COL_ETF_NET_FLOW_AMOUNT: 250000.0, COL_INDEX_CODE: "000300.SH", COL_INDEX_TURNOVER_AMOUNT: 10000.0, COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO: 0.025}])
    updated_df = initial_df.copy()
    updated_df.loc[0, COL_ETF_NET_FLOW_AMOUNT] = 300000.0
    updated_df.loc[0, COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO] = 0.03

    assert db.save_etf_net_flow(initial_df) is True
    assert db.save_etf_net_flow(updated_df) is True

    with db.engine.connect() as conn:
        rows = conn.execute(text(f'SELECT * FROM etf_net_flow WHERE "{COL_ETF_ID}" = "510300"')).mappings().all()
    assert len(rows) == 1
    assert rows[0][COL_ETF_NET_FLOW_AMOUNT] == 300000.0
    assert rows[0][COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO] == 0.03


def test_save_etf_net_flow_rejects_missing_required_columns(self, sqlite_storage):
    assert sqlite_storage.save_etf_net_flow(pd.DataFrame([{COL_ETF_ID: "510300"}])) is False
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest test/storage/test_storage_db.py -k 'etf_net_flow or load_etf_share_size or load_index_daily_turnover' -v
```

Expected: FAIL because the loaders and `save_etf_net_flow()` do not exist.

- [ ] **Step 3: Implement storage methods**

Add `ETFNetFlow` imports and a `COL_MAP_ETF_NET_FLOW` mapping in `storage/storage_db.py`. Implement `load_etf_share_size()` using existing date-range query helpers, and when `include_prior_effective=True`, prepend the latest row strictly before `start_date`. Implement `load_index_daily_turnover()` using the same query helper pattern. Implement `save_etf_net_flow()` by mirroring the PostgreSQL/SQLite conflict-update pattern used by `save_etf_share_size()`.

- [ ] **Step 4: Verify GREEN**

```bash
uv run pytest test/storage/test_storage_db.py -k 'etf_net_flow or load_etf_share_size or load_index_daily_turnover' -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add storage/storage_db.py test/storage/test_storage_db.py
git commit -m "feat: add ETF net flow storage persistence"
```

---

### Task 3: Pure Calculation Helpers and Diagnostics

**Files:**
- Create: `download/etf_net_flow.py`
- Test: `test/download/test_etf_net_flow.py`

**Interfaces:**
- Produces `ETFNetFlowDiagnosticReason(StrEnum)`, `ETFNetFlowDiagnostic`, `ETFNetFlowRebuildResult`, `ETF_SHARE_SIZE_UNIT_TO_SHARES = 10000.0`, `ETF_DAILY_AMOUNT_UNIT_TO_YUAN = 1000.0`, `ETF_DAILY_VOLUME_UNIT_TO_SHARES = 100.0`, `INDEX_TURNOVER_UNIT_TO_YUAN = 1000.0`.
- Produces pure helpers: `calculate_net_share_change(current_total_share, previous_total_share) -> float | None`, `estimate_etf_traded_price(amount, volume, close) -> float | None`, `calculate_net_flow_amount(net_share_change, estimated_price) -> float`, and `calculate_flow_turnover_ratio(net_flow_amount, index_turnover) -> float | None`.

- [ ] **Step 1: Write failing pure calculation tests**

Create `test/download/test_etf_net_flow.py` with tests for normal calculations, negative redemption, close fallback, missing price support, missing turnover, and zero turnover.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest test/download/test_etf_net_flow.py -k 'calculate or traded_price or turnover_ratio' -v
```

Expected: FAIL because `download.etf_net_flow` does not exist.

- [ ] **Step 3: Implement pure helpers and diagnostics**

Create `download/etf_net_flow.py` with enum/dataclasses and pure helpers. `estimate_etf_traded_price()` must compute `amount * 1000 / (volume * 100)` when amount and volume are positive; otherwise return close when close is positive; otherwise return `None`. `calculate_net_flow_amount()` must compute `net_share_change * 10000 * estimated_price`. `calculate_flow_turnover_ratio()` must return `None` when turnover is missing or zero and otherwise compute `net_flow_amount / (index_turnover * 1000)`.

- [ ] **Step 4: Verify GREEN**

```bash
uv run pytest test/download/test_etf_net_flow.py -k 'calculate or traded_price or turnover_ratio' -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add download/etf_net_flow.py test/download/test_etf_net_flow.py
git commit -m "feat: add ETF net flow calculations"
```

---

### Task 4: Rebuild Service

**Files:**
- Modify: `download/etf_net_flow.py`
- Test: `test/download/test_etf_net_flow.py`

**Interfaces:**
- Produces `rebuild_etf_net_flow(*, storage: Any, etf_code: str, start_date: str, end_date: str) -> ETFNetFlowRebuildResult`.
- Consumes `prepare_etf_flow_index_context(etf_code)`, storage loaders from Task 2, pure helpers from Task 3, and constants from Task 1.

- [ ] **Step 1: Write failing rebuild service tests**

Extend `test/download/test_etf_net_flow.py` with a fake storage object and tests covering: normal saved rows, prior effective share lookback, missing prior share, missing mapping without loader calls, missing ETF daily support, missing index turnover null ratio, zero index turnover null ratio, and close-price fallback.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest test/download/test_etf_net_flow.py -k 'rebuild_etf_net_flow' -v
```

Expected: FAIL because `rebuild_etf_net_flow()` does not exist or lacks required behavior.

- [ ] **Step 3: Implement rebuild service**

Implement `rebuild_etf_net_flow()` so mapping failures return `saved_rows=0` without raw loader calls. For mapped ETFs, load share rows with `include_prior_effective=True`, ETF daily rows, and index turnover rows. Build one derived row per requested share/size date when prior share and price support exist. Missing or zero turnover should still save the flow row with a null ratio and an explicit diagnostic. Persist only when at least one row is generated.

- [ ] **Step 4: Verify GREEN**

```bash
uv run pytest test/download/test_etf_net_flow.py -k 'rebuild_etf_net_flow' -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add download/etf_net_flow.py test/download/test_etf_net_flow.py
git commit -m "feat: rebuild ETF net flow metrics"
```

---

### Task 5: DownloadManager Orchestration

**Files:**
- Modify: `download/download_manager.py`
- Test: `test/download/test_download_manager.py`

**Interfaces:**
- Produces `DownloadManager.rebuild_etf_net_flow(self, etf_code: str, start_date: str, end_date: str) -> ETFNetFlowRebuildResult`.
- Consumes `download.etf_net_flow.rebuild_etf_net_flow` and `get_storage()`.

- [ ] **Step 1: Write failing manager tests**

Add tests in `test/download/test_download_manager.py` proving the manager delegates to the service with storage, returns the typed result, and does not call raw downloader methods.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest test/download/test_download_manager.py -k 'rebuild_etf_net_flow' -v
```

Expected: FAIL because manager method does not exist.

- [ ] **Step 3: Implement manager method**

Import the service function and add `DownloadManager.rebuild_etf_net_flow()` that returns `rebuild_etf_net_flow(storage=get_storage(), etf_code=etf_code, start_date=start_date, end_date=end_date)`. Do not call `self.downloader` or raw download methods.

- [ ] **Step 4: Verify GREEN**

```bash
uv run pytest test/download/test_download_manager.py -k 'rebuild_etf_net_flow' -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add download/download_manager.py test/download/test_download_manager.py
git commit -m "feat: expose ETF net flow rebuild manager"
```

---

### Task 6: Integration Verification and Simplify Review

**Files:**
- Review all touched implementation and test files.

**Interfaces:**
- Consumes all prior task outputs.
- Produces final verification evidence for issue #69.

- [ ] **Step 1: Run focused verification**

```bash
uv run pytest test/download/test_etf_net_flow.py test/download/test_download_manager.py -k 'etf_net_flow or rebuild_etf_net_flow' -v
uv run pytest test/storage/model/test_etf_net_flow_model.py test/storage/test_storage_db.py test/tools/test_db_common.py -k 'etf_net_flow or load_etf_share_size or load_index_daily_turnover or business_tables_include_etf_net_flow' -v
```

- [ ] **Step 2: Run formatting, linting, and type checks**

```bash
uv run ruff format common/const.py download/etf_net_flow.py download/download_manager.py storage/__init__.py storage/model/__init__.py storage/model/etf_net_flow.py storage/storage_db.py test/download/test_etf_net_flow.py test/download/test_download_manager.py test/storage/model/test_etf_net_flow_model.py test/storage/test_storage_db.py test/tools/test_db_common.py
uv run ruff check common/const.py download/etf_net_flow.py download/download_manager.py storage/__init__.py storage/model/__init__.py storage/model/etf_net_flow.py storage/storage_db.py test/download/test_etf_net_flow.py test/download/test_download_manager.py test/storage/model/test_etf_net_flow_model.py test/storage/test_storage_db.py test/tools/test_db_common.py
uv run mypy
```

- [ ] **Step 3: Run simplify review**

Invoke `simplify` and apply only targeted simplifications that preserve issue scope and verified behavior.

- [ ] **Step 4: Re-run affected verification after simplification**

Re-run the focused pytest and Ruff commands if simplify changes files.

- [ ] **Step 5: Commit verification cleanup if needed**

```bash
git add <changed-files>
git commit -m "refactor: simplify ETF net flow implementation"
```
