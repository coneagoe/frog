# Forecast Snapshot Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and operate immutable, validated forecast snapshots for explicit reporting and announcement-date ranges, without changing the existing mutable forecast-refresh workflow.

**Architecture:** A dedicated `ForecastSnapshotService` calls the raw TuShare forecast boundary, normalizes and validates each provider response, and transitions a storage-owned snapshot run from `running` to `completed` or `failed`. Two immutable SQLAlchemy models preserve attempts and source ordering; storage acquisition enforces idempotent completed reuse and one active equivalent range. A CLI and manual DAG invoke the same service and only expose JSON-serializable run summaries.

**Tech Stack:** Python 3.12, pandas, SQLAlchemy, PostgreSQL/TimescaleDB, SQLite unit tests, pytest, Airflow, TuShare provider wrapper, Ruff, mypy, Docker Compose test database.

## Global Constraints

- All public dates use exact ISO `YYYY-MM-DD`; provider calls receive `YYYYMMDD`.
- Use `ForecastSnapshotStatus` as a Python `StrEnum` and `forecast_snapshot_status` as the named PostgreSQL enum.
- Snapshot records retain every normalized provider row, including non-A-share rows, in zero-based order within each requested provider response.
- Empty DataFrames are valid covered announcement dates; required-schema, provider, date, numeric, normalization, and persistence failures fail the attempt.
- The range identity is `(report_end_date, announcement_start_date, announcement_end_date)`.
- A completed equivalent range returns stored output without a provider call; an active equivalent range cannot start a second attempt; failed history creates the next attempt.
- Failed snapshot runs and records are never returned by completed-snapshot lookup.
- Do not modify `DownloadManager.download_forecast`, `tools/backfill_forecast.py`, `dags/download_forecast_daily.py`, or mutable `forecasts` behavior.
- Add every new business table and enum to `tools/db_common.sh` export/import governance.
- PostgreSQL-dependent tests run through `tools/run_tests.sh`; use `uv run` for all other Python commands.

---

## File Structure

- Create: `storage/model/forecast_snapshot.py` - snapshot run and immutable provider-record SQLAlchemy models.
- Modify: `storage/model/__init__.py` - re-export snapshot models and table names.
- Modify: `storage/domain_enums.py` - add `ForecastSnapshotStatus`.
- Modify: `storage/enum_migration.py` - govern the snapshot status enum and upgrade legacy string status columns.
- Modify: `storage/storage_db.py` - create snapshot tables and provide atomic range acquisition, persistence, finalization, failure, and completed-only lookup methods.
- Modify: `tools/db_common.sh` - add snapshot tables and status enum to business export/import governance.
- Create: `forecast_snapshot/__init__.py` - package marker and public service exports.
- Create: `forecast_snapshot/service.py` - request/result dataclasses, range validation, raw-provider normalization, per-date ingestion, lifecycle management, and duplicate metrics.
- Create: `test/forecast_snapshot/test_service.py` - mocked-provider service behavior tests.
- Create: `test/storage/test_forecast_snapshot_storage.py` - SQLite storage lifecycle and immutability tests.
- Create: `test/storage/test_forecast_snapshot_enum_migration.py` - PostgreSQL enum, legacy conversion, partial-index, rollback, and concurrency contract tests.
- Create: `tools/create_forecast_snapshot.py` - explicit operator command.
- Create: `test/tools/test_create_forecast_snapshot.py` - CLI validation, output, and failure-status tests.
- Create: `dags/create_forecast_snapshot.py` - manually triggered Airflow entry point.
- Create: `test/dags/test_create_forecast_snapshot.py` - mocked-Airflow DAG callable tests.
- Modify: `docs/airflow.md` - document manual snapshot DAG configuration only if it already documents manual DAG operation.
- Modify: `docs/config.md` - document snapshot command only if it already documents operator command usage.

## Task 1: Define Snapshot Domain Models and Status Governance

**Files:**
- Create: `storage/model/forecast_snapshot.py`
- Modify: `storage/domain_enums.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/enum_migration.py`
- Modify: `tools/db_common.sh`
- Test: `test/storage/test_forecast_snapshot_storage.py`
- Test: `test/storage/test_forecast_snapshot_enum_migration.py`

