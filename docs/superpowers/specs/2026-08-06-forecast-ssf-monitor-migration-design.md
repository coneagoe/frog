# Forecast SSF Monitor Migration Design

## Goal

Make the forecast SSF monitor workflow safe for upgraded monitor-target databases, diagnose legacy workflow-owner duplicates before enforcing uniqueness, and retire workflow targets whose stocks no longer belong to the qualified forecast universe.

## Scope

- Upgrade existing `stock_monitor_targets` tables before any ORM access that selects the durable `workflow` column.
- Backfill the durable workflow owner from `condition["workflow"]`, including an empty string because every non-NULL durable value denotes ownership.
- Reject legacy duplicate workflow owners with an actionable error before creating the unique ownership index.
- Disable and record workflow-owned daily targets when their stock is absent from the current qualified forecast candidates.
- Preserve manual targets and workflow targets for frequencies other than `daily`.

## Schema Migration

`StorageDb.ensure_monitor_targets_table()` is the single migration gate. It must create the table if absent and then invoke workflow-identity migration before callers query or insert `StockMonitorTarget` rows.

The migration performs these ordered actions:

1. Add nullable `workflow VARCHAR(64)` when the existing table lacks it.
2. Backfill every row with `workflow IS NULL` from a present JSON `condition["workflow"]` marker. An empty-string marker is backfilled because it is a non-NULL owner value.
3. Query non-NULL owners grouped by `(stock_code, market, frequency, workflow)`.
4. If any group has more than one row, raise `ValueError` before index creation. The message includes the owner key and conflicting target IDs. The migration does not delete, merge, or otherwise modify conflicting rows.
5. Create `uq_stock_monitor_targets_workflow_owner` only after duplicate validation succeeds.

All monitor startup paths, target CLI operations, and daily monitoring therefore encounter either a compatible schema or a clear remediation error instead of an undefined-column/database-specific index error.

## Synchronization Lifecycle

The synchronizer continues to process each current qualified forecast candidate using blackroom filtering and the existing SSF detector. After that pass, it inspects persisted candidates associated with the daily `forecast_ssf_ma20` workflow whose stock codes were absent from the current forecast result.

For each absent stock, it finds only the daily workflow-owned target. It atomically persists candidate state `ineligible` with reason `forecast_no_longer_qualified` and disables that target when it exists and is enabled. Candidate evidence retains the prior evidence, augmented with the current synchronization date and a lifecycle marker identifying qualified-universe removal. A missing target still results in the candidate state transition with no target linkage. Manual and intraday targets are never queried or mutated by retirement.

An empty forecast result is a valid, successful synchronization and retires all persisted daily `forecast_ssf_ma20` candidates. A systemic failure while loading current qualified forecasts still raises before any candidate or target mutation.

## Error Handling

- A missing legacy `workflow` column is migrated before ORM target access.
- Legacy duplicate ownership fails closed with a readable `ValueError`; operator data must be repaired before monitoring proceeds.
- Target retirement uses the existing atomic candidate-and-workflow-target storage primitive, so candidate evidence and target disablement commit or roll back together.
- A candidate without a linked workflow target is recorded as ineligible without attempting to create or change a target.

## Testing

Storage tests will build pre-Issue-31 SQLite schemas without `workflow` and verify startup migration permits target reads and manual creates. They will verify marker backfill, empty-string backfill, duplicate diagnostics before index creation, and successful uniqueness enforcement afterward.

Service tests will verify that an absent qualified stock disables only its matching daily workflow target, persists the approved ineligible state and lifecycle evidence, leaves manual and intraday targets untouched, and handles an empty qualified universe. Existing systemic-failure and atomic-transition tests remain regression coverage.

Focused verification will include the migration storage tests, forecast SSF service tests, monitor-target service tests, daily DAG tests, Ruff, mypy for `storage`, `monitor`, and `dags`, and the repository's full test suite before integration.
