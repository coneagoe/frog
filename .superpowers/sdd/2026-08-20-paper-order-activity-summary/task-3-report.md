# Task 3 Report: Render Activity Summaries in the Frontend

## Summary

Migrated the paper-trading frontend analytics to the new activity contract: removed the legacy
`ActivityBucket` daily/weekly/monthly bucket tables, added `ActivitySummary`/`ActivityAnalytics`
types matching the backend API (`paper_trading/schemas/analytics.py`), and rendered coverage plus
Daily/Weekly/Monthly average-order summary cards with an explicit unavailable state when
`activity` is null. Execution, Trade Quality, and Risk & Drawdown sections are untouched.

## Changes

### `frontend/paper-trading/lib/types.ts`
- Deleted `ActivityBucket`.
- Added `ActivitySummary` (`total_orders`, `successful_orders`, `failed_orders` — all `string`,
  matching the backend's serialized `Decimal`) and `ActivityAnalytics` (`coverage_start`,
  `coverage_end`, `daily`, `weekly`, `monthly`).
- `AnalyticsResponse`: replaced `activity_daily`/`activity_weekly`/`activity_monthly` lists with
  `activity: ActivityAnalytics | null`. Verified this matches the backend pydantic schema exactly.

### `frontend/paper-trading/features/analytics/analytics-tables.tsx`
- Removed `ActivityTable` and the `ActivityBucket` import. `DataTable`/`Column` imports stay
  because Reject Reasons and Round Trips tables still use them (only the Activity usage became
  obsolete, per brief).
- Rewrote `AnalyticsActivitySection`:
  - `analytics?.activity` null (or analytics missing) → `<div className="muted">Activity unavailable</div>`,
    no summary units rendered.
  - Otherwise renders an `Activity Coverage` header using the existing `panel__header` pattern
    (h3 label + muted range), with each coverage date formatted via `formatDate(...)` in its own
    `<span>` so tests and assistive tech see the exact dates.
  - Three stable units (Daily, Weekly, Monthly) rendered in fixed order, each an `<h3>` followed
    by the existing `summary-grid` + `MetricCard` pattern showing `Total Orders`,
    `Successful Orders`, `Failed Orders` as `formatQuantity(Number(summary.<field>))`.
- `AnalyticsExecutionSection`, `AnalyticsTradeQualitySection`, `AnalyticsRiskSection` unchanged.

### `frontend/paper-trading/features/analytics/analytics-page.test.tsx`
- Fixture: replaced the three legacy activity lists with the brief's `activity` object
  (coverage 2026-08-28 → 2026-09-10, string Decimal averages).
- New test "renders activity coverage and average order summaries": asserts `Activity Coverage`,
  both dates, `Daily`/`Weekly`/`Monthly`, exactly 3 each of `Total Orders`/`Successful Orders`/
  `Failed Orders`, and that legacy `Period` and `Trades` headers are absent.
- New test "shows activity as unavailable when no activity summary is returned": mocks
  `activity: null`, asserts `Activity unavailable` and that no coverage, unit labels, summary
  labels, or formatted fixture values (`0.286`, `1.333`) appear.
- Retained existing assertions for Overview, Execution, Trade Quality, Risk & Drawdown, reject
  reason (`Insufficient Cash`), and round-trip data (`000001.SZ`).

## Design decisions

- Reused existing UI primitives only: `panel__header`, `h3` subsection headings (same as
  "Reject Reasons"/"Round Trips"), `summary-grid`, and `MetricCard`. No new CSS, keeping the
  panel consistent with the rest of the Analytics page.
- Coverage dates rendered as separate spans inside the muted range so each formatted date is an
  individually addressable text node.
- Fixed-order `units` array guarantees the Daily/Weekly/Monthly sequence is stable regardless of
  backend serialization order.
- The old `grid grid--two` layout was dropped with the tables; `grid--two` CSS remains in use by
  the accounts page, so no stylesheet changes were needed.

## Verification

### Step 2 — failing tests first (expected FAIL)
`npm test -- --run features/analytics/analytics-page.test.tsx`
```
Test Files  1 failed (1)
     Tests  2 failed | 3 passed (5)
```
Both new tests failed ("Activity Coverage" / "Activity unavailable" not found); the 3 legacy
tests still passed.

### Step 5 — after implementation (PASS)
`npm test -- --run features/analytics/analytics-page.test.tsx`
```
✓ features/analytics/analytics-page.test.tsx (5 tests) 539ms
Test Files  1 passed (1)
     Tests  5 passed (5)
```

`npm run lint`
```
✖ 2 problems (0 errors, 2 warnings)
```
Both warnings are pre-existing in files not touched by this task
(`features/accounts/accounts-page.test.tsx` unused `withdrawCashMock`,
`features/analytics/analytics-summary.tsx` unused `MoneyText`).

`npm run build` — PASS (compiled, lint + type-check clean, all 9 routes generated).

Extra check — full frontend suite: `npm test` → 15 files, 178 tests, all passed.

## Commit

```
57bd299 feat: show paper order activity summaries
```
Files: `frontend/paper-trading/lib/types.ts`,
`frontend/paper-trading/features/analytics/analytics-tables.tsx`,
`frontend/paper-trading/features/analytics/analytics-page.test.tsx`
(3 files, +84/−31).

## Simplify review

The `simplify` skill is not present under `.agents/skills/` in this worktree, so the review was
performed manually. Findings: the touched code is already minimal and follows neighboring
patterns; the only candidate (driving the three metric cards from a field/label map) would add
indirection without improving clarity and would deviate from the brief's prescribed explicit
structure. No change worth making.

## update_doc review

The only docs referencing `activity_daily`/`ActivityBucket` are this issue's SDD plan/spec under
`docs/superpowers/`, which are orchestrator-owned and excluded by the task scope ("do not modify
backend or docs"). No product docs are affected by this frontend-only change.

## Concerns

1. **node_modules symlink (untracked)**: the worktree had no `frontend/paper-trading/node_modules`.
   `package-lock.json` is byte-identical to the main checkout, so I symlinked
   `/data/frog/frontend/paper-trading/node_modules` to run tests/lint/build. It shows as untracked
   (`?? frontend/paper-trading/node_modules`) because this repo's `.gitignore` lacks a
   `node_modules` entry; it was not committed. Remove it if a clean `npm ci` is preferred.
2. **`.gitignore` `lib/` pattern**: the root `.gitignore` `lib/` rule (Python-venv oriented)
   matches `frontend/paper-trading/lib`, so `git add` on `lib/types.ts` printed an ignored-path
   warning and exited non-zero even though the tracked file was staged. Commit succeeded on retry.
   Not changing repo-wide ignore rules within this task's scope.
3. **Pre-existing lint warnings** (listed above) remain; out of scope.
4. `formatQuantity` rounds to 3 fraction digits (e.g. `0.285714` → `0.286`); this is the brief's
   prescribed formatting and matches how other counts render.
