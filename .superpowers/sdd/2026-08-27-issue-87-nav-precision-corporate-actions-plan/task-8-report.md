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

## Final-Review Fix Wave

This fix wave addresses the remaining code-addressable issue #87 findings:

- Widened position, lot, order, trade, validity, and round-trip accounting
  fields to `Numeric(30, 12)` in the ORM. PostgreSQL startup upgrades widen
  these fields monotonically, and SQLite startup upgrades rebuild only tables
  whose target columns are below the contract while preserving values and
  indexes. Existing schemas with higher precision are not narrowed.
- Added `PaperTradingRepository.get_cash_available_internal()`, which returns
  the quantized 12-decimal ledger total. Corporate-action eligibility and
  accounting use this path; the existing `get_cash_available()` display/API
  path remains four-decimal.
- Normalized SQLite repository `start_at` and `end_at` corporate-action
  filters to UTC before comparison and rejected naive bounds.
- Enforced exact action-specific parameter sets in the domain validator and
  invoked that validation in `CorporateActionService` before idempotency
  lookup, preserving canonical replay behavior for valid requests.
- Updated the precision documentation to include position and lot cost values
  in the 12-decimal scope without changing display precision.

## Fix-Wave Tests Added

- Direct domain tests for unexpected corporate-action parameters.
- Direct service tests for sub-display cash precision and validation ordering
  relative to idempotency lookup.
- SQLite repository test for non-UTC offset bounds against UTC-persisted rows.
- SQLite migration test for position and lot precision widening and value
  preservation.

## Fix-Wave Validation

Command:

```text
uv run pytest test/paper_trading/domain/test_corporate_actions.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/storage/test_corporate_action_migration.py test/paper_trading/storage/test_repository.py -q
```

Exact result:

```text
140 passed, 2 skipped in 75.15s (0:01:15)
```

The two skipped tests are PostgreSQL-only tests skipped because
`TEST_POSTGRESQL_URL` is unavailable in this environment.

Command:

```text
uv run ruff format --check storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/services/corporate_action_service.py paper_trading/domain/corporate_actions.py storage/storage_db.py test/paper_trading/domain/test_corporate_actions.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py && uv run ruff check storage/model/paper_trading.py paper_trading/storage/repository.py paper_trading/services/corporate_action_service.py paper_trading/domain/corporate_actions.py storage/storage_db.py test/paper_trading/domain/test_corporate_actions.py test/paper_trading/services/test_corporate_action_service.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py
```

Exact result:

```text
9 files already formatted
All checks passed!
```

Command:

```text
git diff --check
```

Result: passed with no output.

Command:

```text
git status --short && git diff --stat
```

Result: ten issue-owned implementation, test, and documentation files are
modified; the approved plan and unrelated subsystems are unchanged.

## Simplify Self-Review

The required `simplify` skill was checked for under
`.agents/skills/**/simplify/**` and is not installed in this worktree, so it
could not be invoked. Manual self-review found no additional safe
behavior-preserving simplification: the internal cash accessor deliberately
separates accounting precision from display precision, the SQLite migration
is isolated behind monotonic target checks, and exact parameter validation is
shared by domain and service paths.

## Remaining Blockers

PostgreSQL integration migration coverage was not runnable because the
required `TEST_POSTGRESQL_URL` is unavailable. No other blocker was observed
in the scoped fix-wave validation.

## SQLite Migration Safety Follow-up

Implemented the remaining issue #87 SQLite migration blockers while preserving
the approved integer-backed position and lot quantity model. SQLite numeric
upgrades now compare both precision and scale, rebuild only when either target
capability increases, and preserve larger existing dimensions in the rebuilt
declaration. For example, `NUMERIC(40, 4)` becomes `NUMERIC(40, 12)` and
`NUMERIC(40, 18)` remains unchanged.

The rebuild uses a raw SQLite connection so `PRAGMA foreign_keys` is disabled
before the transaction begins and restored afterward. It retains complete
explicit index SQL, including partial unique indexes, retains foreign-key
definitions through the reflected table, copies rows, and runs
`PRAGMA foreign_key_check` after migration. Regression coverage uses enabled
foreign keys and existing `orders -> trades` / `orders -> validity checks` /
`trades -> round trips` dependencies, verifies rows, keys, indexes, numeric
declarations, and repeatability.

SQLite startup applies the same monotonic policy to account, cash-ledger,
snapshot, and corporate-action audit values in addition to position, order,
trade, validity, and round-trip accounting fields. `rounding_residual` retains
its distinct `NUMERIC(30, 24)` target.

`docs/paper_trading.md` now distinguishes whole-share integer position/lot
quantities from 12-decimal account, ledger, snapshot, and corporate-action
audit precision. It also states that non-integral corporate-action results are
rejected before writes.

Validation performed:

```text
uv run pytest test/paper_trading/storage/test_corporate_action_migration.py test/paper_trading/services/test_corporate_action_service.py -q
```

Result: `17 passed, 2 skipped`. The skipped tests require
`TEST_POSTGRESQL_URL`.

