# Task 7 Report

## Scope

Task 7 changes are limited to `paper_trading/services/analytics_service.py`, `test/paper_trading/services/test_analytics_service.py`, `test/paper_trading/api/test_analytics_api.py`, and this report. No frontend, schema, corporate-action service, corporate-action tests, or Task 5 report files are part of Task 7.

Task 7 replay commits are `a10e46f`, `6dcd630`, `eae607b`, `0bd8fd8`, `02a0f26`, and `8a38c92`; Task 5 corporate-action commits are deliberately excluded from this report.

## Implementation

- Analytics requires a shared `ReplayResult` from `NavSeriesBuilder`; repositories without the replay seam return `replay_unavailable` instead of using snapshot-only metrics.
- Performance and risk metrics consume the same replay-derived NAV series, excluding cash-flow replay points from return sampling.
- Missing and invalid initial points return `available=false` with distinct `missing_initial` and `invalid_initial` reasons. A `NavSeriesBuilder.build()` `ValueError` returns `replay_unavailable`; other exceptions are not normalized by this contract.
- Any invalid replay point, including a valid-quality point with a missing, non-positive, or non-finite NAV, surfaces `valuation_gap` with an `invalid_nav` diagnostic for all performance/risk metrics; no NAV or return is synthesized across a gap.
- Any unresolved persisted valuation gap also returns an unavailable analytics payload; resolved gaps remain non-blocking.
- `AnalyticsUnavailableReason` is a closed enum covering replay, repair, valuation-gap, and insufficient-data discriminators.
- Replay-produced `NavPoint.nav` is the sole performance-series authority; persisted snapshots remain display/audit inputs only.
- Event series preserves snapshot, cash-flow, and corporate-action audit events and uses replay order where available.
- Snapshot API events now expose `quality`, `point_type`, `timezone`, `nav`, `share`, and the existing invalid reason fields.
- `AnalyticsUnavailableResponse.reason` accepts both the established migration enum and explicit analytics availability reasons.

## TDD Evidence

- Added a failing test proving analytics ignored a replay-only result before implementation.
- Added failing tests for replay-only NAV authority, gaps after multiple valid NAV points, structured availability reasons, and same-time replay ordering.
- Added real repository/API coverage for cash-only replay, backdated cash flow, same-time cash/corporate-action ordering, and unresolved/resolved persisted gaps.
- Added a route-level mocked-builder contract test verifying HTTP 200 and the complete invalid-replay-NAV valuation-gap JSON payload.
- Implemented the shared replay path, then verified the new review-finding tests and the complete focused suites passed.

## Verification

- Focused analytics service/API tests: `89 passed, 1 warning`
- Scoped Ruff: passed for analytics service and analytics service/API tests
- `git diff --check`: passed
- Warning: installed Starlette emits an `httpx` deprecation warning from `TestClient`; unrelated to Task 7.

## Review

The `simplify` review removed the duplicate trading-snapshot NAV validation and duplicate `@staticmethod` decorator while preserving the shared replay analytics boundary.
