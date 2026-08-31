# Task 7 Report

## Scope

Task 7 changes are limited to analytics schemas/service and analytics service/API tests. No frontend, corporate-action service, or Task 8 files were modified. Existing external modifications in `paper_trading/services/corporate_action_service.py` and its test were left untouched and unstaged.

## Implementation

- Analytics now builds a shared `ReplayResult` through `NavSeriesBuilder` when the repository exposes replay events.
- Performance and risk metrics consume the same replay-derived NAV series, excluding cash-flow replay points from return sampling.
- Invalid initial points return `available=false` with `missing_initial`; replay failures return an explicit unavailable reason.
- Invalid valuation points stop the contiguous series and surface `valuation_gap`; no NAV or return is synthesized across a gap.
- Persisted snapshot NAV remains authoritative for compatible snapshot data while replay supplies ordering and quality.
- Event series preserves snapshot, cash-flow, and corporate-action audit events and uses replay order where available.
- Snapshot API events now expose `quality`, `point_type`, `timezone`, `nav`, `share`, and the existing invalid reason fields.
- `AnalyticsUnavailableResponse.reason` accepts both the established migration enum and explicit analytics availability reasons.

## TDD Evidence

- Added a failing test proving analytics ignored a replay-only result before implementation.
- Added a failing test proving a replay valuation gap was incorrectly treated as insufficient data before implementation.
- Implemented the shared replay path, then verified both tests passed.

## Verification

- Focused analytics service/API tests: `63 passed, 1 warning`
- Scoped Ruff: passed for analytics service/schema and analytics service/API tests
- `git diff --check`: passed
- Warning: installed Starlette emits an `httpx` deprecation warning from `TestClient`; unrelated to Task 7.

## Review

The `simplify` review found no safe simplification worth applying without changing the shared replay/legacy compatibility boundary.
