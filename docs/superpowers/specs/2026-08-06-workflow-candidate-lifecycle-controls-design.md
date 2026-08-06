# Workflow Candidate Lifecycle Controls Design

## Goal

Make the forecast SSF workflow safe for long-running operation by recording durable candidate lifecycle transitions, preserving active targets when shareholder evidence is incomplete, retiring superseded reporting periods, and honoring an operator's explicit pause decision.

## Scope

- Persist every forecast SSF candidate lifecycle state with a reason, timestamped transition evidence, and target linkage.
- Support durable pause and resume controls on workflow-owned monitor targets.
- Continue collecting current evidence for paused workflow targets without automatically enabling them.
- Retire workflow targets for stocks that leave the qualified forecast universe or are superseded by a newer reporting period.
- Preserve manual targets and never mutate them through the forecast SSF workflow.

## Target Control Model

`StockMonitorTarget` gains a durable boolean `paused` column, defaulting to `False`. It represents an operator decision and is intentionally independent of `enabled`:

- `enabled` expresses whether price monitoring is active.
- `paused` prevents the forecast SSF synchronizer from activating the target automatically.

The monitor-target service and CLI expose explicit pause and resume operations for workflow-owned targets. Pausing marks the target paused and disables it in one transaction. It does not discard the candidate, evidence, lifecycle history, or workflow ownership. Resuming only clears `paused`; it does not enable the target. A later successful synchronization enables a resumed target only after fresh forecast, blackroom, and shareholder checks pass.

Manual unmarked targets are not selectable through workflow pause/resume controls and remain isolated from synchronization.

## Candidate Lifecycle

Each candidate remains keyed by stock, market, and workflow context and records one of these states:

- `eligible`: current forecast, blackroom, and fresh SSF-holder rules pass.
- `ineligible`: current data successfully proves the candidate does not qualify.
- `deferred`: shareholder data is unavailable, missing, or stale, so eligibility cannot be decided safely.
- `blackroom`: an active blackroom record excludes the stock.
- `paused`: the workflow target is manually paused; fresh evidence is still recorded.
- `delisted_or_unlisted`: a validated stock-listing check confirms the stock can no longer be monitored.

Every write appends or updates a `lifecycle` evidence record with `as_of_date`, state, reason, and prior state where it changed. Existing forecast, shareholder, blackroom, and historical lifecycle evidence is retained. The persisted candidate state reflects the manual pause while its target is paused, even when fresh evidence would otherwise make it eligible. The evidence retains the independently evaluated automatic outcome so operators can see whether a resume is likely to qualify on the next run.

## Synchronization Rules

The synchronizer first loads and validates the complete current forecast universe. A source or validation failure raises before any candidate or target write. It then completes blackroom preflight for every current forecast stock before candidate mutation.

For each current candidate:

1. A banned stock is persisted as `blackroom` and its matching workflow target is disabled unless it is already disabled. A later non-banned run can recover it when all other rules pass and it is not paused.
2. A holder-query exception, missing disclosure, or disclosure older than two months is persisted as `deferred`. It never changes target enablement, including for an already enabled workflow target.
3. A fresh disclosure without an SSF match persists `ineligible` and disables only the matching workflow target.
4. A fresh SSF match persists `eligible` and enables the matching workflow target unless it is paused. A paused target instead persists `paused`, updates evidence with the evaluated eligible result, and remains disabled.

After current candidates are processed, the synchronizer retires persisted workflow candidates not represented by the current qualified universe. It also compares reporting periods: when a current stock has a newer report end date, the older candidate is persisted as `ineligible` with `reporting_period_superseded` and its matching daily workflow target is disabled. The new period is evaluated on the next successful synchronization, not the same run. Retirement never deletes target or candidate rows.

Before changing an existing workflow target, the synchronizer verifies its durable workflow identity, stock, market, frequency, and candidate linkage. Missing or mismatched links transition only the candidate without creating or modifying a target.

## Listing Validation

The synchronizer validates whether a candidate remains listed before applying workflow target changes. A validated absent or delisted stock is recorded as `delisted_or_unlisted`, disables only its matching workflow target, and includes the listing validation outcome in evidence. A listing-source error is systemic: it raises before mutations rather than treating the stock as delisted.

## Atomicity And Idempotency

Candidate state, lifecycle evidence, and any matching workflow-target update are persisted using an atomic storage operation. If the target update fails, the candidate write rolls back as well.

Repeated runs with unchanged source data retain the same target state, do not re-enable paused targets, and do not increment action counters for no-op transitions. A paused target stays paused through blackroom changes, deferrals, ineligibility, reporting-period promotion, and qualified-universe retirement until an operator resumes it.

## Error Handling

- A failed forecast load, forecast validation, blackroom preflight, or listing validation produces no candidate or target mutation.
- Per-stock shareholder retrieval failures are contained as `deferred` transitions and do not disable targets.
- A target update failure rolls back its paired candidate transition.
- Pause/resume reject manual or non-workflow targets with a clear error.
- Resume does not imply eligibility or immediate activation.

## Testing

Storage tests will cover the `paused` schema default and migration, atomic pause/resume operations, workflow-target identity checks, lifecycle evidence persistence, and transaction rollback.

Service tests will cover every state and transition: blackroom exclusion and recovery; missing, stale, and failed shareholder data; non-SSF ineligibility; paused eligible candidates; explicit resume followed by fresh qualification; unqualified-universe retirement; newer-reporting-period supersession; delisted/unlisted retirement; target-link isolation; systemic preflight failures; and repeated-run idempotency.

CLI/service tests will verify that only marked workflow targets can be paused or resumed and that a manual target remains unchanged. Focused verification includes storage, monitor service, monitor CLI, and daily DAG tests, then Ruff, mypy for `storage`, `monitor`, and `dags`, and the full repository test suite.
