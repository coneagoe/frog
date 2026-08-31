# Task 7 Report

## Scope

Task 7 changes are limited to analytics schemas/service and analytics service/API tests. No frontend, corporate-action service, or Task 8 files were modified. Existing external modifications in `paper_trading/services/corporate_action_service.py` and its test were left untouched and unstaged.

## Implementation

- Analytics requires a shared `ReplayResult` from `NavSeriesBuilder`; repositories without the replay seam return `replay_unavailable` instead of using snapshot-only metrics.
- Performance and risk metrics consume the same replay-derived NAV series, excluding cash-flow replay points from return sampling.
- Missing and invalid initial points return `available=false` with distinct `missing_initial` and `invalid_initial` reasons; replay failures return `replay_unavailable`.
- Any invalid replay point surfaces `valuation_gap` for all performance/risk metrics; no NAV or return is synthesized across a gap.
- Any unresolved persisted valuation gap also returns an unavailable analytics payload; resolved gaps remain non-blocking.
- `AnalyticsUnavailableReason` is a closed enum covering replay, repair, valuation-gap, and insufficient-data discriminators.
- Replay-produced `NavPoint.nav` is the sole performance-series authority; persisted snapshots remain display/audit inputs only.
- Event series preserves snapshot, cash-flow, and corporate-action audit events and uses replay order where available.
- Snapshot API events now expose `quality`, `point_type`, `timezone`, `nav`, `share`, and the existing invalid reason fields.
- `AnalyticsUnavailableResponse.reason` accepts both the established migration enum and explicit analytics availability reasons.

## TDD Evidence

- Added a failing test proving analytics ignored a replay-only result before implementation.
- Added failing tests for replay-only NAV authority, gaps after multiple valid NAV points, structured availability reasons, and same-time replay ordering.
- Implemented the shared replay path, then verified the new review-finding tests and the complete focused suites passed.

## Verification

- Focused analytics service/API tests: `84 passed, 1 warning`
- Scoped Ruff: passed for analytics service/schema and analytics service/API tests
- `git diff --check`: passed
- Warning: installed Starlette emits an `httpx` deprecation warning from `TestClient`; unrelated to Task 7.

## Review

The `simplify` review found no safe simplification worth applying without changing the shared replay analytics boundary.
