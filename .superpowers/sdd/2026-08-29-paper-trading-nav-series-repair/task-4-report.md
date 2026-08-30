# Task 4 Report: Route Account Creation and Cash Flows Through Replay

## Status

Complete for the recovered Task 4 scope.

## Changes

- Account creation continues to validate positive initial cash and fee values,
  and the existing repository transaction creates one immutable `initial_cash`
  deposit ledger event plus one valid initial snapshot at NAV 1 with timezone-
  aware canonical UTC provenance.
- `CashService.deposit()` and `CashService.withdraw()` now persist the cash
  ledger event first, then use `NavSeriesBuilder` and
  `SnapshotRecalculationService` to replay from the cash flow date through the
  latest existing trading snapshot when derived snapshots exist.
- The account NAV state is synchronized from the replay result rather than
  applying an unsupported direct adjustment. Backdated cash flows therefore
  rebuild later snapshots while preserving Decimal quantities and persisted
  rounding residuals.
- Account cash endpoints provide market data only when the account has
  positions, avoiding unnecessary provider initialization for cash-only
  accounts while allowing valuation-backed replay for held assets.
- Added focused service coverage for a backdated deposit and its rebuilt
  snapshot; existing account creation, cash-flow, residual, timezone, and API
  tests remain covered.
- No matching, settlement, or Task 5/6/7/8 files were modified.

## Verification

Focused tests:

```text
uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py -q
80 passed, 5 warnings
```

Scoped Ruff:

```text
uv run ruff check paper_trading/services/cash_service.py paper_trading/services/account_service.py paper_trading/storage/repository.py paper_trading/api/routers/accounts.py paper_trading/schemas/accounts.py test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py
All checks passed.
```

`git diff --check` passed.

## Concerns

- Cash-flow replay for an account with existing positions requires a supplied
  market-data provider; if it cannot be provided, the operation errors after
  the surrounding transaction can roll back the newly inserted ledger event.
- The API currently obtains the market-data provider directly in the cash
  route only when positions exist; the existing test fixture has no PostgreSQL
  service, so no provider is initialized for its cash-only account paths.
- Full repository-wide tests and PostgreSQL integration tests were not run;
  they are outside the assigned focused validation.

## Review Follow-up

- Forward-dated cash flows now recalculate through `max(latest_snapshot_date,
  cash_flow_date)`, avoiding an invalid reversed range and materializing the
  new derived trading date.
- Replay events now carry persisted pricing NAV, share delta, and rounding
  residual. Cash-flow replay uses the persisted share delta and validates the
  residual identity at residual precision instead of recomputing and dropping
  the ledger allocation.
- Account NAV/share/cumulative state is taken from the final replay projection,
  including when trading snapshots exist; failed replay raises before the
  request transaction can commit the ledger event.
- Added exact-one initial ledger/snapshot field and provenance assertions,
  backdated withdrawal coverage, forward-dated deposit coverage, and persisted
  residual consistency coverage.

Review follow-up verification:

```text
uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_account_service.py test/paper_trading/api/test_accounts_api.py -q
83 passed, 5 warnings

uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_recalculation_service.py -q
54 passed, 3 skipped

Scoped Ruff: All checks passed.
```

## Final Important Finding Follow-up

- `_is_creation_initial_cash_event()` now performs structural checks before
  Decimal conversion and catches conversion/arithmetic errors. A normal
  `note="initial_cash"` ledger with missing or invalid allocation fields safely
  returns `False`, so it remains an ordinary replay event and reaches the
  unified allocation repair validation.
- Added regression coverage for missing `net_asset_value`, `share_delta`, or
  `rounding_residual`, plus invalid allocation strings.

Verification:

```text
Task 4 focused: 119 passed, 5 warnings
Task 3 regression: 54 passed, 3 skipped
PostgreSQL runner: 54 passed
Scoped Ruff: All checks passed.
git diff --check: passed
```

## Review Follow-up 2

- Initial ledger suppression now requires a matching creation snapshot,
  canonical timestamp/trade date, initial amount/NAV/share allocation, and zero
  residual; an ordinary deposit with `note="initial_cash"` remains replayable.
- Withdrawals calculate available cash, shares, and pricing NAV from replay
  facts strictly before `occurred_at`, so later deposits cannot authorize a
  backdated withdrawal.
- Deposit and withdrawal operations wrap ledger insertion and replay in a
  service-level savepoint. Replay or materialization errors roll back the
  inserted ledger even when a direct caller catches the exception and commits.
- Replay rejects persisted `share_delta` without `rounding_residual` as a
  repair-required legacy allocation rather than silently recomputing it.
- Added regression coverage for ordinary initial-note deposits, future cash
  followed by historical withdrawal, service rollback, missing residual,
  initial identity fields, and prior backdated/forward cash flows.

Verification:

```text
Task 4 focused: 87 passed, 5 warnings
Task 3 regression: 54 passed, 3 skipped
Scoped Ruff: All checks passed.
```

## Review Follow-up 3

- Backdated withdrawals now reject a non-valid event-before-`occurred_at`
  replay point instead of relying only on cash and share fields.
- Cash-flow allocation facts now require persisted `pricing_nav`, `share_delta`,
  and `rounding_residual` together. Any absent element is repair-required.
- The cash-flow boundary passes a rollback-shielded caller session to snapshot
  recalculation. Its outer savepoint still rolls back the failed cash ledger,
  while unrelated caller transaction changes remain commit-able.
- Added coverage for invalid prior replay state, each missing allocation member,
  and recalculation failure preserving caller-owned changes.

Verification:

```text
Task 4 focused: 92 passed, 5 warnings
Task 3 regression: 54 passed, 3 skipped
PostgreSQL runner: 27 passed
Scoped Ruff: All checks passed.
```

## Final Review Follow-up

- `NavSeriesReplay` now rejects partial or malformed persisted allocation
  triples. `pricing_nav` must be positive finite Decimal; `share_delta` and
  `rounding_residual` must be finite Decimal; their residual identity must
  match. Completely allocation-free legacy replay events retain the existing
  compatibility path, while Task 4 cash operations reject them for repair.
- Backdated withdrawal authorization rejects any invalid event-before-time
  projection and uses the final valid replay point's NAV for pricing. A
  persisted non-default snapshot NAV is retained only for an established
  valuation-only legacy boundary.
- Added malformed `NaN`, infinity, and non-Decimal allocation coverage for all
  allocation fields. Existing savepoint coverage continues to verify that
  recalculation failures preserve caller-owned transaction work.

Verification:

```text
Task 4 focused: 104 passed, 5 warnings
Task 3 regression: 54 passed, 3 skipped
PostgreSQL runner: 39 passed
Scoped Ruff: All checks passed.
```

## Allocation Type Follow-up

- Persisted cash allocation facts now accept only native finite `Decimal`
  values. Numeric strings, floats, integers, `NaN`, and infinities are rejected
  before any fallback pricing or share calculation can occur.
- Added coverage for every allocation field with convertible strings, float,
  and integer values, preserving existing invalid-state withdrawal, savepoint,
  initial-event identity, and forward/backdated flow coverage.

Verification:

```text
Task 4 focused: 113 passed, 5 warnings
Task 3 regression: 54 passed, 3 skipped
PostgreSQL runner: 48 passed
Scoped Ruff: All checks passed.
```
