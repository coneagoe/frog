# ETF Account Fees Market Contract Final Fix Report

## Scope

This corrective wave addresses the final review findings for issue #44 only.
It preserves existing A-share and Hong Kong Connect behavior and adds no ETF
eligibility, data, lot, tick, settlement, or matching-range behavior.

## Changes

- Added `etf` to `paper_trading_cli.py order create --market` choices and
  regression coverage that proves it is forwarded to the API client.
- Validated `account create --etf-commission-rate` with the existing local
  non-negative decimal parser. Negative values now return the CLI validation
  exit code before invoking the API client.
- Extended the governed PostgreSQL enum rollback path to handle the additive,
  nullable `paper_accounts.etf_commission_rate` column.
- The rollback preflight accepts a missing column for legacy schemas. If the
  column is present, it must be nullable `NUMERIC(20, 8)` with no default and
  no external catalog dependencies. Otherwise rollback aborts without dropping
  the column. A safe column is removed only after all existing enum and legacy
  key rollback preflights succeed.
- Added PostgreSQL lifecycle coverage for safe column removal and incompatible
  column rollback refusal. These tests use the existing `TEST_POSTGRESQL_URL`
  fixture and skip when no PostgreSQL test database is configured.
- Added direct order-flow tests proving a zero ETF commission override reserves
  no buy commission and persists no fill commission.
- Removed the unreachable ETF fee branch from
  `_place_historical_a_share_order`; that method is called only for
  `Market.A_SHARE`.

## Verification

- `uv run pytest test/tools/test_paper_trading_cli.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_enum_migration.py test/storage/test_storage_db.py -q`
  - `354 passed, 30 skipped`
- `uv run ruff format --check` and `uv run ruff check` on all modified Python
  files
  - passed
- `uv run mypy paper_trading/services/order_service.py paper_trading/storage/enum_migration.py`
  - passed; mypy emitted its existing unused-module-override configuration note

## Limits And Concerns

- `TEST_POSTGRESQL_URL` was not configured in this environment. The added
  PostgreSQL upgrade/rollback lifecycle tests were collected but skipped, so
  live PostgreSQL DDL execution remains to be confirmed in an environment that
  provides that database.
- The rollback deliberately does not remove an additive ETF commission column
  when its nullability, numeric shape, default, or dependencies are unsafe.
