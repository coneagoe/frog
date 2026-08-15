## Task 3 Report: Raw Provider Snapshot Service

### Delivered

- Added `forecast_snapshot` with a request type, immutable summary type, injectable service, and production TuShare provider factory.
- The provider boundary calls `client.forecast(ann_date=..., fields=forecast_fields)` through `get_pro` and `require_pro_client`; it does not use `DownloadManager` or `Downloader.dl_forecast`.
- The service retains every raw provider row, including non-A-share codes, uses zero-based source order per provider response, validates schema/dates/numeric fields, and persists date-by-date totals.
- Empty responses with the required schema persist no rows but count as a covered provider date. The service-provided coverage count is passed through to storage unchanged.
- Completed acquisitions return their stored summary without a provider request. Errors after acquiring a running run transition that run to `failed`, include the requested ISO date and exception type in the diagnostic, and return a failed summary.

### TDD Evidence

RED:

```text
uv run pytest test/forecast_snapshot/test_service.py::test_create_snapshot_persists_all_provider_rows_in_source_order -v
FAILED: ModuleNotFoundError: No module named 'forecast_snapshot'
```

GREEN and final focused verification:

```text
uv run pytest test/forecast_snapshot/test_service.py -v
10 passed

uv run ruff format --check forecast_snapshot test/forecast_snapshot
3 files already formatted

uv run ruff check forecast_snapshot test/forecast_snapshot
All checks passed!
```

### Documentation Review

No existing repository documentation required changes. The forecast snapshot design and implementation plan already cover this service task; `README.md` and `AGENTS.md` do not document this internal provider/service API.

### Residual Scope

This task intentionally does not change mutable forecast refresh, the rolling DAG, or the backfill command. Storage lifecycle persistence remains covered by Task 2's storage tests; this task tests the service with injected provider and storage seams.

### Fix Round 1: Reject Non-Finite Numeric Values

Root cause: `pd.to_numeric(..., errors="raise")` converts infinity representations to non-finite floats without raising. `_optional_numeric` previously persisted that result without checking whether it was finite.

RED reproduction:

```text
uv run pytest test/forecast_snapshot/test_service.py::test_invalid_numeric_value_marks_run_failed -v
1 failed, 1 passed

FAILED test_invalid_numeric_value_marks_run_failed[inf]
AssertionError: assert 'completed' == 'failed'
```

GREEN evidence:

```text
uv run pytest test/forecast_snapshot/test_service.py::test_invalid_numeric_value_marks_run_failed -v
3 passed
```

Changed files:

- `forecast_snapshot/service.py`: reject converted numeric values that are not finite after preserving actual null values as `None`.
- `test/forecast_snapshot/test_service.py`: exercise `"NaN"` and `"inf"` through the failed-run lifecycle, and rename the preconfigured attempt-2 test to match its behavior.
- This report.

Self-review:

- The finite check is immediately after conversion and applies to either optional numeric provider field.
- Legitimate absent provider values still take the existing `pd.isna(value)` branch and remain nullable.
- The failure is handled by the existing operational failure lifecycle, so its detail includes the requested ISO date and `ValueError`.
- No mutable forecast refresh, rolling DAG, backfill command, or provider boundary behavior changed.