```text
uv run ruff format --check storage/storage_db.py test/paper_trading/storage/test_corporate_action_migration.py
uv run ruff check storage/storage_db.py test/paper_trading/storage/test_corporate_action_migration.py
git diff --check
```

Result: passed. The broader focused storage command also ran 162 tests
successfully and skipped three PostgreSQL-only cases; one pre-existing
PostgreSQL fallback test failed because its local fallback database has an
incomplete enum-governed legacy schema (`paper_accounts.status` is absent).

No repository `simplify` skill is installed in this worktree. A targeted manual
simplification review found no safe simplification: the raw-connection boundary
is necessary because SQLite ignores foreign-key pragma changes inside an active
transaction.

## Final Migration Integrity Follow-up

SQLite numeric-table rebuilds now run `PRAGMA foreign_key_check` before their
transaction commits. A violation raises `IntegrityError`, rolls back the table
replacement, and leaves the original table declaration, rows, dependent foreign
keys, and partial unique index intact. The original `PRAGMA foreign_keys`
setting is restored only after the successful commit or failed rollback ends the
transaction, which respects SQLite's rule that changing this pragma inside a
transaction is ineffective.

The rollback regression creates the existing dependent `paper_trades ->
paper_orders` topology with an intentionally invalid legacy child row. It
asserts that the rebuild fails on `foreign_key_check`, the original
`NUMERIC(20, 4)` declaration and values remain, the partial unique index
remains, the known violation remains visible, and enabled foreign-key enforcement
is restored.

PostgreSQL widening compares precision and scale independently and builds each
replacement declaration from the maximum of the existing and target dimensions.
Thus an existing `NUMERIC(40, 4)` widens to `NUMERIC(40, 12)`, while
`NUMERIC(40, 20)` is unchanged. Multi-column changes use PostgreSQL's valid
comma-separated `ALTER COLUMN ... TYPE ...` clauses.

### Validation

```text
uv run pytest test/paper_trading/storage/test_corporate_action_migration.py test/paper_trading/storage/test_repository.py -q
```

Result: `97 passed, 2 skipped in 66.68s`. The skipped tests are the two
PostgreSQL migration tests, skipped because `TEST_POSTGRESQL_URL` is unavailable
in this environment; no Docker-backed PostgreSQL test URL was supplied.

```text
uv run ruff format --check storage/storage_db.py test/paper_trading/storage/test_corporate_action_migration.py
uv run ruff check storage/storage_db.py test/paper_trading/storage/test_corporate_action_migration.py
git diff --check
```

Result: all passed.

### Simplify Review

The requested `simplify` skill is not installed in this worktree (no matching
entry exists under `.agents/skills/**/simplify/**`), so it could not be invoked.
Manual review found no safe behavior-preserving simplification: the explicit
post-transaction rollback before restoring `PRAGMA foreign_keys` is required by
SQLite transaction semantics.

## PostgreSQL Fixture Follow-up

The two PostgreSQL migration tests initially failed during `Base.metadata.create_all()`
because a fresh isolated schema did not contain unrelated `blackroom_market` and
`blackroom_source` enums. The fixture creates the complete paper-trading governed
dependency set required by these tests while excluding unrelated global metadata.
It then removes the corporate-action table and its types, leaving the issue-87
migration responsible for its corporate-action enum/table setup. It explicitly
uses `NUMERIC(40, 4)` to verify scale expansion without precision narrowing.

## Independent Review Fixes

The PostgreSQL migration tests now assert every label in the governed
`paper_corporate_action_type`, `paper_corporate_action_processing_status`, and
extended `paper_cash_event_type` enums. They also assert the corporate-action
`market`, `processing_status`, `cash_delta`, `quantity_delta`, and `created_at`
defaults. The widening fixture seeds integer-backed position and lot quantities
and verifies both their `INTEGER` declarations and legacy values remain
unchanged. It also verifies the legacy snapshot values remain unchanged after
numeric widening.

### Validation

```text
TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5433/quant uv run pytest test/paper_trading/storage/test_corporate_action_migration.py -v
```

Exact result: `5 passed in 15.28s`.

```text
uv run ruff format --check test/paper_trading/storage/test_corporate_action_migration.py
```

Exact result: `1 file already formatted`.

```text
uv run ruff check test/paper_trading/storage/test_corporate_action_migration.py
```

Exact result: `All checks passed!`.

```text
git diff --check
```

Exact result: passed with no output.

### Self-Review

- The fixture uses `_GOVERNED_TABLES` in full, so it creates the complete
  paper-trading dependency set required by migration preflight; unrelated
  metadata is excluded without claiming the fixture contains four tables.
- Enum assertions derive expected labels from the domain enums and query the
  PostgreSQL catalog, covering additions and ordering as well as presence.
- Default assertions cover the corporate-action defaults relevant to the
  migration contract while intentionally ignoring the unrelated identity
  sequence default on `id`.
- Integer position and lot quantity declarations and seeded values are checked
  after startup widening, alongside the pre-existing snapshot value checks.
