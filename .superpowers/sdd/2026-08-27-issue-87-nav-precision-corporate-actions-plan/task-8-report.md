# Task 8 Verification and Fix Report

## Summary

Fixed the issue-87 verification failures. Public paper-trading responses now
retain the approved display precision while storage and internal calculations
keep 12-decimal values: money is serialized to four decimal places and NAV,
share, and share-delta values to six decimal places. The snapshot response and
nested cash-ledger response are covered at their response-schema boundaries.

Analytics now converts persisted corporate-action strings through
`CorporateActionType` before constructing the typed analytics event. The
reported nullable-Decimal and test-fixture typing issues were fixed with
explicit test narrowing and a typed test cast.

## Files

- `paper_trading/schemas/accounts.py`
- `paper_trading/schemas/snapshots.py`
- `paper_trading/services/analytics_service.py`
- `test/paper_trading/storage/test_repository.py`
- `test/paper_trading/services/test_analytics_service.py`

## Validation

Command:

```text
uv run pytest test/paper_trading/api/test_accounts_api.py test/paper_trading/services/test_analytics_service.py test/paper_trading/storage/test_repository.py
```

Result: 181 passed, 5 warnings. The warnings are existing Starlette/AnyIO
deprecation warnings.

Command:

```text
uv run ruff check paper_trading/schemas/accounts.py paper_trading/schemas/snapshots.py paper_trading/services/analytics_service.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_analytics_service.py
```

Result: passed.

Command:

```text
uv run pre-commit run --files paper_trading/schemas/accounts.py paper_trading/schemas/snapshots.py paper_trading/services/analytics_service.py test/paper_trading/storage/test_repository.py test/paper_trading/services/test_analytics_service.py
```

Result: all hooks passed, including Ruff format, Ruff, and mypy.

Command:

```text
uv run mypy
```

Result: issue-87 source and test typing errors are resolved. The command still
reports 12 pre-existing missing or untyped third-party imports in nine
`tools/*` files (`plotly`, `dash`, and `swifter`); those files were not changed.

## Simplify Review

Completed a targeted simplification review of the touched code. No safe
simplification was identified: the response serializers represent distinct
public precision contracts, and the enum conversion and test type narrowings
are already minimal and behavior-preserving.

## Scope

The plan and unrelated documentation were not modified.

## Final Navigation Precision Fix

- Changed the AccountsPage detail workspace condition from `selectedAccountId`
  to the derived `selectedAccount` object. A stale ID can survive one render
  after the account list refreshes to empty; the current account object cannot.
- Strengthened the last-account deletion regression name and assertion to cover
  the stale-detail render path while retaining the existing valid re-selection
  and corporate-action refresh coverage.
- No backend, docs, plan, or unrelated files were modified. This report is the
  only documentation file updated.

## Final Validation

Exact focused AccountsPage command:

```text
npm test -- features/accounts/accounts-page.test.tsx
```

Exact output:

```text
npm notice run paper-trading-frontend@0.1.0 test
npm notice run vitest run --passWithNoTests features/accounts/accounts-page.test.tsx
The CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.

 RUN  v2.1.9 /data/frog/.worktrees/issue-87-nav-precision/frontend/paper-trading

 ✓ features/accounts/accounts-page.test.tsx (42 tests) 11335ms

 Test Files  1 passed (1)
      Tests  42 passed (42)
   Start at  00:29:47
   Duration  13.60s (transform 657ms, setup 126ms, collect 887ms, tests 11.34s, environment 677ms, prepare 115ms)
```

Exact Task 6 focused frontend command:

```text
npm run test -- lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx
```

Exact output:

```text
npm notice run paper-trading-frontend@0.1.0 test
npm notice run vitest run --passWithNoTests lib/api-client.test.ts features/accounts/corporate-action-modal.test.tsx features/accounts/accounts-page.test.tsx features/trading/trading-tables.test.tsx features/analytics/asset-chart.test.tsx features/analytics/analytics-page.test.tsx
The CJS build of Vite's Node API is deprecated. See https://vite.dev/guide/troubleshooting.html#vite-cjs-node-api-deprecated for more details.

 RUN  v2.1.9 /data/frog/.worktrees/issue-87-nav-precision/frontend/paper-trading

 ✓ features/accounts/accounts-page.test.tsx (42 tests) 19350ms
 ✓ features/analytics/analytics-page.test.tsx (10 tests) 2137ms
 ✓ features/trading/trading-tables.test.tsx (26 tests) 3140ms
 ✓ lib/api-client.test.ts (19 tests) 124ms
 ✓ features/accounts/corporate-action-modal.test.tsx (10 tests) 8657ms
 ✓ features/analytics/asset-chart.test.tsx (4 tests) 171ms

 Test Files  6 passed (6)
      Tests  111 passed (111)
   Start at  00:30:32
   Duration  53.28s (transform 2.10s, setup 1.57s, collect 4.22s, tests 33.58s, environment 8.51s, prepare 1.43s)
```

Exact lint command:

```text
npm run lint
```

Exact output:

```text
npm notice run paper-trading-frontend@0.1.0 lint
npm notice run eslint .
```

Lint exited successfully with no warnings or errors.

Exact diff check:

```text
git diff --check
```

Result: exited successfully with no output.

## Final Self-Review

- The live-object gate removes the transient deleted-account workspace without
  changing selection repair, manual account selection, URL selection, or
  corporate-action completion refresh behavior.
- The regression test covers the last-account refresh result and asserts both
  stale detail headings are absent.
- Targeted simplification review found no further safe simplification: the
  derived `selectedAccount` directly expresses the required invariant.
- No remaining blockers for this frontend fix. Vitest emits the existing Vite
  CJS API deprecation notice only.
