# Forecast Ingestion Operations Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add focused evidence that the rolling forecast-ingestion DAG and explicit backfill command consume the shared forecast-download result contract reliably, preserve persistence idempotency, and do not affect forecast SSF MA20 synchronization.

**Architecture:** Add a test-only cross-workflow module that supplies equivalent mocked `ForecastDownloadResult` values to each public workflow entry point and asserts their common aggregation semantics plus intentionally different failure behavior. Extend the existing SQLite-backed forecast storage test with a repeat-save assertion; retain the independent SSF synchronization suite as a regression guard. Production source files remain unchanged.

**Tech Stack:** Python 3.11+, pytest, `unittest.mock`, existing fake-Airflow test pattern, pandas, SQLAlchemy SQLite, `DownloadManager`, `ForecastDownloadResult`.

## Global Constraints

- Use `uv run` for every Python command in this repository.
- Modify tests only; do not change `DownloadManager`, forecast provider calls, normalization, storage schema, persistence implementation, DAG schedules, dependencies, retries, task boundaries, SLA, or forecast SSF MA20 synchronization code.
- Mock `DownloadManager.download_forecast`; do not call TuShare, storage, or an Airflow scheduler in workflow tests.
- A forecast result succeeds only when `ForecastDownloadResult.saved` is `True`.
- A successful result with zero `source_rows` or zero `a_share_rows` is a valid empty result.
- The rolling task processes a 30-day China-local natural-date range and fails at the first unsuccessful result; the explicit backfill processes every selected natural date and returns `1` when any result failed.
- Validate repeated persistence with the existing SQLite `StorageDb` fixture pattern; do not add a PostgreSQL container test.
- Preserve the existing SSF synchronization DAG’s independent schedule and service contract; do not introduce a DAG dependency.

---

## File Structure

- Create `test/forecast/test_forecast_ingestion_operations.py`: test-only Airflow doubles and cross-workflow contract scenarios that invoke `dags/download_forecast_daily.py` and `tools/backfill_forecast.py` through their public callable entry points.
- Modify `test/storage/test_forecast_storage.py`: save an identical normalized forecast DataFrame twice through `StorageDb.save_forecasts` and query the `forecasts` table to prove primary-key upsert idempotency.
- Do not modify `dags/download_forecast_daily.py`, `tools/backfill_forecast.py`, `storage/storage_db.py`, or `dags/forecast_ssf_ma20_sync.py`.

### Task 1: Cross-Workflow Result Contract Tests

**Files:**
- Create: `test/forecast/test_forecast_ingestion_operations.py`
- Verify: `dags/download_forecast_daily.py:22-55`
- Verify: `tools/backfill_forecast.py:28-101`

**Interfaces:**
- Consumes: `DownloadManager.download_forecast(ann_date: str) -> ForecastDownloadResult` where `ForecastDownloadResult(announcement_date: str, source_rows: int, a_share_rows: int, saved: bool)`.
- Consumes: `download_forecast_daily.download_forecast(**context: Any) -> dict[str, Any]` and `backfill_forecast.main(argv: list[str] | None = None) -> int`.
- Produces: regression evidence that both workflows interpret saved, empty, failed, source-row, and A-share-row result fields consistently while retaining their specified failure policies.

- [ ] **Step 1: Create shared test setup and successful-result contract test**

Create `test/forecast/test_forecast_ingestion_operations.py`. Add the repository root and `dags/` directory constants, minimal fake `DAG` and `PythonOperator` classes, and a `daily_module` fixture that installs fake `airflow`, `airflow.operators`, and `airflow.operators.python` modules before importing `download_forecast_daily`.

