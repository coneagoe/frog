# Forecast Download Result Design

## Goal

Replace the boolean result returned by `DownloadManager.download_forecast` with
a stable, structured outcome for one requested forecast announcement date.
The result lets subsequent daily-ingestion and repair workflows distinguish
normal empty dates from failures and report what was persisted.

## Scope

This issue changes only the forecast download-manager boundary and its focused
tests. It does not add Airflow DAGs, backfill commands, or downstream callers.

## Result Contract

Add an immutable `ForecastDownloadResult` dataclass in
`download/download_manager.py` with these fields:

- `announcement_date: str`: the date supplied to `download_forecast`.
- `source_rows: int`: the number of rows returned by `Downloader.dl_forecast`.
- `a_share_rows: int`: the number of normalized A-share rows passed to
  `save_forecasts`.
- `saved: bool`: whether forecast persistence completed successfully.

`DownloadManager.download_forecast(ann_date)` always returns this type. A
successful persistence returns `saved=True`, including a zero-row input.
Provider, normalization, or persistence exceptions are logged through the
existing error path and return a result for the requested date with zero row
counts and `saved=False`.

The existing TuShare downloader already performs normalization before returning
its DataFrame. Therefore `source_rows` and `a_share_rows` are equal at this
boundary today, but remain separate fields because downstream orchestration
requires both observable statistics.

## Data Flow

1. The caller supplies an announcement date to `DownloadManager.download_forecast`.
2. The manager calls `Downloader.dl_forecast(ann_date=...)`, which retains its
   current provider and normalization behavior.
3. The manager rejects a `None` provider response as a failed outcome.
4. For a returned DataFrame, the manager records its row count and passes it to
   `get_storage().save_forecasts` without filtering or altering it.
5. On persistence success, the manager returns the requested date, both counts,
   and `saved=True`.
6. On an exception or false persistence result, the manager returns an
   unsuccessful result and retains the current error logging behavior.

## Error Handling

- An empty provider DataFrame is a valid success when `save_forecasts` succeeds.
- An empty normalized A-share DataFrame is also a valid success. At the current
  manager seam, this is represented by the same empty returned DataFrame.
- A `None` provider response, an exception from the provider or normalization,
  an exception from persistence, or a false persistence result is unsuccessful.
- The result carries no exception text. Existing logging remains the immediate
  diagnostic channel; detailed error reporting belongs to the later DAG and
  backfill issues.

## Testing

Extend `test/download/test_download_manager.py` using its existing mocked
downloader and storage setup. Cover:

- A non-empty response reports its requested date, row counts, and successful
  persistence.
- An empty DataFrame is persisted and reports a successful zero-row outcome.
- A `None` response returns an unsuccessful outcome without persistence.
- Provider exceptions return an unsuccessful outcome without persistence.
- A false persistence result returns an unsuccessful outcome with the observed
  row counts.
- Persistence exceptions return an unsuccessful outcome.

Tests do not call TuShare. Existing downloader tests remain responsible for the
normalization details below the manager seam.

## Non-Goals

- Do not alter TuShare forecast retrieval or A-share normalization.
- Do not alter forecast storage schema, upsert behavior, or empty-frame
  persistence semantics.
- Do not add the daily forecast DAG or the historical backfill command.
- Do not modify forecast SSF MA20 synchronization, monitor schedules, or
  candidate behavior.