**Interfaces:**
- Produces: `ForecastSnapshotStatus` with exact values `running`, `completed`, and `failed`.
- Produces: `ForecastSnapshotRun` with `id`, range identity fields, `attempt`, `status`, count fields, lifecycle timestamps, and `failure_detail`.
- Produces: `ForecastSnapshotRecord` with `run_id`, provider fields, normalized dates and numeric fields, and per-announcement-date `source_order`.
- Produces: table names `forecast_snapshot_runs`, `forecast_snapshot_records`, and PostgreSQL enum `forecast_snapshot_status`.

- [ ] **Step 1: Write the failing SQLite model tests**

Add `test/storage/test_forecast_snapshot_storage.py` with the model-level expectations:

```python
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from storage.model import Base, ForecastSnapshotRecord, ForecastSnapshotRun
from storage.domain_enums import ForecastSnapshotStatus


def test_snapshot_record_source_order_is_unique_within_a_provider_response():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        run_id = connection.execute(
            ForecastSnapshotRun.__table__.insert().values(
                report_end_date=date(2026, 6, 30),
                announcement_start_date=date(2026, 7, 1),
                announcement_end_date=date(2026, 7, 1),
                attempt=1,
                status=ForecastSnapshotStatus.RUNNING.value,
            )
        ).inserted_primary_key[0]
        row = {
            "run_id": run_id,
            "source_order": 0,
            "ts_code": "600001.SH",
            "announcement_date": date(2026, 7, 1),
            "report_end_date": date(2026, 6, 30),
            "forecast_type": "预增",
        }
        connection.execute(ForecastSnapshotRecord.__table__.insert().values(row))
        with pytest.raises(IntegrityError):
            connection.execute(ForecastSnapshotRecord.__table__.insert().values(row))
```

- [ ] **Step 2: Run the model test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_record_source_order_is_unique_within_a_provider_response -v`

Expected: FAIL during import because the snapshot models and status enum do not exist.

- [ ] **Step 3: Add the status enum and models**

In `storage/domain_enums.py`, add:

```python
class ForecastSnapshotStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
```

Create `storage/model/forecast_snapshot.py` following the existing `_value_enum` pattern. Define a partial unique index named `uq_forecast_snapshot_running_range` over the three range columns, with `sqlite_where=text("status = 'running'")` and `postgresql_where=text("status = 'running'")`. Define a full unique constraint named `uq_forecast_snapshot_attempt` over range identity plus `attempt`; define `uq_forecast_snapshot_record_source_order` over `(run_id, announcement_date, source_order)`.

Use these essential columns:

```python
class ForecastSnapshotRun(Base):
    id: Mapped[int]
    report_end_date: Mapped[date]
    announcement_start_date: Mapped[date]
    announcement_end_date: Mapped[date]
    attempt: Mapped[int]
    status: Mapped[str]
    requested_date_count: Mapped[int]
    covered_date_count: Mapped[int]
    source_row_count: Mapped[int]
    record_count: Mapped[int]
    duplicate_record_count: Mapped[int]
    same_day_conflict_count: Mapped[int]
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    failed_at: Mapped[datetime | None]
    failure_detail: Mapped[str | None]
```

`ForecastSnapshotRecord` uses `Integer` primary key, a `ForeignKey("forecast_snapshot_runs.id")`, `String(32)` `ts_code`, `Date` provider announcement/report dates, `String(20)` provider forecast type, nullable `Float` growth bounds, and `Integer` source order. Do not add mutable `updated_at` fields or update helpers.

Export both models and both table constants from `storage/model/__init__.py`.

- [ ] **Step 4: Add storage enum governance and export/import registration**

Extend `storage/enum_migration.py` to import `ForecastSnapshotStatus` and `ForecastSnapshotRun`, add a `StorageEnumGroup`:

```python
StorageEnumGroup(
    "forecast_snapshot_status",
    _labels(ForecastSnapshotStatus),
    (_column("forecast_snapshot_runs", "status", "VARCHAR(16)"),),
)
```

Include `ForecastSnapshotRun.__table__` in `_GOVERNED_TABLES`, so PostgreSQL startup leaves creation and conversion to the enum adapter. Add both snapshot table names to `BUSINESS_TABLES`, add `forecast_snapshot_status` to `BUSINESS_ENUM_TYPES`, and add its `forecast_snapshot_runs` dependency to the `business_enum_is_needed` case in `tools/db_common.sh`.

- [ ] **Step 5: Run the SQLite model test to verify it passes**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_record_source_order_is_unique_within_a_provider_response -v`

