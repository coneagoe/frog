# Forecast Ingestion Operations Verification Design

## Goal

Verify the routine rolling forecast-ingestion DAG and explicit forecast
backfill command from issues #50 and #51 as reliable, interpretable operations
without changing forecast download, persistence, or forecast SSF MA20
synchronization behavior.

## Scope

Add focused verification tests only. Production modules remain unchanged.

- Add a focused cross-workflow test module for the daily DAG and backfill
  command.
- Extend focused forecast persistence coverage only as needed to demonstrate
  that reprocessing the same forecast rows remains idempotent.
- Retain the existing forecast SSF MA20 synchronization DAG test as the
  explicit non-regression guard.

## Shared Download Contract

Both workflow entry points call `DownloadManager.download_forecast` and consume
the returned `ForecastDownloadResult`. Tests mock this manager boundary using
equivalent result fixtures to verify shared interpretations:

- `saved=True` is a successful date.
- A successful result with zero source rows or zero A-share rows is a valid
  empty date.
- Aggregate source-row and A-share-row totals are accumulated from every
  processed result.
- An unsuccessful result is a failed date.

No test performs a live TuShare request or changes provider, normalization, or
storage behavior.

## Workflow Verification

### Rolling Daily Ingestion

Tests verify the public daily task with a mocked download manager:

- It derives its end date from `data_interval_end` converted to `LOCAL_TZ` and
  processes exactly 30 inclusive natural dates in ascending order.
- It returns the expected requested, successful, empty, failed, source-row,
  and A-share-row aggregates for successful and valid empty results.
- It stops at the first unsuccessful result, logs accumulated statistics, and
  raises `RuntimeError` containing the announcement date so Airflow can apply
  its existing retry and alert behavior.

### Explicit Backfill

Tests verify the command with a mocked download manager:

- An explicit `--start-date` / `--end-date` range includes both boundaries and
  processes dates in ascending order.
- It reports the same aggregate semantics as the daily workflow for successful
  and valid empty results.
- It continues after unsuccessful results, prints the complete summary and
  failed announcement-date list, and returns exit code `1` when any date
  failed.
- Successful ranges, including valid empty results, return exit code `0`.

The contrasting failure behavior is intentional: the scheduled task fails
immediately for Airflow retry handling, while the operator command completes
the interval to provide an auditable rerun target.

## Persistence Idempotency

Extend existing forecast storage coverage to save the same normalized forecast
records twice. The test verifies the second save succeeds and the retained
forecast data is not duplicated. This confirms that repeated dates from the
rolling window or overlapping backfill range preserve the existing upsert
semantics.

## Forecast SSF Synchronization Non-Regression

`test/dags/test_forecast_ssf_ma20_sync.py` remains the focused guard for the
independent synchronization workflow. It verifies its existing schedule,
single task, trading-day skip behavior, China-local as-of date, and service
result handling. Issue #52 neither adds a dependency between the ingestion DAG
and this synchronization DAG nor changes synchronization code.

## Verification

Run the focused forecast operation tests, the forecast storage test, and the
forecast SSF synchronization test with `uv run pytest`. Run Ruff formatting
and lint checks on changed Python files if production or test files are added
or updated.

## Non-Goals

- Change `DownloadManager`, provider calls, forecast normalization, storage
  schema, or forecast persistence implementation.
- Change the daily ingestion DAG schedule, dependencies, retries, task
  boundaries, or SLA.
- Change the backfill command interface or its failure semantics.
- Change forecast SSF MA20 synchronization behavior or introduce an explicit
  dependency between it and forecast ingestion.
- Add live-provider, Airflow scheduler, or full PostgreSQL-container
  integration tests.
