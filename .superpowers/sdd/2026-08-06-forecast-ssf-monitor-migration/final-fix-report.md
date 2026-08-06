# Final Review Fix Report

## Scope

- Finding 1: generic monitor-target storage operations must migrate a legacy table before mapped ORM access.
- Finding 2: a manual target must not receive a JSON workflow marker without durable workflow ownership.

## Root Cause

- `list_monitor_targets`, `get_monitor_target`, manual `create_monitor_target`, `update_monitor_target`, `delete_monitor_target`, and `update_monitor_target_state` opened mapped ORM operations before the migration gate. A pre-Issue-31 table therefore failed when SQLAlchemy selected or inserted the mapped `workflow` column.
- `update_monitor_target` protected existing durable workflow owners but allowed a durable manual target to receive `condition["workflow"]`, producing inconsistent JSON and durable ownership.

## Test-Driven Evidence

- Added real SQLite legacy-schema coverage for every generic operation, each starting from a table without `workflow`.
- Added a real persistence test that rejects a manual condition update containing a workflow marker and verifies that both condition and durable owner remain unchanged.
- Red run: `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -k 'generic_monitor_target_operations or manual_monitor_target_rejects_condition_workflow_marker' -v` produced seven expected failures: six missing-column failures and one missing validation failure.
- Green run: the same focused command passed after the production changes.

## Production Changes

- Generic target operations call `ensure_monitor_targets_table()` before any mapped target ORM query or insert.
- The gate remains non-recursive: it creates/migrates schema through `_ensure_workflow_monitor_target_identity()` and does not invoke generic target operations.
- Manual targets reject condition updates with a non-NULL workflow marker, preserving durable ownership.

## Verification

- `uv run pytest test/storage/test_forecast_ssf_candidate_storage.py -v`: 24 passed.
- `uv run pytest test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py test/dags/test_monitor_stock_daily.py -v`: 35 passed.
- `uv run pytest test`: 1217 passed, 17 skipped, 6 existing third-party deprecation warnings.
- `uv run ruff format --check storage/storage_db.py test/storage/test_forecast_ssf_candidate_storage.py`: passed.
- `uv run ruff check storage monitor dags test/storage/test_forecast_ssf_candidate_storage.py`: passed.
- `uv run mypy storage monitor dags`: passed with the existing unused-module-section note.
- `git diff --check`: passed.

## Documentation Review

- No repository documentation required a behavioral update because this wave only corrects internal migration-gate coverage and an existing ownership invariant.
- This report records the final-review remediation and evidence.
