# Final Review Fix Report

## Scope

Fixed the listing-data contract consumed by the forecast SSF synchronizer.
`StorageDb.load_a_stock_listing_status` now returns `COL_STOCK_NAME` for both
empty and populated data frames, allowing the existing synchronizer ST-name
qualification check to receive real listing data.

## Changed Files

- `storage/storage_db.py`
- `test/storage/test_forecast_ssf_candidate_storage.py`
- `test/monitor/test_forecast_ssf_monitor_sync.py`

## Regression Coverage

- Storage contract verifies populated listing output includes stock names and
  that an empty listing output preserves the same schema.
- Integration-level sync coverage builds real SQLite-backed `StorageDb`
  listing data for a listed `*ST` stock, supplies an immutable forecast record,
  and verifies that the stock cannot qualify, its retained workflow target
  remains disabled, and blackroom lookup is not reached.

## Commands And Results

1. `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py::test_load_a_stock_listing_status_returns_requested_rows_and_omits_absent_codes test/storage/test_forecast_ssf_candidate_storage.py::test_load_a_stock_listing_status_empty_input_returns_schema_only -v`
   Result: failed before the production fix because `COL_STOCK_NAME` was absent
   from both result schemas; passed after the fix, 2 passed.

2. `uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py::test_sync_real_listing_output_keeps_st_named_stock_target_disabled -v`
   Result: failed before the production fix because the listed ST stock counted
   as a forecast candidate; passed after the fix, 1 passed.

3. `uv run pytest test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py -v`
   Result: 127 passed, 12 SQLite date-adapter deprecation warnings.

4. `uv run ruff format --check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py && uv run ruff check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py monitor/shareholder_selling_punishment.py test/storage/test_forecast_snapshot_storage.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py test/dags/test_forecast_ssf_ma20_sync.py`
   Result: 7 files already formatted; all checks passed.

5. `uv run mypy storage monitor`
   Result: success with no issues in 51 source files. Mypy also printed the
   repository's existing unused-module-override note from `pyproject.toml`.

## Documentation Review

No repository documentation was changed. The existing issue design already
states that qualification requires listed, non-ST status; this is a narrow
storage-output contract repair rather than a behavior or architecture change.
