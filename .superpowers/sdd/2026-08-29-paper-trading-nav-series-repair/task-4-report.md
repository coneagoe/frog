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