```python
import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from download.download_manager import ForecastDownloadResult
from tools import backfill_forecast

ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = ROOT / "dags"


class FakeDAG:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class FakePythonOperator:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


@pytest.fixture()
def daily_module(monkeypatch):
    monkeypatch.syspath_prepend(str(DAGS_DIR))
    monkeypatch.setenv("FROG_PROJECT_ROOT", str(ROOT))
    airflow = types.ModuleType("airflow")
    airflow.DAG = FakeDAG
    airflow_operators = types.ModuleType("airflow.operators")
    airflow_python = types.ModuleType("airflow.operators.python")
    airflow_python.PythonOperator = FakePythonOperator
    monkeypatch.setitem(sys.modules, "airflow", airflow)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_python)
    sys.modules.pop("download_forecast_daily", None)
    module = importlib.import_module("download_forecast_daily")
    yield module
    sys.modules.pop("download_forecast_daily", None)


def local_window_context():
    return {"data_interval_end": datetime(2026, 8, 10, 10, tzinfo=timezone.utc)}


def test_workflows_aggregate_saved_and_empty_results_consistently(monkeypatch, daily_module, capsys):
    rolling_manager = MagicMock()
    rolling_manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260712", 2, 1, True),
        ForecastDownloadResult("20260713", 0, 0, True),
        *[ForecastDownloadResult(f"date-{offset}", 1, 1, True) for offset in range(28)],
    ]
    monkeypatch.setattr(daily_module, "DownloadManager", lambda: rolling_manager)

    rolling_summary = daily_module.download_forecast(**local_window_context())

    backfill_manager = MagicMock()
    backfill_manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260801", 2, 1, True),
        ForecastDownloadResult("20260802", 0, 0, True),
        ForecastDownloadResult("20260803", 1, 1, True),
    ]
    monkeypatch.setattr(backfill_forecast, "parse_config", lambda: None)
    monkeypatch.setattr(backfill_forecast, "DownloadManager", lambda: backfill_manager)

    assert backfill_forecast.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 0
    assert rolling_summary["successful_dates"] == 30
    assert rolling_summary["empty_dates"] == 1
    assert rolling_summary["failed_dates"] == 0
    assert rolling_summary["source_rows"] == 30
    assert rolling_summary["a_share_rows"] == 29
    assert "requested_dates=3 successful_dates=3 empty_dates=1 failed_dates=0 source_rows=3 a_share_rows=2" in capsys.readouterr().out
```

Use `FakeAirflowDateTime` with an `in_timezone` method if the plain `datetime` context cannot satisfy the DAG helper; it must return `self.astimezone(tz)` like the existing DAG test. Keep the final 28 rolling outcomes successful with `source_rows=1` and `a_share_rows=1`, so the complete rolling sequence contains 30 results.

- [ ] **Step 2: Run the new success-contract test**

Run: `uv run pytest test/forecast/test_forecast_ingestion_operations.py::test_workflows_aggregate_saved_and_empty_results_consistently -v`

Expected: PASS. Issue #52 is verification-only, so the new test documents
behavior already implemented by issues #50 and #51 rather than requiring a
production change.

- [ ] **Step 3: Complete the success-contract assertions for date ordering and aggregate semantics**

Finish the test created in Step 1 with exact manager-call assertions. The daily workflow must call the first and last announcement dates in its local 30-day window. The explicit backfill must call each supplied date, inclusively and in ascending order.

```python
    assert rolling_manager.download_forecast.call_count == 30
    assert rolling_manager.download_forecast.call_args_list[0] == call(ann_date="20260712")
    assert rolling_manager.download_forecast.call_args_list[-1] == call(ann_date="20260810")
    assert backfill_manager.download_forecast.call_args_list == [
        call(ann_date="20260801"),
        call(ann_date="20260802"),
        call(ann_date="20260803"),
    ]
```

The backfill stdout assertion must contain exactly its expected six summary fields in command order and must not contain `failed_announcement_dates=` for all-successful results.

- [ ] **Step 4: Run the successful-result contract test**

Run: `uv run pytest test/forecast/test_forecast_ingestion_operations.py::test_workflows_aggregate_saved_and_empty_results_consistently -v`

Expected: PASS, proving both entry points treat `saved=True`, valid empty rows, totals, and ascending natural dates according to the contract.

- [ ] **Step 5: Add failing-result tests for the intentionally different operational policies**

