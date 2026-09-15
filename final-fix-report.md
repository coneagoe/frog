# Issue #115 final-fix report

## Fixes

- Alert triggers keep original `evidence` immutable and reject deletes, while permitting delivery state/metadata updates. Migration and export DDL install the same trigger contract.
- Delivery metadata is added before recovery-schema preflight, upgrading existing schemas before validation.
- Approved execution resolves through the locked repository callback, avoiding a second fresh-session lock acquisition.

## Retry safety

The external history write precedes database resolution. If the database transaction rolls back, retry remains safe because the exact `(stock_id, business_date)` write/readback contract is idempotent: retry may repeat the upsert but cannot create a second exact row or resolve a mismatched row.

## Verification

- `uv run pytest test/paper_trading/services/test_data_gap_recovery_service.py test/paper_trading/services/test_data_gap_alert_service.py -q`: 49 passed.
- `uv run pytest test/paper_trading/storage/test_data_gap_recovery.py test/paper_trading/api/test_data_gap_recovery_api.py -q`: 51 passed.
- `tools/run_tests.sh test/paper_trading/storage/test_data_gap_recovery_enum_migration.py -v`: 7 passed, including legacy enum setup with an explicit typed default.
- `uv run ruff check` on all changed Python files: passed.

## Final review fix

- Approved execution now reads the exact history key while holding the approval transaction lock before appending. A matching existing row is reused and the gap is resolved; a differing row fails closed.
- Added coverage for a matching pre-existing row and retry after resolution failure, confirming the history writer is called only once.
- Ordinary provider rows are recorded as immutable canonical candidates before the recovery write, and the production DAG persists those records through its fresh-session repository adapter.
- Rollback now performs the same strict recovery schema, constraint, and append-only trigger preflight as forward migration; stale pending alert claims are reclaimable after fifteen minutes.

## Latest blocker fixes

- Escalated provider candidates are immutable evidence only and transition to pending approval without an automatic history write; pending approvals are guarded from recovery writes.
- Candidate retries are idempotent after payload, validation, and source compatibility checks.
- Approved execution receives the immutable payload from the locked repository boundary; the DAG no longer reconstructs a caller payload.

## Final blocker fix

- `canonical_candidate_payload()` now recursively normalizes NumPy scalars, pandas/NumPy dates, decimals, missing values, mappings, and simple sequences into deterministic JSON-safe values. Canonical hashing now serializes strictly without an arbitrary string fallback.
- Added production-shaped NumPy provider-row coverage proving JSON serialization, hash stability after round-trip, and `record_candidate()` persistence.

## Final verification

- `uv run pytest test/paper_trading/services/test_data_gap_recovery_service.py test/paper_trading/storage/test_data_gap_recovery.py test/paper_trading/api/test_data_gap_recovery_api.py test/paper_trading/services/test_data_gap_alert_service.py test/dags/test_partition_dag_sources.py test/tools/test_paper_trading_cli.py -q`: 285 passed, 20 skipped.
- `tools/run_tests.sh test/paper_trading/storage/test_data_gap_recovery_enum_migration.py -v`: 7 passed.
- `uv run ruff check` on changed Python files: passed.
- Simplify review: no safe simplification identified.

## Full export/import enum expectation

- Confirmed the full export/import failure was a stale four-label test expectation; governed `DataGapRecoveryStatus` now includes `pending_approval`. Updated the test to derive expected labels from the enum. `delivery_metadata` was not added because it is outside this test's enum-registration purpose.

## Documentation rationale

- Corrected `docs/airflow.md` to describe threshold escalation, immutable candidate recording, pending browser approval, alerts, and account recovery as part of the post-matching recovery workflow, and to state that escalated candidates do not auto-write before approval.