Expected: PASS. The duplicate source-order insertion raises `IntegrityError`.

- [ ] **Step 6: Write the failing PostgreSQL enum migration test**

Create `test/storage/test_forecast_snapshot_enum_migration.py` using the existing PostgreSQL schema-fixture style. Create a legacy `forecast_snapshot_runs` table with `status VARCHAR(16) NOT NULL`, seed all three valid labels, call `migrate_enums(connection)`, and assert:

```python
assert _column_type(connection, "forecast_snapshot_runs", "status") == "forecast_snapshot_status"
assert _enum_labels(connection, "forecast_snapshot_status") == ("running", "completed", "failed")
assert _index_predicate(connection, "uq_forecast_snapshot_running_range") == "(status = 'running'::forecast_snapshot_status)"
```

Also add a test that seeds `status='unknown'` and asserts `EnumGovernanceError`, with the legacy column remaining `character varying`.

- [ ] **Step 7: Run the PostgreSQL migration test to verify it fails**

Run: `tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v`

Expected: FAIL because the snapshot enum group, table, and partial index are absent.

- [ ] **Step 8: Implement only the migration support required by the test**

Use the existing storage enum-adapter helpers for preflight, enum creation, explicit text-to-enum conversion, verification, and rollback. Ensure missing governed snapshot tables are created by the adapter, the legacy conversion rejects unknown labels, and rollback returns the status column to `VARCHAR(16)` only after checking enum dependencies.

- [ ] **Step 9: Run focused domain tests**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py -v && tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v`

Expected: PASS. SQLite validates SQLAlchemy constraints; PostgreSQL validates enum conversion, labels, partial uniqueness index, unknown-label rejection, and rollback.

- [ ] **Step 10: Commit the model and governance deliverable**

```bash
git add storage/domain_enums.py storage/model/forecast_snapshot.py storage/model/__init__.py storage/enum_migration.py tools/db_common.sh test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py
git commit -m "feat: add forecast snapshot schema"
```

## Task 2: Implement Atomic Snapshot Storage Lifecycle

**Files:**
- Modify: `storage/storage_db.py`
- Modify: `test/storage/test_forecast_snapshot_storage.py`
- Modify: `test/storage/test_forecast_snapshot_enum_migration.py`

**Interfaces:**
- Consumes: `ForecastSnapshotRun`, `ForecastSnapshotRecord`, and `ForecastSnapshotStatus` from Task 1.
- Produces: `StorageDb.acquire_forecast_snapshot_run(report_end_date: date, announcement_start_date: date, announcement_end_date: date) -> ForecastSnapshotRun`.
- Produces: `StorageDb.save_forecast_snapshot_records(run_id: int, records: list[dict[str, object]], counts: dict[str, int]) -> None`.
- Produces: `StorageDb.complete_forecast_snapshot_run(run_id: int, counts: dict[str, int]) -> ForecastSnapshotRun` and `StorageDb.fail_forecast_snapshot_run(run_id: int, failure_detail: str) -> ForecastSnapshotRun`.
- Produces: `StorageDb.get_completed_forecast_snapshot_run(...) -> ForecastSnapshotRun | None` and `StorageDb.list_forecast_snapshot_records(run_id: int) -> list[ForecastSnapshotRecord]`.

- [ ] **Step 1: Write failing acquisition and lifecycle tests**

Extend `test/storage/test_forecast_snapshot_storage.py` with a SQLite test showing the lifecycle contract:

```python
def test_snapshot_acquisition_reuses_completed_run_and_retries_failed_run(db):
    first = db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2))
    assert first.attempt == 1
    assert first.status == "running"

    db.complete_forecast_snapshot_run(first.id, {"covered_date_count": 2, "source_row_count": 0, "record_count": 0,
                                                "duplicate_record_count": 0, "same_day_conflict_count": 0})
    assert db.acquire_forecast_snapshot_run(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)).id == first.id

    failed = db.acquire_forecast_snapshot_run(date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 1))
    db.fail_forecast_snapshot_run(failed.id, "provider unavailable")
    retry = db.acquire_forecast_snapshot_run(date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 1))
    assert (retry.attempt, retry.status) == (2, "running")
