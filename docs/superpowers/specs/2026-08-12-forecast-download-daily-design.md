# Daily Forecast Download Design

## Goal

Populate and maintain the `forecasts` table with A-share earnings forecasts so
that `forecast_ssf_ma20_sync` has data to evaluate.

## Scope

Add a standalone `download_forecast_daily` Airflow DAG. It runs daily, reloads
the latest 30 natural announcement dates from TuShare, and persists normalized
A-share records through `DownloadManager.download_forecast`.

Add a standalone `tools/backfill_forecast.py` script for the currently empty
table and future explicit repairs. Its default interval is 2026-01-01 through
the date seven natural days before execution. It accepts `--start-date` and
`--end-date` overrides.

The existing `forecast_ssf_ma20_sync` DAG remains unchanged. Forecasts
downloaded after market close become eligible for its next trading-day 15:05
sync.

## Scheduling

- DAG ID: `download_forecast_daily`
- Schedule: 18:00 every natural day in `Asia/Shanghai`; it does not skip
  weekends or market holidays because forecasts can be announced then.
- Task: one Python task, `download_forecast`
- Execution: derive the China-local date from Airflow's data interval with
  `data_interval_end.in_timezone(LOCAL_TZ).date()`. The task queries that date
  and the preceding 29 natural dates.
- The DAG `start_date` and schedule use the existing `LOCAL_TZ` setting so
  18:00 always means China Standard Time, rather than the container's UTC date.

## Data Flow

1. The DAG derives the current China-local announcement date from its data
   interval.
2. It calls `DownloadManager.download_forecast(ann_date=YYYYMMDD)` once per
   date in the 30-day natural-date window.
3. The manager calls TuShare's `forecast` endpoint, normalizes A-share records,
   and saves them to `forecasts` using the existing upsert behavior.
4. `DownloadManager.download_forecast` returns an immutable
   `ForecastDownloadResult`, rather than a boolean. It contains
   `announcement_date`, `source_rows`, `a_share_rows`, and `saved`.
5. The DAG logs and returns the per-date and aggregate statistics. A failed
   result raises an error so Airflow records the failed run and applies the
   repository's existing retry policy.
6. On the next trading day, `forecast_ssf_ma20_sync` reads the persisted data
   and applies its existing forecast, blackroom, shareholder, and MA20 rules.

## Backfill

`tools/backfill_forecast.py` invokes the same download-manager method for each
natural date in the requested inclusive range. It excludes the latest seven
days by default so it does not overlap the daily DAG's 30-day rolling window.
Explicit date arguments may include those dates for targeted repair.

The script emits aggregate requested-day, successful-day, empty-day,
source-row, A-share-row, and failed-date statistics. It exits with code 0 only
when every date completes; it exits nonzero and lists failed dates otherwise.
Existing forecast-table keys make repeats and partial-range reruns idempotent.

## Error Handling

- Provider errors are handled by the downloader's existing three-attempt retry;
  an unsuccessful manager result fails the DAG task or is recorded as a failed
  date by the backfill script.
- Empty provider results, including results containing no A-share rows, are
  valid successes. The result statistics distinguish both cases from failures.
- No new zero-data alert is added. Empty forecast days are normal outside
  reporting seasons. Provider, normalization, and persistence errors retain
  existing Airflow retry and email-alert behavior.

## Tests

Add DAG tests that verify:

- The DAG ID, 18:00 schedule, and single task.
- Conversion from a UTC data interval to the correct China-local 30-day date
  window.
- Per-date and aggregate statistics returned from the task.
- A failed result raises an exception, while empty source or A-share results
  complete successfully.
- The download-manager result type for source count, normalized A-share count,
  and persistence status.
- Backfill inclusive ranges, default end-date behavior, summary output, and
  nonzero exit status for partial failure.

## Non-Goals

- Do not modify the 15:05 `forecast_ssf_ma20_sync` schedule, dependencies, or
  current latest-reporting-period selection behavior. A newly available report
  period takes effect immediately regardless of its candidate count.
- Do not embed forecast download in monitor execution DAGs.
- Do not change forecast filtering, SSF matching, or monitor-target rules.
