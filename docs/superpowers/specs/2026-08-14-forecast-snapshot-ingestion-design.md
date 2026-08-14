# Forecast Snapshot Ingestion Design

## Goal

Create immutable, auditable forecast snapshots for an explicit reporting-period
end date and inclusive announcement-date range. A completed snapshot retains
the normalized provider response and provider row order, while failed attempts
remain available for diagnosis and cannot become candidate input.

## Scope

Add a dedicated snapshot ingestion path with a command, parameterized Airflow
entry point, service, persistence models, storage methods, and focused tests.
The existing rolling forecast refresh remains an incremental write to mutable
forecast storage and does not create or complete snapshots.

All public date arguments use ISO `YYYY-MM-DD`. The provider boundary converts
them to `YYYYMMDD`.

## Architecture

### Dedicated Provider Boundary

The snapshot service calls a dedicated forecast-provider boundary rather than
`DownloadManager.download_forecast`. That manager intentionally normalizes to
supported A-share rows and writes mutable storage, which cannot retain all
provider rows or their source ordering. The snapshot boundary requests the
existing TuShare forecast field set and validates its response before data is
written.

For each requested announcement date, the service requires a pandas DataFrame
with all required provider columns: `ts_code`, `ann_date`, `end_date`, `type`,
`p_change_min`, and `p_change_max`. It validates every returned `ann_date`
against the requested date, normalizes dates and numeric fields, and assigns
zero-based `source_order` in the original response order. A successful empty
response covers its requested date and produces no records. Provider errors,
invalid result types, missing schema, invalid dates or numbers, response-date
mismatches, normalization errors, and persistence failures fail the run.

Rows outside the strategy universe remain snapshot records. Universe filtering
is a later candidate-screening concern and never discards auditable provider
input during ingestion.

### Immutable Lifecycle Storage

`ForecastSnapshotRun` persists one immutable input attempt with:

- reporting-period end date;
- inclusive announcement start and end dates;
- positive attempt number;
- lifecycle status `running`, `completed`, or `failed`;
- requested-date, covered-date, source-row, normalized-record, duplicate, and
  same-day-conflict counts;
- creation, completion, and failure timestamps; and
- a free-form failure-detail message.

`ForecastSnapshotRecord` belongs to a run and persists its normalized provider
fields, announcement date, report end date, numeric growth bounds, and
`source_order`. The `(run_id, source_order)` pair is unique. Completed records
are immutable: storage exposes no update or delete operation, and application
logic inserts all records before marking the run complete.

Use a Python `StrEnum` and named PostgreSQL enum for run status. The storage
schema follows the repository enum-migration requirements: explicit creation
and upgrade handling, PostgreSQL coverage, and export/import table-list
updates in `tools/db_common.sh`.

### Idempotency, Retry, and Concurrency

The range identity is `(report_end_date, announcement_start_date,
announcement_end_date)`. On a request:

1. A completed run with that identity is returned without provider calls.
2. A concurrent running run with that identity is rejected or observed as
   already in progress; no second downloader runs.
3. A failed history creates the next positive attempt and retains every earlier
   run and its diagnostics.
4. A new identity creates attempt one.

The storage layer enforces the one-running-attempt rule in PostgreSQL and
serializes range acquisition so two processes cannot both create a running
attempt. It returns the existing completed result deterministically. Each
successful per-date response and all run counts are persisted in the same
transactional lifecycle, so a failed finalization cannot expose a partial run
as completed.

Duplicate metrics record repeated normalized provider records and same-stock,
same-announcement-date conflicts. The latter preserves the final provider row
through its greater source order; ingestion never resolves or removes either
record.

### Operator Entry Points

`tools/create_forecast_snapshot.py` requires:

- `--report-end-date YYYY-MM-DD`
- `--announcement-start-date YYYY-MM-DD`
- `--announcement-end-date YYYY-MM-DD`

It initializes configuration through `conf.parse_config()`, validates an
inclusive non-inverted range, invokes the snapshot service, prints the run ID,
attempt, status, counts, and diagnostic detail, and returns a nonzero status
when the run fails. Invalid command arguments return exit code `2`.

A new manual, parameterized Airflow DAG entry point requires the same three
run-conf parameters. Its callable rejects absent, malformed, or inverted
parameters before constructing the service. It returns a JSON-serializable
run summary, and fails its task when the service reports a failed run. It does
not change the rolling forecast DAG's schedule, dependencies, retries, task
boundaries, or SLA.

## Data Flow

1. The command or DAG validates ISO date inputs and creates a snapshot request.
2. The service acquires the range lifecycle under the storage concurrency
   contract.
3. For a reusable completed run, it returns the stored summary immediately.
4. For a new attempt, it processes each natural announcement date in ascending
   order through the dedicated provider boundary.
5. It validates, normalizes, and persists every response in source order;
   valid empty responses increment coverage without records.
6. It atomically marks the run completed only after all requested dates are
   covered. On any failure, it marks that attempt failed with diagnostic detail
   and preserves records already written for diagnosis.
7. Future consumers query only completed runs. Failed runs and their records
   are excluded from candidate-input lookup.

## Error Handling

- A response that is not a DataFrame, lacks a required column, or has any
  mismatched announcement date fails the attempt.
- Date and numeric conversion is strict. A malformed value fails the attempt;
  null numeric provider values remain null only where the provider field is
  legitimately absent rather than malformed.
- Empty DataFrames are successful coverage after schema validation.
- Persistence exceptions mark the active attempt failed and retain diagnostic
  detail. They never leave it selectable as completed.
- A completed run is never mutated by a rerun. A failed run is never overwritten
  by retry.

## Testing and Verification

Tests use mocked TuShare/provider calls and never issue live requests.

- Service tests cover completed nonempty ranges, valid empty dates, source
  ordering, date validation, schema and numeric failures, failed lifecycle,
  idempotent completed reuse, retry attempts, and duplicate metrics.
- Command tests cover required ISO arguments, invalid and inverted ranges,
  success output, and failed-result exit status.
- DAG callable tests cover required run configuration, parameter parsing,
  returned summary, and failure propagation without changing the rolling DAG.
- SQLite storage tests cover normalized records, completed-only lookup, record
  order, and failed-run exclusion.
- PostgreSQL contract tests run through `tools/run_tests.sh` and cover enum
  schema creation or upgrade, concurrent acquisition of equivalent ranges,
  only-one-running invariant, immutable record storage, deterministic completed
  lookup, and retry history.
- Run focused test modules with `uv run pytest`, PostgreSQL tests with
  `tools/run_tests.sh`, and Ruff format/check plus relevant mypy checks on
  changed files.

## Non-Goals

- Change `DownloadManager.download_forecast`, current TuShare normalization,
  mutable forecast persistence, rolling forecast refresh, or backfill command.
- Infer announcement ranges from a disclosure calendar.
- Treat an explicit complete range as evidence that all possible disclosures
  for a reporting period have been retrieved.
- Select snapshots for candidates, implement forecast SSF synchronization, or
  change monitoring behavior. Those consumers will use only completed snapshot
  runs in later issues.
- Perform live-provider, scheduler, or production-database operations.