```

Add tests that a second acquisition of an active SQLite range raises `StorageError`, records retain insertion order when listed, and `get_completed_forecast_snapshot_run` returns `None` for running and failed attempts.

- [ ] **Step 2: Run the lifecycle test to verify it fails**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py::test_snapshot_acquisition_reuses_completed_run_and_retries_failed_run -v`

Expected: FAIL because the `StorageDb` snapshot lifecycle methods do not exist.

- [ ] **Step 3: Implement lifecycle methods in `StorageDb`**

Add `ensure_forecast_snapshot_tables()` beside the existing forecast table ensure methods. It imports both snapshot models and creates them only for SQLite or non-governed paths; PostgreSQL table creation remains with enum governance.

Implement acquisition in a database transaction:

1. Ensure tables.
2. Query completed equivalent ranges first, ordered by `completed_at DESC, id DESC`; return the one row if present.
3. Query active equivalent ranges and raise `StorageError("forecast snapshot is already running for requested range")` if found.
4. Query the maximum attempt for the identity, insert a running row at `max + 1`, and return it.
5. Catch `IntegrityError` from the partial unique index, roll back, repeat the completed/active query once, then return the completed run or raise the same active-run `StorageError`.

`save_forecast_snapshot_records` performs an insert-only batch and updates only nonterminal run count columns. It must reject a run not in `running` state. `complete_forecast_snapshot_run` requires `covered_date_count == requested_date_count`, sets status `completed`, `completed_at`, and all final counts in one transaction. `fail_forecast_snapshot_run` requires a running run and sets `failed`, `failed_at`, and `failure_detail`; it never deletes records. List records by announcement date then `source_order ASC`.

- [ ] **Step 4: Run SQLite storage tests to verify they pass**

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py -v`

Expected: PASS. It proves completed reuse, failed retry, active-range exclusion, record ordering, and completed-only lookup.

- [ ] **Step 5: Write a failing PostgreSQL concurrency test**

In `test/storage/test_forecast_snapshot_enum_migration.py`, use two independent `StorageDb` instances backed by `TEST_POSTGRESQL_URL` and a random schema. Call `acquire_forecast_snapshot_run` for the same range through both, catching the expected `StorageError` from one caller. Assert exactly one persisted run has `status='running'` and `attempt=1`.

- [ ] **Step 6: Run the PostgreSQL concurrency test to verify it fails**

Run: `tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py::test_postgresql_allows_only_one_running_equivalent_snapshot -v`

Expected: FAIL before the acquisition method handles the partial-index `IntegrityError` race.

- [ ] **Step 7: Make race recovery deterministic and run focused storage verification**

Ensure the `IntegrityError` recovery path uses a newly opened transaction/session before re-querying. Do not replace the partial database constraint with an in-process lock.

Run: `uv run pytest test/storage/test_forecast_snapshot_storage.py -v && tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v`

Expected: PASS. PostgreSQL leaves exactly one running range and SQLite retains the same API behavior.

- [ ] **Step 8: Commit the storage lifecycle deliverable**

```bash
git add storage/storage_db.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py
git commit -m "feat: persist forecast snapshot lifecycle"
```

## Task 3: Build the Raw Provider Snapshot Service

**Files:**
- Create: `forecast_snapshot/__init__.py`
- Create: `forecast_snapshot/service.py`
- Create: `test/forecast_snapshot/test_service.py`

**Interfaces:**
- Consumes: `StorageDb` methods from Task 2 and `download.dl.downloader_tushare.require_pro_client` / the existing `forecast_fields` provider contract.
- Produces: `ForecastSnapshotRequest(report_end_date: date, announcement_start_date: date, announcement_end_date: date)`.
- Produces: `ForecastSnapshotSummary(run_id: int, attempt: int, status: str, requested_date_count: int, covered_date_count: int, source_row_count: int, record_count: int, duplicate_record_count: int, same_day_conflict_count: int, failure_detail: str | None)` with `to_dict() -> dict[str, int | str | None]`.
- Produces: `ForecastSnapshotService.create_snapshot(request: ForecastSnapshotRequest) -> ForecastSnapshotSummary`.

- [ ] **Step 1: Write a failing successful-range service test**

Create `test/forecast_snapshot/test_service.py` with a fake storage exposing Task 2 methods and an injected provider callable. Test an inclusive two-date range where the provider returns two ordered raw rows on the first date and an empty DataFrame with required columns on the second:

```python
summary = service.create_snapshot(
    ForecastSnapshotRequest(date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2))
)

