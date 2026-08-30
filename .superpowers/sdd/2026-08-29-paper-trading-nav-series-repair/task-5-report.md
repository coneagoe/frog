# Task 5 Report — Replay Historical Corporate Actions

## Implemented

- Corporate-action impacts are replayable facts: dividend, split, reverse split,
  bonus share, and rights issue are recalculated from replay state and persisted
  parameters rather than current position state.
- Initial replay events restore proven imported holdings and cost basis.
- Mutable position/lot projections are updated only after the replayed pre-action
  state matches the projection; mismatches are rejected before accounting writes.
- Existing cash-ledger audit rows remain separate from corporate-action replay
  events, preventing duplicate cash application during NAV replay.
- Existing idempotency, processing metadata, affected range, precision, and
  bounded snapshot recalculation behavior are preserved.
- Corporate-action API/service fixtures now use imported holdings as explicit
  historical facts and post-baseline event times.

## Verification

- `uv run pytest test/paper_trading/domain/test_corporate_actions.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/api/test_corporate_actions_api.py -q`
  - **93 passed**, 1 existing Starlette/httpx deprecation warning.
- `uv run ruff check ...` on all Task 5 changed source and test files: **passed**.
- `git diff --check`: **passed**.
- PostgreSQL runner: skipped; the assigned focused coverage did not require
  PostgreSQL integration.

## Simplification Review

The replay path and projection update were reviewed for safe simplification;
no further behavior-preserving reduction was worthwhile within Task 5 scope.

## Concerns

- The working tree includes only Task 5 source/test files plus this report.
- Full CI and orchestrator-owned PostgreSQL verification remain outside this
  agent's assigned validation.