Add two tests to the same module. The daily task receives a successful result followed by an unsuccessful result and must raise on the second date without requesting a third. The backfill command receives the same pattern plus a third successful empty result and must process all three dates, return `1`, and report the failed date.

```python
def test_daily_workflow_stops_on_first_unsaved_result(monkeypatch, daily_module):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260712", 1, 1, True),
        ForecastDownloadResult("20260713", 0, 0, False),
    ]
    monkeypatch.setattr(daily_module, "DownloadManager", lambda: manager)

    with pytest.raises(RuntimeError, match="20260713"):
        daily_module.download_forecast(**local_window_context())

    assert manager.download_forecast.call_count == 2


def test_backfill_workflow_continues_and_reports_unsaved_result(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        ForecastDownloadResult("20260801", 1, 1, True),
        ForecastDownloadResult("20260802", 0, 0, False),
        ForecastDownloadResult("20260803", 3, 0, True),
    ]
    monkeypatch.setattr(backfill_forecast, "parse_config", lambda: None)
    monkeypatch.setattr(backfill_forecast, "DownloadManager", lambda: manager)

    assert backfill_forecast.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 1
    assert manager.download_forecast.call_count == 3
    assert capsys.readouterr().out == (
        "requested_dates=3 successful_dates=2 empty_dates=1 failed_dates=1 "
        "source_rows=4 a_share_rows=1\n"
        "failed_announcement_dates=20260802\n"
    )
```

- [ ] **Step 6: Run the failure-policy tests to confirm they pass**

Run: `uv run pytest test/forecast/test_forecast_ingestion_operations.py -v`

Expected: PASS. The daily test proves fail-fast Airflow behavior. The backfill test proves complete-range reporting and exit code `1` after a failed date.

- [ ] **Step 7: Format, lint, and commit the cross-workflow tests**

Run: `uv run ruff format test/forecast/test_forecast_ingestion_operations.py && uv run ruff check test/forecast/test_forecast_ingestion_operations.py && uv run pytest test/forecast/test_forecast_ingestion_operations.py -v`

Expected: all commands exit `0`.

```bash
git add test/forecast/test_forecast_ingestion_operations.py
git commit -m "test: verify forecast ingestion operations"
```

### Task 2: Forecast Persistence Idempotency Test

**Files:**
- Modify: `test/storage/test_forecast_storage.py`
- Verify: `storage/storage_db.py:1650-1693`
- Verify: `storage/model/forecast.py:17-25`

**Interfaces:**
- Consumes: `StorageDb.save_forecasts(df: pd.DataFrame) -> bool` and the `forecasts` primary key of `("股票代码", "公告日期", "截止日期")`.
- Produces: a SQLite-backed regression test proving that repeated normalized forecast records retain one persisted row and return success on both writes.

- [ ] **Step 1: Write the idempotency regression test**

Append this test to `test/storage/test_forecast_storage.py`. Follow the existing `StorageDb.__new__`, SQLite engine, `Session = None`, `Base.metadata.create_all`, and `ensure_forecasts_table()` setup exactly.

```python
def test_save_forecasts_is_idempotent_for_repeated_normalized_rows(tmp_path):
    db = StorageDb.__new__(StorageDb)
    db.engine = create_engine(f"sqlite:///{tmp_path}/forecast.db")
    db.Session = None
    Base.metadata.create_all(db.engine)
    db.ensure_forecasts_table()
    forecast = pd.DataFrame(
        {
            "股票代码": ["600001.SH"],
            "公告日期": ["2025-01-05"],
            "截止日期": ["2024-12-31"],
            "预告类型": ["预增"],
            "增长下限": [50.0],
            "增长上限": [70.0],
        }
    )

    assert db.save_forecasts(forecast) is True
    assert db.save_forecasts(forecast) is True

    with db.engine.connect() as conn:
        rows = conn.execute(text('SELECT "股票代码", "公告日期", "截止日期", "增长下限" FROM forecasts')).mappings().all()

    assert len(rows) == 1
    assert rows[0]["股票代码"] == "600001"
    assert rows[0]["增长下限"] == 50.0
```