assert provider.call_args_list == [call("20260701"), call("20260702")]
assert summary.to_dict() == {
    "run_id": 1, "attempt": 1, "status": "completed", "requested_date_count": 2,
    "covered_date_count": 2, "source_row_count": 2, "record_count": 2,
    "duplicate_record_count": 0, "same_day_conflict_count": 0, "failure_detail": None,
}
assert storage.saved_records[0]["source_order"] == 0
assert storage.saved_records[1]["source_order"] == 1
assert storage.saved_records[0]["ts_code"] == "600001.SH"
```

- [ ] **Step 2: Run the service test to verify it fails**

Run: `uv run pytest test/forecast_snapshot/test_service.py::test_create_snapshot_persists_all_provider_rows_in_source_order -v`

Expected: FAIL because the package, request type, and service do not exist.

- [ ] **Step 3: Implement request validation, raw provider call, and normalization**

Define `ForecastSnapshotRequest.__post_init__` to reject an announcement end before its start. In `ForecastSnapshotService`, inject:

```python
def __init__(self, storage: StorageDb, fetch_forecast: Callable[[str], pd.DataFrame]) -> None: ...
```

Provide a production factory that creates a TuShare client through the existing decorated provider helper and calls `client.forecast(ann_date=compact_date, fields=forecast_fields)`. Do not call `Downloader.dl_forecast`, because it filters to A shares.

For every row, require all forecast field names, parse `ann_date` and `end_date` with `format="%Y%m%d", errors="raise"`, require the parsed `ann_date` to equal the requested date, and parse non-null `p_change_min` / `p_change_max` with `pd.to_numeric(errors="raise")`. Store the raw `ts_code`, raw provider `type`, Python `date` values, and zero-based `source_order`. Allow nullable numeric provider fields by converting only non-null values.

Count duplicate records by repeated complete normalized value tuples and same-day conflicts by repeated `(ts_code, announcement_date)` groups beyond the first. Keep every row.

- [ ] **Step 4: Run the successful service test to verify it passes**

Run: `uv run pytest test/forecast_snapshot/test_service.py::test_create_snapshot_persists_all_provider_rows_in_source_order -v`

Expected: PASS. The service calls the provider once per ascending natural date, preserves both rows and orders, and treats the empty day as covered.

- [ ] **Step 5: Add failing validation, failure, reuse, and retry tests**

Add focused tests for:

```python
@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame({"ts_code": ["600001.SH"]})])
def test_missing_required_schema_marks_running_run_failed(frame): ...

