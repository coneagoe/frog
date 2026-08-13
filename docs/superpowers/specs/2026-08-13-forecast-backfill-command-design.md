# Forecast Backfill Command Design

## Goal

Add the explicit operator command required by issue #51 to populate or repair
forecast records for every natural announcement date in an inclusive range.
The command provides an auditable summary and allows the currently empty
current-year history to be backfilled independently of Airflow.

## Scope

Add one script and focused tests:

- `tools/backfill_forecast.py`
- `test/tools/test_backfill_forecast.py`

The script uses the existing `DownloadManager.download_forecast` structured
outcome. It does not change forecast retrieval, normalization, persistence,
the daily ingestion DAG, or forecast SSF synchronization.

## Command Interface

The script provides these optional arguments:

- `--start-date YYYY-MM-DD`
- `--end-date YYYY-MM-DD`

When neither argument is supplied, the selected inclusive range starts at
`2026-01-01` and ends seven natural days before the local execution date. When
either argument is supplied, both are required and define the explicit
inclusive range.

Dates must use the ISO `YYYY-MM-DD` format. Malformed dates, a missing paired
boundary, and an end date earlier than the start date are command-line
validation errors with exit code `2`. The script initializes configuration with
`conf.parse_config()` before constructing the download manager.

## Data Flow

1. The script resolves the requested date range, including both endpoints.
2. It constructs one `DownloadManager` and calls
   `download_forecast(ann_date=YYYYMMDD)` once for every natural date in
   ascending order.
3. It adds each `ForecastDownloadResult` to an aggregate summary containing
   requested dates, successful dates, empty dates, failed dates, source rows,
   and A-share rows.
4. A result is successful exactly when `saved` is true. A successful result
   with zero source rows or zero A-share rows is counted as an empty date.
5. The script continues through every selected date after failures so its final
   summary and failed-date list describe the complete requested range.
6. It writes an auditable summary to stdout. If any result failed, it also
   lists the failed announcement dates and exits with code `1`; otherwise it
   exits with code `0`.

Existing forecast persistence remains responsible for idempotency, so rerunning
a full or partial range is safe.

## Error Handling

- The existing download manager captures provider, normalization, and
  persistence errors into unsuccessful results; the backfill command does not
  duplicate that error handling.
- Empty source or normalized A-share data is a valid result when persistence
  succeeds and does not cause a nonzero exit.
- Operational failures are recorded per date rather than terminating the loop,
  allowing an operator to rerun only the affected interval after resolving a
  provider or storage issue.

## Testing

Tests mock `DownloadManager` and date resolution, without contacting TuShare or
storage. They verify:

- The default range begins on 2026-01-01 and ends seven natural days before
  the execution date.
- Explicit ranges include both endpoints and are requested in ascending order.
- Aggregate requested, successful, empty, source-row, and A-share-row totals
  follow structured result semantics.
- A failed date does not stop later dates, is reported in the summary, and
  returns exit code `1`.
- All-successful outcomes return exit code `0`.
- Invalid, incomplete, and inverted date arguments are validation errors with
  exit code `2`.

## Non-Goals

- Change `DownloadManager`, TuShare calls, forecast normalization, storage, or
  database schema.
- Change the `download_forecast_daily` DAG schedule, task behavior, retries,
  dependencies, or SLA.
- Add an Airflow task, monitoring alert, progress persistence, parallelism, or
  a market-calendar filter.
