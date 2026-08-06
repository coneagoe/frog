# Task 3 Report: Validated Candidate Lifecycle Synchronization

## Status

Completed. Task 3 adds listing-status preflight, lifecycle evidence, pause-aware transitions, reporting-period supersession, delisted/unlisted retirement, idempotent action counters, and storage rollback coverage while retaining workflow-only daily target ownership.

## Commits

- `f2fc45c Enforce forecast candidate lifecycle`
- `8d4d62e Document lifecycle task verification`

## Changed Files

- `storage/storage_db.py`
  - Added `load_a_stock_listing_status(stock_codes)` with SQLAlchemy expanding bind parameters.
  - Empty input returns the exact three-column DataFrame schema; database failures are not caught.
- `monitor/forecast_ssf_monitor_sync.py`
  - Preflights listing status and blackroom checks before candidate writes.
  - Records lifecycle evidence on every persistence path without discarding existing evidence.
  - Implements listing classification, reporting-period promotion, paused automatic outcomes, and exact workflow target-link retirement.
  - Counts disable operations only for targets that were enabled before an effective disable.
- `test/storage/test_forecast_ssf_candidate_storage.py`
  - Covers active/non-active/absent listing lookup rows, empty lookup input, and paused atomic rollback.
- `test/monitor/test_forecast_ssf_monitor_sync.py`
  - Covers paused eligibility, deferred target isolation, listing preflight failure, promotion gating, delisted retirement, blackroom recovery, and idempotent counters.

## Test Evidence

Red verification before implementation:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'paused or promotion or delisted or lifecycle or preflight' -v
4 failed, 1 passed, 18 deselected in 1.81s
```

Focused synchronizer verification after implementation:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -v
25 passed in 1.10s
```

Required focused regression suite:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py -v
86 passed in 9.59s
```

Quality checks:

```text
uv run ruff format monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
2 files left unchanged

uv run ruff check storage/storage_db.py monitor/forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_forecast_ssf_monitor_sync.py
All checks passed!

git diff --check
exit 0
```

## Self-Review

- Listing lookup uses parameterized expanding binds and exposes only the required columns.
- Listing and blackroom failures occur before any candidate or target mutation.
- Empty successful forecast universes still preflight persisted candidates and retire only matching daily workflow targets.
- Manual and intraday targets remain isolated through the existing exact workflow/daily lookup.
- Paused targets preserve an automatic evaluation in evidence while remaining disabled.
- Reporting-period promotion disables the existing workflow target and defers evaluation of the newer report period to the next sync.
- Atomic rollback tests cover both existing generic transitions and a paused candidate/target update failure.

## Concerns

- The required focused suite passed. Full repository `pytest test` and `mypy` were not run because this task requires the focused storage/monitor/DAG regression suite.
- SQLite returns the selected delisting `DATE` through `pandas.read_sql` as an ISO string; production classification only depends on listing status, and the storage test asserts that observed boundary representation.