def test_mismatched_returned_announcement_date_marks_run_failed(): ...
def test_invalid_numeric_value_marks_run_failed(): ...
def test_provider_exception_marks_run_failed_without_processing_later_dates(): ...
def test_completed_acquisition_returns_stored_summary_without_provider_call(): ...
def test_failed_acquisition_creates_later_attempt(): ...
```

The failed-run assertions must verify the run passed to `fail_forecast_snapshot_run` receives a detail containing the requested ISO announcement date and exception category. The completed-reuse test must assert `fetch_forecast.assert_not_called()`.

- [ ] **Step 6: Run the new tests to verify they fail for the expected behavior**

Run: `uv run pytest test/forecast_snapshot/test_service.py -v`

Expected: FAIL for each missing failure transition or completed-reuse branch.

- [ ] **Step 7: Implement minimal lifecycle error handling and summary conversion**

Acquire first. When acquisition returns an already completed run, build its summary and return without calling the provider. For all operational exceptions after acquiring a running run, call `fail_forecast_snapshot_run(run.id, detail)`, return its failed summary, and do not re-raise from the service. For successful processing, persist each date's records and accumulating counts, then complete the run. This means CLI and DAG decide their own failure signaling from `summary.status`.

- [ ] **Step 8: Run all service tests and style checks**

Run: `uv run pytest test/forecast_snapshot/test_service.py -v && uv run ruff format --check forecast_snapshot test/forecast_snapshot && uv run ruff check forecast_snapshot test/forecast_snapshot`

Expected: PASS with no formatter or lint diagnostics.

- [ ] **Step 9: Commit the service deliverable**

```bash
git add forecast_snapshot/__init__.py forecast_snapshot/service.py test/forecast_snapshot/test_service.py
git commit -m "feat: ingest immutable forecast snapshots"
```

## Task 4: Add the Explicit Operator Command

**Files:**
- Create: `tools/create_forecast_snapshot.py`
- Create: `test/tools/test_create_forecast_snapshot.py`

**Interfaces:**
- Consumes: `ForecastSnapshotRequest`, `ForecastSnapshotService`, and `conf.parse_config()` from Task 3.
- Produces: `main(argv: list[str] | None = None) -> int`.
- Produces: CLI options `--report-end-date`, `--announcement-start-date`, and `--announcement-end-date`, all required ISO dates.

- [ ] **Step 1: Write the failing command success test**

Create `test/tools/test_create_forecast_snapshot.py`:

```python
def test_main_prints_completed_snapshot_summary(monkeypatch, capsys):
    summary = ForecastSnapshotSummary(7, 1, "completed", 2, 2, 3, 3, 0, 0, None)
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "ForecastSnapshotService", lambda: service)

    assert command.main([
        "--report-end-date", "2026-06-30",
        "--announcement-start-date", "2026-07-01",
        "--announcement-end-date", "2026-07-02",
    ]) == 0
    assert service.create_snapshot.call_args.args[0].report_end_date == date(2026, 6, 30)
    assert "run_id=7 attempt=1 status=completed requested_date_count=2" in capsys.readouterr().out
