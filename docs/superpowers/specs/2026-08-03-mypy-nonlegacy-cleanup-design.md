# Non-Legacy Mypy Cleanup

## Problem Statement

The repository documents `uv run mypy` as a focused check, but the command has
no configured target and exits before checking code. Running mypy explicitly on
the paper-trading subsystem exposes widespread false instance types such as
`Column[str]` and `Column[Decimal]`. These originate in SQLAlchemy ORM models
whose annotations describe class-level columns rather than instance values.

The errors prevent mypy from providing useful safety for active, non-legacy
systems such as storage and paper trading. Existing legacy exclusions remain
intentional and should not be folded into this migration.

## Solution

Make the default mypy command check the repository's active, non-legacy Python
scope. Convert affected SQLAlchemy ORM model fields to SQLAlchemy 2 typed
declarative mappings using `Mapped[T]` and `mapped_column(...)`, preserving
their database definitions and runtime behavior. Resolve the remaining
non-legacy type errors through accurate annotations and narrow code changes,
not broad error suppression.

## User Stories

1. As a developer, I want `uv run mypy` to run without additional arguments, so
   that the documented focused check is usable locally and in automation.
2. As a developer, I want ORM attributes to resolve to their domain values on
   model instances, so that static checks catch invalid cash, position, date,
   and market-data interactions.
3. As a paper-trading maintainer, I want type checks to cover matching,
   settlement, positions, ledger reconstruction, and analytics, so that changes
   to account state have reliable static feedback.
4. As a storage maintainer, I want typed model mappings without schema changes,
   so that existing tables and database data remain compatible.
5. As a developer, I want existing legacy module exemptions retained, so that
   this cleanup remains scoped to actively maintained modules.
6. As a reviewer, I want no blanket `ignore_errors`, pervasive casts, or broad
   `type: ignore` directives added to obtain a green result, so that the check
   remains meaningful.
7. As an operator, I want model migration to retain existing queries,
   constraints, defaults, and relationships, so that type modernization does
   not change application behavior.
8. As a developer, I want each migrated model group verified with its existing
   tests, so that the migration is safe to review and integrate incrementally.
9. As a developer, I want the final active scope to have zero mypy errors, so
   that regressions in typed modules are visible immediately.

## Implementation Decisions

- Preserve the existing `ignore_errors` overrides for `app.*`, `stock.*`,
  `fund.*`, `tools.*`, and `backtest.deprecate.*`. Do not expand their scope.
- Configure the default mypy invocation with explicit repository targets for
  active modules and their tests where appropriate. The command must not rely on
  an implicit current-directory target.
- Migrate active SQLAlchemy declarative models from legacy `Column(...)`
  annotations to SQLAlchemy 2 typed mappings. Each field must keep its current
  SQL type, nullability, default, server default, primary-key, index, unique,
  foreign-key, relationship, and constraint behavior.
- Migrate shared storage models before dependent services, then paper-trading
  models and services, followed by remaining active module groups in dependency
  order.
- Correct accurate local types, protocol signatures, and return types revealed
  after the model migration. Prefer a type that represents the runtime contract
  over `Any`, casts, or suppression.
- Treat the SQLAlchemy model migration as a type-only refactor: do not alter
  table names, migration histories, data-export table lists, market rules,
  matching behavior, or public API schemas.
- Retain third-party missing-import configuration where the dependency has no
  stubs; do not use it to suppress first-party module errors.

## Testing Decisions

- The final verification is `uv run mypy` with zero errors for its configured
  active scope.
- Before and after each model group migration, run the closest existing pytest
  coverage for the owning subsystem, beginning with storage model tests and
  paper-trading service/API tests.
- Run database-model tests against the project test database to establish that
  typed mappings retain construction, persistence, relationships, and query
  behavior.
- Run the complete repository test suite before integration because shared ORM
  models are used across storage, download, monitoring, DAG, and paper-trading
  paths.
- Inspect diffs to ensure no legacy exemption is removed or broadened and no
  schema-affecting field option changed unintentionally.

## Out of Scope

- Removing the existing legacy `ignore_errors` overrides.
- Typing `app.*`, `stock.*`, `fund.*`, `tools.*`, or `backtest.deprecate.*`.
- Changing database schemas, migration history, stored data, table names, or
  SQL query semantics.
- Introducing a new ORM, database driver, or type-checking tool.
- Replacing correct first-party types with broad `Any`, mass casts, or blanket
  suppressions merely to pass mypy.

## Further Notes

The SQLAlchemy instance-versus-column distinction is the primary root cause of
the current paper-trading error volume. A typed-declarative migration fixes the
information source rather than suppressing its symptoms. The work is large and
should be delivered in dependency-aware batches, each retaining a green test
suite before the next batch begins.
