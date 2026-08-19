# Partial Paper Schema Enum Migration Compatibility

## Problem Statement

As an operator running PostgreSQL enum governance, I need the paper-trading
migration to support reduced legacy schemas used by governed storage bootstrap
and migration tests. Those schemas can retain enum-governed columns while
omitting the business-key columns needed for paper-trading market-qualified
identity. The migration currently tries to create, verify, query, or restore
keys using absent columns and aborts the unified `migrate_enums` workflow.

## Solution

The paper-trading enum-governance adapter will apply market-qualified key
operations only when the table contains every column required by that key. A
reduced legacy schema will still receive enum conversion, `market` backfill when
applicable, and enum rollback; it will skip only the business-key operation that
cannot be inferred safely. A complete paper-trading schema will retain its
existing strict market-qualified identity contract.

## User Stories

1. As a PostgreSQL operator, I want unified enum governance to convert a reduced legacy schema, so that storage bootstrap does not fail on unrelated paper-trading key DDL.
2. As a PostgreSQL operator, I want unified enum governance to roll back a reduced legacy schema, so that enum recovery does not fail on unavailable business-key columns.
3. As a paper-trading operator, I want a complete `paper_positions` schema to retain `(account_id, market, symbol)` uniqueness, so that same-symbol positions remain isolated by market.
4. As a paper-trading operator, I want a complete `daily_bar_diagnostics` schema to retain its market-qualified business key, so that diagnostics from separate markets cannot overwrite one another.
5. As a migration operator, I want legacy-key collision detection to run only where its full key exists, so that downgrade safety checks remain meaningful and executable.
6. As a migration operator, I want rollback to restore legacy keys only where their full column sets exist, so that reduced schemas can complete enum rollback without fabricated DDL.
7. As a developer, I want enum migration verification to ignore only inapplicable keys, so that incomplete fixtures remain supported without weakening validation for production schemas.
8. As a developer, I want the preconverted `paper_market` fixture to include `a_share`, `hk_connect`, and `etf`, so that it matches the persisted market enum contract.
9. As a maintainer, I want focused adapter tests and unified governance tests to cover this behavior, so that changes at either migration entrypoint cannot reintroduce missing-column failures.

## Implementation Decisions

- The existing paper-trading enum-governance adapter remains the owner of `paper_market`, market-column backfill, and market-qualified key lifecycle behavior.
- The existing unified `migrate_enums` entrypoint remains the highest-level integration seam; no new migration API, adapter, or feature flag is introduced.
- The paper-positions market-qualified key lifecycle includes upgrade, verification, legacy-key collision detection, and rollback restoration. Every operation runs only when `account_id`, `market`, and `symbol` are present.
- The daily-bar-diagnostics market-qualified key lifecycle has the same four operations. Every operation runs only when `business_date`, `market`, `stock_id`, and `adjust` are present.
- A missing required key column does not make an otherwise enum-governed table incompatible. It skips only the associated market-qualified key operation.
- Complete schemas continue to require the current market-qualified constraints and continue to reject rollback when cross-market rows would collide under a legacy key.
- Enum label validation remains strict. Fixtures representing a preconverted market enum use the current persisted labels `a_share`, `hk_connect`, and `etf`.
- This does not alter the ownership boundary: Storage enum governance continues to own daily-bar diagnostic adjustment, classification, and provider-outcome checks; Paper Trading owns `paper_market` and its market-qualified diagnostic identity.

## Testing Decisions

- The highest behavioral seam is the existing unified `migrate_enums(connection)` workflow against isolated PostgreSQL schemas. Tests assert observable migration and rollback outcomes, rather than private helper calls or emitted SQL implementation details.
- Focused paper-trading adapter migration tests cover reduced `paper_positions` and reduced `daily_bar_diagnostics` schemas during apply, verify, and rollback. They prove enum behavior completes and inapplicable market-qualified constraints are neither required nor restored.
- Unified enum-governance tests cover the same reduced-schema behavior through the full Paper Trading, Monitor, and Storage adapter ordering.
- Existing complete-schema migration tests remain prior art and regression coverage for market-qualified key upgrade, verification, collision rejection, and rollback restoration.
- PostgreSQL integration tests use the repository test runner so the isolated `test_db` service and `TEST_POSTGRESQL_URL` are available.

## Out of Scope

- Changing the paper-trading market-qualified identity contract for complete schemas.
- Adding or removing persisted market enum labels beyond aligning the stale test fixture with the existing `etf` label.
- Altering Paper Trading API, CLI, repository, matching, valuation, or market-data behavior.
- Relaxing enum value, default, type, dependency, index, or Storage-governed diagnostic validation.
- Creating missing business-key columns or synthesizing unique constraints for reduced legacy schemas.

## Further Notes

This compatibility behavior is intentionally symmetric: the complete-key guard
applies to migration upgrade, verification, rollback collision detection, and
legacy-key restoration. It preserves the contract established by the
market-qualified identity work while allowing older or intentionally minimal
governed schemas to participate in enum migration safely.