```

- [ ] **Step 2: Run the command test to verify it fails**

Run: `uv run pytest test/tools/test_create_forecast_snapshot.py::test_main_prints_completed_snapshot_summary -v`

Expected: FAIL because the command module does not exist.

- [ ] **Step 3: Implement the command parser and output**

Follow `tools/backfill_forecast.py` path bootstrap and exact ISO parser style. Require all three arguments. Reject inverted ranges via `parser.error`, preserving argparse exit code `2`. Call `parse_config()` only after argument validation. Construct one `ForecastSnapshotService()` production instance and one `ForecastSnapshotRequest`.

Print fields in this exact stable order:

```text
run_id=<id> attempt=<attempt> status=<status> requested_date_count=<n> covered_date_count=<n> source_row_count=<n> record_count=<n> duplicate_record_count=<n> same_day_conflict_count=<n> failure_detail=<detail-or-empty>
```

Return `0` only for `completed`; return `1` for a service result with `failed` status.

- [ ] **Step 4: Run the command success test to verify it passes**

Run: `uv run pytest test/tools/test_create_forecast_snapshot.py::test_main_prints_completed_snapshot_summary -v`

Expected: PASS.

- [ ] **Step 5: Add failing invalid-input and failure-status tests**

Add parameterized invalid cases for each missing option, malformed ISO date, and end before start, all expecting `SystemExit.code == 2`. Add a failed-summary test asserting exit code `1`, output contains `status=failed` and the stored diagnostic string, and `parse_config()` was called for valid inputs.

- [ ] **Step 6: Run the command suite to verify failure cases fail**

Run: `uv run pytest test/tools/test_create_forecast_snapshot.py -v`

Expected: FAIL until invalid inputs and failed service results are handled.

- [ ] **Step 7: Complete command error paths and run focused checks**

Run: `uv run pytest test/tools/test_create_forecast_snapshot.py -v && uv run ruff format --check tools/create_forecast_snapshot.py test/tools/test_create_forecast_snapshot.py && uv run ruff check tools/create_forecast_snapshot.py test/tools/test_create_forecast_snapshot.py`

Expected: PASS with a stable output contract and no Ruff diagnostics.

- [ ] **Step 8: Commit the command deliverable**

```bash
git add tools/create_forecast_snapshot.py test/tools/test_create_forecast_snapshot.py
git commit -m "feat: add forecast snapshot command"
```

## Task 5: Add the Parameterized Manual Airflow Entry Point

**Files:**
- Create: `dags/create_forecast_snapshot.py`
- Create: `test/dags/test_create_forecast_snapshot.py`

**Interfaces:**
- Consumes: `ForecastSnapshotRequest` and `ForecastSnapshotService` from Task 3.
- Produces: `create_forecast_snapshot(**context: Any) -> dict[str, int | str | None]`.
- Produces: Airflow DAG ID `create_forecast_snapshot` with one Python task named `create_forecast_snapshot`, no schedule, and no dependency on the rolling forecast DAG.

- [ ] **Step 1: Write the failing DAG configuration and callable tests**

Create `test/dags/test_create_forecast_snapshot.py` by copying only the mocked-Airflow fixture mechanics from `test/dags/test_download_forecast_daily.py`. Assert:

```python
assert snapshot_module.dag.kwargs["schedule"] is None
assert set(task.task_id for task in FakePythonOperator.instances) == {"create_forecast_snapshot"}

