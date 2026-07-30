# Current mypy errors cleanup design

## Goal

Make the current `uv run pre-commit run mypy --all-files` result pass without
changing runtime behavior or expanding the typing-cleanup scope beyond the 139
errors currently reported by that command.

## Scope

- Retain `explicit_package_bases = true` in `[tool.mypy]` so the duplicate DAG
  source-file mapping remains resolved.
- Correct the current errors in the files reported by the pre-commit mypy hook.
- Preserve current production interfaces and test assertions unless a test
  deliberately supplies a value outside the declared domain contract.

## Out of scope

- A SQLAlchemy 2.x conversion of legacy models to `Mapped[...]` and
  `mapped_column(...)`.
- Fixing type errors that are not currently emitted by the all-files hook.
- Broad mypy ignores or relaxing project-wide type-checking rules.
- Runtime behavior, DAG scheduling, dependency, or task-boundary changes.

## Design

### Paper-trading market-data fakes

`MarketDataProvider` requires `get_latest_daily_close`. Shared and local test
doubles will implement that method with the existing `Decimal | None` contract.
Each fake will return a context-appropriate value while retaining the existing
behavior of tests that do not call the new method. This resolves the dominant
protocol-conformance errors without weakening constructor types or casting
providers to `Any`.

### SQLAlchemy query boundaries

Repository methods whose legacy SQLAlchemy query result is inferred as `Any`
will narrow the result at the query boundary to their already-declared model
return types. This is limited to the four current `no-any-return` errors and
does not migrate model declarations or alter persistence behavior.

### Download boundaries

The download manager will narrow dynamically derived outcome statuses to the
existing `ProviderOutcome` literal union. The yfinance provider will establish
a local DataFrame type boundary for its normalized output (and any necessary
narrow third-party typing configuration), preserving provider output behavior.

### Airflow DAG boundaries

DAG code will keep its runtime import bootstrap unchanged. Its Airflow context
and task-instance/XCom values will be narrowed at the boundary before date or
XCom operations. Any project-local import typing treatment will remain narrow
enough not to mask unrelated DAG errors.

### Test-only typing repairs

Tests will receive minimal, behavior-neutral corrections: valid
`ProviderOutcome` literals, explicit empty-container types, statements instead
of using `list.append()` as an expression, and a concrete sortable value type.

## Verification

1. Run targeted mypy commands for each changed ownership lane.
2. Run focused pytest files where test fake or behavior-adjacent test changes
   are made.
3. Run `uv run pre-commit run mypy --all-files`; it must exit zero with no
   mypy errors.
4. Run `git diff --check` to validate the final patch formatting.

## Risk controls

- Do not add broad `ignore_errors`, global error-code disables, or `Any` casts
  solely to suppress errors.
- Keep protocol methods structurally compatible with production signatures.
- Narrow untyped framework and ORM values only at their integration boundary.
- Stop and re-scope with the user if fixing a current error exposes a required
  broad model migration or changes observable business behavior.