The incoming `.SH` identifier intentionally verifies that persistence idempotency follows the production normalization path before primary-key conflict resolution.

- [ ] **Step 2: Run the focused idempotency test to confirm the expected initial result**

Run: `uv run pytest test/storage/test_forecast_storage.py::test_save_forecasts_is_idempotent_for_repeated_normalized_rows -v`

Expected: PASS without any production edit, because `save_forecasts` already performs a SQLite upsert keyed by stock code, announcement date, and end date. If it fails, stop and investigate the existing persistence behavior before changing production code; issue #52 does not authorize a behavioral change.

- [ ] **Step 3: Run all forecast storage coverage and commit the regression test**

Run: `uv run ruff format test/storage/test_forecast_storage.py && uv run ruff check test/storage/test_forecast_storage.py && uv run pytest test/storage/test_forecast_storage.py -v`

Expected: all commands exit `0`.

```bash
git add test/storage/test_forecast_storage.py
git commit -m "test: cover forecast persistence idempotency"
```

### Task 3: Focused Regression Verification

**Files:**
- Verify: `test/dags/test_download_forecast_daily.py`
- Verify: `test/tools/test_backfill_forecast.py`
- Verify: `test/storage/test_forecast_storage.py`
- Verify: `test/dags/test_forecast_ssf_ma20_sync.py`
- Verify: `test/forecast/test_forecast_ingestion_operations.py`

**Interfaces:**
- Consumes: the public rolling task, backfill command, SQLite forecast persistence, and independent forecast SSF synchronization test contracts verified by Tasks 1 and 2.
- Produces: final focused evidence that issue #52 added coverage only and did not regress predecessor workflows or SSF synchronization.

- [ ] **Step 1: Run all focused forecast-operation and SSF synchronization tests**

Run:

```bash
uv run pytest \
  test/forecast/test_forecast_ingestion_operations.py \
  test/dags/test_download_forecast_daily.py \
  test/tools/test_backfill_forecast.py \
  test/storage/test_forecast_storage.py \
  test/dags/test_forecast_ssf_ma20_sync.py -v
```

Expected: PASS. In particular, `test_forecast_ssf_ma20_sync.py` continues to verify schedule `"5 15 * * *"`, one `sync_forecast_ssf_targets` task, non-trading-day skip behavior, China-local `as_of_date`, JSON success return, and service-failure propagation.

- [ ] **Step 2: Run repository formatting and lint verification for every changed test**

Run:

```bash
uv run ruff format --check \
  test/forecast/test_forecast_ingestion_operations.py \
  test/storage/test_forecast_storage.py
uv run ruff check \
  test/forecast/test_forecast_ingestion_operations.py \
  test/storage/test_forecast_storage.py
```

Expected: all commands exit `0` with no formatting or lint diagnostics.

- [ ] **Step 3: Inspect the final diff before closing the issue**

Run: `git status --short && git diff HEAD~2..HEAD -- test/forecast/test_forecast_ingestion_operations.py test/storage/test_forecast_storage.py`

Expected: only the intended test additions are present in the two issue commits; production forecast ingestion, storage, and SSF synchronization source files are unchanged. Do not stage or alter unrelated untracked files already present in the worktree.

## Plan Self-Review

- **Spec coverage:** Task 1 covers the shared structured result contract, local 30-day rolling range, explicit inclusive backfill range, aggregate counts, valid empty results, and each workflow’s distinct failed-date behavior. Task 2 covers repeated-date persistence idempotency. Task 3 executes the existing independent SSF synchronization guard and all affected predecessor tests.
- **No placeholders:** Every action names concrete files, public interfaces, test values, expected commands, and pass/fail outcomes. No production implementation step is required because the approved specification is verification-only.
- **Type consistency:** All workflow fixtures construct `ForecastDownloadResult(announcement_date, source_rows, a_share_rows, saved)` and call the existing `download_forecast(**context)` and `main(argv)` interfaces. Storage assertions use the existing `StorageDb.save_forecasts(pd.DataFrame) -> bool` method and the documented `forecasts` primary key.