result = snapshot_module.create_forecast_snapshot(
    dag_run=SimpleNamespace(conf={
        "report_end_date": "2026-06-30",
        "announcement_start_date": "2026-07-01",
        "announcement_end_date": "2026-07-02",
    })
)
assert result["status"] == "completed"
```

Mock the service and assert it receives a `ForecastSnapshotRequest` with parsed `date` fields.

- [ ] **Step 2: Run the DAG test to verify it fails**

Run: `uv run pytest test/dags/test_create_forecast_snapshot.py::test_snapshot_dag_is_manual_and_has_one_task -v`

Expected: FAIL because the DAG module does not exist.

- [ ] **Step 3: Implement the manual DAG and request parser**

Follow the existing DAG root-path bootstrap and `get_default_args()` import pattern. Define `dag = DAG("create_forecast_snapshot", ..., schedule=None, catchup=False, tags=["forecast", "manual"])`; do not modify any existing DAG. The callable reads `context["dag_run"].conf`, requires all three exact keys, parses exact ISO dates, and raises `ValueError` naming the missing or invalid parameter before constructing the service.

For a completed summary, return `summary.to_dict()`. For a failed summary, raise `RuntimeError` that contains `run_id` and `failure_detail`, so Airflow records task failure while the failed attempt stays in storage.

- [ ] **Step 4: Run the DAG configuration and successful-callable tests**

Run: `uv run pytest test/dags/test_create_forecast_snapshot.py -v`

Expected: PASS for DAG identity, manual schedule, request construction, and completed summary return.

- [ ] **Step 5: Add failing missing-config and failed-service tests**

Add tests for absent `dag_run`, absent one required conf key, malformed dates, inverted ranges, and a service summary with `status="failed"`. The failed-service assertion must require `RuntimeError` containing the persisted run ID and diagnostic detail.

- [ ] **Step 6: Run the failure-path tests to verify they fail**

Run: `uv run pytest test/dags/test_create_forecast_snapshot.py -v`

Expected: FAIL until all parameter validation and failure propagation behavior is implemented.

- [ ] **Step 7: Implement failure propagation and run focused DAG checks**

Run: `uv run pytest test/dags/test_create_forecast_snapshot.py -v && uv run ruff format --check dags/create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py && uv run ruff check dags/create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py`

Expected: PASS. The existing `download_forecast_daily` module remains untouched.

- [ ] **Step 8: Commit the DAG deliverable**

```bash
git add dags/create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py
git commit -m "feat: add forecast snapshot DAG"
```

## Task 6: Complete Regression Verification and Targeted Documentation

**Files:**
- Modify: `docs/airflow.md` only if it has a manual-DAG operation section.
- Modify: `docs/config.md` only if it has an operator-command section.
- Test: `test/forecast_snapshot/test_service.py`
- Test: `test/storage/test_forecast_snapshot_storage.py`
- Test: `test/storage/test_forecast_snapshot_enum_migration.py`
- Test: `test/tools/test_create_forecast_snapshot.py`
- Test: `test/dags/test_create_forecast_snapshot.py`
- Test: `test/download/test_download_manager.py`
- Test: `test/download/dl/test_forecast.py`
- Test: `test/tools/test_backfill_forecast.py`
- Test: `test/dags/test_download_forecast_daily.py`

**Interfaces:**
- Consumes: All prior task public interfaces.
- Produces: Verified snapshot command and manual DAG operation instructions, with no documented change to rolling refresh or backfill behavior.

- [ ] **Step 1: Inspect documentation applicability and update only an existing operator surface**

Read `docs/airflow.md` and `docs/config.md`. Update only a document that already covers the related operator surface: add the manual DAG run configuration under an Airflow operation section, or add the CLI invocation under an operator-command section. Use this exact manual trigger configuration:

```json
{
  "report_end_date": "2026-06-30",
  "announcement_start_date": "2026-07-01",
  "announcement_end_date": "2026-07-31"
}
```

If neither document has an applicable section, do not create unrelated documentation. Record this decision in the final completion report.

- [ ] **Step 2: Run all snapshot-focused unit tests**

Run: `uv run pytest test/forecast_snapshot/test_service.py test/storage/test_forecast_snapshot_storage.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py -v`

Expected: PASS. This establishes raw provider validation, lifecycle results, command contract, and manual DAG behavior.

- [ ] **Step 3: Run PostgreSQL storage-contract tests**

Run: `tools/run_tests.sh test/storage/test_forecast_snapshot_enum_migration.py -v`

Expected: PASS. This establishes named enum conversion, unknown-label rejection, rollback, partial active-range uniqueness, and cross-connection concurrency behavior.

- [ ] **Step 4: Run regression tests protecting existing forecast workflows**

Run: `uv run pytest test/download/test_download_manager.py test/download/dl/test_forecast.py test/tools/test_backfill_forecast.py test/dags/test_download_forecast_daily.py test/forecast/test_forecast_ingestion_operations.py -v`

Expected: PASS. This proves the existing incremental manager, rolling DAG, and backfill command retain their behavior.

- [ ] **Step 5: Run static quality checks on changed code**

Run: `uv run ruff format --check storage/model/forecast_snapshot.py storage/domain_enums.py storage/enum_migration.py storage/storage_db.py forecast_snapshot tools/create_forecast_snapshot.py dags/create_forecast_snapshot.py test/forecast_snapshot test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py && uv run ruff check storage/model/forecast_snapshot.py storage/domain_enums.py storage/enum_migration.py storage/storage_db.py forecast_snapshot tools/create_forecast_snapshot.py dags/create_forecast_snapshot.py test/forecast_snapshot test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_snapshot_enum_migration.py test/tools/test_create_forecast_snapshot.py test/dags/test_create_forecast_snapshot.py && uv run mypy storage forecast_snapshot dags/create_forecast_snapshot.py`

Expected: PASS. If existing mypy configuration excludes a touched CLI module, retain the command in Ruff coverage and report that scope explicitly.

- [ ] **Step 6: Inspect final change set and commit documentation/verification updates**

Run: `git status --short && git diff --check && git diff && git log --oneline -10`

Expected: Only Issue #60 source, tests, governed table/enum registration, and directly applicable documentation remain.

```bash
git add docs/airflow.md docs/config.md
git commit -m "docs: document forecast snapshot operation"
```

Stage only documentation files that were actually changed. If no documentation was applicable, do not make an empty commit.
