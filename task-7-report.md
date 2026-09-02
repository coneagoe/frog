# Task 7 Report

## Scope

Task 7 changes are limited to `paper_trading/schemas/analytics.py`, `paper_trading/services/analytics_service.py`, `test/paper_trading/services/test_analytics_service.py`, `test/paper_trading/api/test_analytics_api.py`, and this report. No frontend, corporate-action service, corporate-action tests, or Task 5 report files are part of Task 7.

Task 7 replay commits are `a10e46f`, `6dcd630`, `eae607b`, `0bd8fd8`, `02a0f26`, and `8a38c92`; Task 5 corporate-action commits are deliberately excluded from this report.

## Implementation

- Analytics requires a shared `ReplayResult` from `NavSeriesBuilder`; repositories without the replay seam return `replay_unavailable` instead of using snapshot-only metrics.
- Performance and risk metrics consume the same replay-derived NAV series, excluding cash-flow replay points from return sampling.
- Missing and invalid initial points return `available=false` with distinct `missing_initial` and `invalid_initial` reasons; replay failures return `replay_unavailable`.
- Any invalid replay point, including a valid-quality point with a missing, non-positive, or non-finite NAV, surfaces `valuation_gap` for all performance/risk metrics and includes a diagnostic `valuation_gaps` entry; no NAV or return is synthesized across a gap.
- Any unresolved persisted valuation gap also returns an unavailable analytics payload; resolved gaps remain non-blocking.
- `AnalyticsUnavailableReason` is a closed enum covering replay, repair, valuation-gap, and insufficient-data discriminators.
- Replay-produced `NavPoint.nav` is the sole performance-series authority; persisted snapshots remain display/audit inputs only.
- Event series preserves snapshot, cash-flow, and corporate-action audit events and uses replay order where available.
- Snapshot API events now expose `quality`, `point_type`, `timezone`, `nav`, `share`, and the existing invalid reason fields.
- `AnalyticsUnavailableResponse.reason` accepts both the established migration enum and explicit analytics availability reasons.

## TDD Evidence

- Added a failing test proving analytics ignored a replay-only result before implementation.
- Added failing tests for replay-only NAV authority, gaps after multiple valid NAV points, structured availability reasons, and same-time replay ordering.
- Added real repository/builder integration coverage for a persistable invalid snapshot producing a shared replay gap, plus API JSON assertions for gap date, details, resolution, and ordering.
- Valid-quality invalid replay NAV values are covered by a narrow mocked builder contract because repository snapshot validation rejects non-finite values and the real market-valuation builder recomputes NAV from persisted assets/shares; that path still requires an HTTP 200 response.
- Opaque builder-exception coverage remains a separate mocked contract because no persisted repository state can represent an unavailable builder implementation.
- Implemented the shared replay path, then verified the new review-finding tests and the complete focused suites passed.

## Verification

- Focused analytics service/API tests: `89 passed, 1 warning`
- Scoped Ruff: passed for analytics service/schema and analytics service/API tests
- `git diff --check`: passed
- Warning: installed Starlette emits an `httpx` deprecation warning from `TestClient`; unrelated to Task 7.

## Review

The `simplify` review removed the duplicate trading-snapshot NAV validation and duplicate `@staticmethod` decorator while preserving the shared replay analytics boundary.

## Task 7 NAV date repair follow-up

### Status

Implemented and committed the focused creation-initial-cash replay fix.

### Changes

- Added a regression test proving an edited initial snapshot does not replay the matching creation deposit a second time.
- Added a replay-only creation-pair classification path that ignores mutable snapshot cash components while retaining immutable ledger allocation, timing, provenance, account, and snapshot identity checks.
- Preserved strict `_is_creation_initial_cash_event` behavior used by cash-service classification and repair paths, so incomplete or invalid allocations remain ordinary cash flows.

### Exact verification commands and results

- `uv run pytest test/paper_trading/services/test_nav_series.py::test_repository_builder_does_not_replay_creation_cash_again_after_initial_snapshot_edit test/paper_trading/services/test_snapshot_recalculation_service.py::test_recalculation_preserves_initial_cash_components_and_identity test/paper_trading/services/test_cash_service.py::test_deposit_with_initial_cash_note_is_replayed_as_ordinary_cash_flow test/paper_trading/services/test_cash_service.py::test_initial_cash_note_with_incomplete_allocation_is_not_creation_event test/paper_trading/services/test_cash_service.py::test_initial_cash_note_with_invalid_allocation_is_not_creation_event test/paper_trading/services/test_cash_service.py::test_initial_cash_note_invalid_allocation_reaches_replay_repair_path` — **12 passed**.
- `uv run pytest test/paper_trading/services/test_snapshot_recalculation_service.py` — **20 passed, 2 skipped**.
- `uv run pytest test/paper_trading/services/test_nav_series.py test/paper_trading/storage/test_repository.py` — **140 passed, 6 skipped, 4 failed**. The four failures are unrelated pre-existing provenance/SQLite rollback tests: `test_unproven_persisted_*` and `test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails`.
- `git diff --check` — **passed** before commit.

### Commit

- `80fdcd0` — `Fix creation cash replay after snapshot edits`

### Concerns

- Full repository/NAV module coverage still reports the four unrelated baseline failures listed above.
- PostgreSQL-specific tests were skipped because `TEST_POSTGRESQL_URL` was unavailable.
