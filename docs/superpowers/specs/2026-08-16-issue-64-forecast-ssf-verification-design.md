# Issue 64 Forecast SSF Workflow Verification Design

## Goal

Verify and document the completed forecast SSF close-crossover workflow across its public seams. The workflow must remain research and monitoring only: it creates, retains, disables, and monitors candidates and targets, but it does not place orders or make execution decisions.

## Scope

- Validate focused service, monitor-runner, snapshot command, DAG callable, migration, and storage-contract behavior using existing public seams.
- Add regression coverage for the disabled/re-enabled workflow target lifecycle: a target already above MA20 must not alert immediately after re-enable, but must alert once after a later valid fall and upward final-close crossover.
- Update operator documentation for snapshot range verification, completed-snapshot selection on later synchronization windows, current listing/ST limitations, disabled-target retention, HFQ final-close crossover semantics, and no automatic trade execution.
- Keep DAG schedules, dependencies, retries, task boundaries, and SLA unchanged.

## Verification Claim

The assembled workflow is correct when:

- Snapshot ingestion explicitly verifies every requested announcement date in the requested range; completed snapshots are the only eligible synchronization input.
- Synchronization on a later business date selects the latest completed snapshot whose announcement end date is not later than the business date.
- Candidate screening is limited to currently listed, non-ST, supported A-share stocks with qualifying forecast and SSF evidence.
- Lifecycle transitions retain workflow target identity and `last_state` through disable, pause, resume, blackroom suppression, and requalification.
- `close_cross_ma` evaluates final HFQ closes only and triggers on `previous_close <= previous_ma20` followed by `current_close > current_ma20`.
- The workflow records monitoring evidence only and never issues trading orders.

## Approach

Use the recommended focused-verification approach:

1. Add one public monitor-runner regression that exercises the disable/re-enable lifecycle state edge through `close_cross_ma` final-close histories.
2. Reuse existing focused test suites for service, snapshot command, DAG callable, migration, and storage-contract acceptance criteria rather than broad refactoring.
3. Update `docs/stock_monitor.md` with concise operator-facing coverage limits and safety semantics.
4. Run focused pytest targets, PostgreSQL-dependent storage coverage through `tools/run_tests.sh`, formatting, lint, and relevant type checks.

## Testing

- RED: write the monitor-runner regression first and verify it fails for the intended alert-sequencing reason if the current behavior is incomplete.
- GREEN: make the smallest code change needed only if the regression fails.
- Run focused suites covering:
  - `test/monitor/test_monitor_runner.py`
  - `test/monitor/test_forecast_ssf_monitor_sync.py`
  - `test/tools/test_create_forecast_snapshot.py`
  - `test/dags/test_create_forecast_snapshot.py`
  - `test/dags/test_forecast_ssf_ma20_sync.py`
  - storage and migration tests through `tools/run_tests.sh` where PostgreSQL is required.
- Run `uv run ruff format`, `uv run ruff check`, and relevant `uv run mypy` checks.

## Non-Goals

- Do not change DAG topology or scheduling.
- Do not introduce automatic trading, order placement, portfolio decisions, or execution recommendations.
- Do not broaden candidate qualification beyond current listed non-ST A-share support.
- Do not replace existing storage contracts or migration mechanics.

## Self-Review

- No placeholders remain.
- The scope is limited to issue #64 verification and documentation.
- The design separates regression coverage, documentation, and verification commands.
- The no-trading boundary is explicit.
