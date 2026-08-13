# Rolling Daily Forecast Ingestion Design

## Goal

Add the standalone daily forecast-ingestion workflow required by issue #50.
It refreshes the current China-local announcement date and preceding 29 natural
dates so newly published and revised A-share forecasts are available to the
next trading-day SSF MA20 synchronization.

## Scope

Add one Airflow DAG and focused DAG tests only:

- `dags/download_forecast_daily.py`
- `test/dags/test_download_forecast_daily.py`

The structured `ForecastDownloadResult` contract already exists from issue
#49. This issue does not add the parent issue's backfill command, change
forecast download normalization or persistence, or modify the existing forecast
SSF synchronization and monitor workflows.

## Architecture

The new `download_forecast_daily` DAG has one Python task,
`download_forecast`. It follows the existing standalone-DAG pattern and uses
the shared `LOCAL_TZ` and `get_default_args()` from `dags.common_dags`.

The DAG runs with `schedule="0 18 * * *"`, `catchup=False`, and
`max_active_runs=1`. Its every-day cron schedule intentionally includes
weekends and market holidays because forecasts can be announced on any natural
date. The task does not query or apply the A-share trading calendar.

## Data Flow

1. The task obtains `data_interval_end` from the Airflow context and converts
   it to `LOCAL_TZ` before taking the date.
2. It builds an inclusive 30-natural-date window ending on that local date.
3. For every date in the window, it calls
   `DownloadManager.download_forecast(ann_date=date.strftime("%Y%m%d"))`.
4. The existing manager invokes TuShare, preserves its existing A-share
   normalization and storage upsert behavior, and returns a
   `ForecastDownloadResult`.
5. The task aggregates requested, successful, empty, failed, source-row, and
   A-share-row statistics and records the per-date outcomes in a
   JSON-serializable dictionary returned through Airflow.
6. The next existing trading-day `forecast_ssf_ma20_sync` DAG uses the
   refreshed persisted data without an explicit dependency on this DAG.

## Result Semantics And Errors

An outcome is successful exactly when `ForecastDownloadResult.saved` is true.
Successful outcomes with zero source rows or zero A-share rows are normal,
valid empty dates and remain successful. An empty-date count includes every
successful date with either zero source rows or zero A-share rows.

The task raises `RuntimeError` as soon as it sees an unsuccessful result. The
error includes the relevant announcement date. This makes the Airflow task fail
and preserves its existing default retry and email-alert behavior. Statistics
are returned only after every date in the rolling window is successful.

## Testing

Use the existing mocked-Airflow DAG-test style. Mock
`DownloadManager.download_forecast` at the manager boundary; no test performs a
live TuShare request or contacts storage.

The tests verify:

- DAG ID, 18:00 every-day schedule, `max_active_runs`, and the single task.
- Correct conversion of a UTC data-interval end to the China-local date.
- Exactly 30 inclusive natural request dates, including dates that could fall
  on weekends or holidays.
- Aggregate source rows, A-share rows, requested and successful dates, and
  empty-date counts from structured results.
- Successful completion for valid empty outcomes.
- A `RuntimeError` for an unsuccessful outcome and no further date requests.

## Non-Goals

- Add or change the forecast backfill CLI.
- Modify `DownloadManager`, provider calls, forecast normalization, storage, or
  database schema.
- Change existing forecast SSF synchronization, daily monitor schedules,
  dependencies, task boundaries, retries, SLA, selection logic, or alert
  behavior.
- Add a zero-data alert, dashboard, or market-calendar gate.
