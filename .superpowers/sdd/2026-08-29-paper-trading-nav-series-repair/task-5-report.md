# Task 5 Report — Replay Historical Corporate Actions

## Implemented

- Corporate-action impacts are replayable facts: dividend, split, reverse split,
  bonus share, and rights issue are recalculated from replay state and persisted
  parameters rather than current position state.
- Initial replay events restore proven imported holdings and cost basis.
- Mutable position/lot projections are updated only after the replayed pre-action
  state is proven. Late actions materialize the complete post-action replay,
  including later trades, before updating the current projection.
- Corporate actions sharing a timestamp with a trade are rejected as ambiguous
  unless chronology is separately proven; no static precedence guess is used.
- Actions earlier than the proven initial baseline are rejected before impact or
  accounting persistence.
- Valid event timestamps remain replayable when a valuation date is unavailable;
  valuation gaps are preserved for bounded recalculation rather than treated as
  chronology ambiguity.
- Late action materialization uses the exact effective timestamp and reconstructs
  lot inventory through subsequent trades, so later buy lots retain their own
  quantity and cost basis.
- Frozen sell quantity is reconstructed from order chronology and the action
  chain rather than scaled from the current aggregate position.
- Existing corporate actions after a late action are replayed in sequence, with
  cash eligibility advanced through each event and per-lot cost basis preserved.
- Existing cash-ledger audit rows remain separate from corporate-action replay
  events, preventing duplicate cash application during NAV replay.
- Existing idempotency, processing metadata, affected range, precision, and
  bounded snapshot recalculation behavior are preserved.
- Corporate-action API/service fixtures now use imported holdings as explicit
  historical facts and post-baseline event times.

## Verification

- `uv run pytest test/paper_trading/domain/test_corporate_actions.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/api/test_corporate_actions_api.py -q`
  - **102 passed**, 1 existing Starlette/httpx deprecation warning.
- `uv run pytest test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_recalculation_service.py -q`
  - **29 passed, 3 skipped** (Task 3 regression suite).
- `tools/run_tests.sh test/paper_trading/services/test_corporate_action_service.py test/paper_trading/api/test_corporate_actions_api.py -q`
  - **47 passed** with PostgreSQL test database.
- `uv run ruff check ...` on all Task 5 changed source and test files: **passed**.
- `git diff --check`: **passed**.

The latest review fix was verified by the same focused suite, Task 3 regression,
PostgreSQL runner, scoped Ruff, and diff checks; all passed with the counts above.

## Simplification Review

The replay path and projection update were reviewed for safe simplification;
no further behavior-preserving reduction was worthwhile within Task 5 scope.

## Concerns

- The working tree includes only Task 5 source/test files plus this report.
- Two pre-existing analytics test files were already modified in the worktree;
  they were intentionally not touched or staged for Task 5.
- A pre-existing untracked `task-7-report.md` was also left untouched.