- No production code, plan/spec, API/frontend, or unrelated tests were changed.
- A targeted simplification review found no safe behavior-preserving
  simplification; the helper and catalog assertions are scoped to the review
  findings.

### Validation

```text
TEST_POSTGRESQL_URL=postgresql://quant:quant@127.0.0.1:5433/quant uv run pytest test/paper_trading/storage/test_corporate_action_migration.py -v
```

Result: `5 passed in 14.27s`.

```text
uv run ruff format --check test/paper_trading/storage/test_corporate_action_migration.py && uv run ruff check test/paper_trading/storage/test_corporate_action_migration.py && git diff --check
```

Result: all checks passed.

### Self-Review

- The helper excludes unrelated metadata and does not alter production behavior.
- The migration preflight still receives its complete governed table set, while
  unrelated global metadata is excluded.
- Existing assertions continue to cover corporate-action enum labels/table creation,
  indexes/defaults, repeatability, legacy preservation, and monotonic numeric
  widening (`NUMERIC(40, 4)` to scale 12 and unchanged `NUMERIC(40, 20)`).
- Whole-share integer position and lot quantities remain unchanged.
- No further safe simplification was identified; the explicit table list is the
  smallest clear fixture boundary for the tested legacy schema.

## Final Review Fix Wave: Runtime Accounting Precision

This fix wave addresses the remaining issue #87 final-review findings:

- Matching amount, fee, position cost, cost reduction, realized PnL, and account
  realized PnL calculations now use the shared 12-decimal accounting precision.
- Round-trip entry, exit, fees, realized PnL, return percentage, and rebuild
  calculations now retain the 12-decimal accounting contract.
- Repository position rebuild and replay paths now retain 12-decimal cost and
  realized PnL values. Public cash and snapshot accessors retain their existing
  display formatting, including four-decimal monetary output.
- `CashService.withdraw()` authorizes against `get_cash_available_internal()`;
  its error message and returned API value retain display formatting.
- Missing account and snapshot accounting columns are declared as
  `NUMERIC(30, 12)` from creation, while existing-column widening remains
  monotonic. Whole-share integer position and lot quantities were unchanged.

## Final Review Regression Tests

Added coverage for high-precision buy/sell matching, direct and rebuilt
round-trips, repository lot-derived cost/PnL rebuilds, and withdrawal amounts
that cross a four-decimal display boundary.

## Final Review Validation

Focused command:

```text
uv run pytest test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_repository.py test/paper_trading/storage/test_corporate_action_migration.py -q
```

Exact result: `161 passed, 2 skipped in 144.86s (0:02:24)`.
The two skipped cases are PostgreSQL-only migration tests because
`TEST_POSTGRESQL_URL` is unavailable. The run emitted one existing SQLAlchemy
identity-map warning from round-trip rebuild coverage.

PostgreSQL command:

```text
TEST_POSTGRESQL_URL unavailable; uv run pytest test/paper_trading/storage/test_corporate_action_migration.py -v skipped
```

Result: skipped because no PostgreSQL test URL was configured.

Ruff command:

```text
uv run ruff format --check paper_trading/services/matching_service.py paper_trading/services/round_trip_service.py paper_trading/services/cash_service.py paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_repository.py && uv run ruff check paper_trading/services/matching_service.py paper_trading/services/round_trip_service.py paper_trading/services/cash_service.py paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_repository.py
```

Exact result: `9 files already formatted` and `All checks passed!`.

Touched-file mypy command:

```text
uv run mypy paper_trading/services/matching_service.py paper_trading/services/round_trip_service.py paper_trading/services/cash_service.py paper_trading/storage/repository.py storage/storage_db.py
```

Exact result: passed with no issues in 5 source files.

Pre-commit command:

```text
uv run pre-commit run --files paper_trading/services/matching_service.py paper_trading/services/round_trip_service.py paper_trading/services/cash_service.py paper_trading/storage/repository.py storage/storage_db.py test/paper_trading/services/test_cash_service.py test/paper_trading/services/test_round_trip_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/storage/test_repository.py
```

Exact result: all hooks passed, including Ruff format, Ruff, and mypy.

Diff command:

```text
git diff --check
```

Result: passed with no output.

## Final Review Self-Review

- Internal monetary calculations now quantize only through the shared
  12-decimal contract; four-decimal rounding remains at public display
  boundaries.
- Matching, round-trip, repository rebuild, and withdrawal regressions use
  values whose significant digits exceed the former four-decimal limit.
- Startup migration additions use the approved target type from the first DDL,
  and existing-column widening still takes the maximum existing and target
  precision/scale dimensions.
- Position and lot quantity fields remain integer-backed and whole-share based.
- No safe simplification was identified beyond the shared precision helpers and
  the explicit public/internal cash boundary. The repository `simplify` skill is
  not installed in this worktree, so the required simplification review was
  performed manually.
- Remaining blocker: PostgreSQL migration execution could not be rerun in this
  environment because `TEST_POSTGRESQL_URL` is unavailable; prior report entries
  document the earlier five-test PostgreSQL pass.
