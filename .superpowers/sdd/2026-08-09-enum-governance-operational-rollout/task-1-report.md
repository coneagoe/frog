# Task 1 Report: Serializable Unified Audit Contract

## Changed Files

- `storage/enum_governance.py`
  - Added the frozen JSON-serializable audit dataclasses:
    `EnumGovernanceColumnAudit`, `EnumGovernanceGroupAudit`,
    `EnumGovernanceCheckAudit`, and `EnumGovernanceDomainAudit`.
  - Added `EnumGovernanceResult.audits`.
  - Collects available adapter audits only after all adapter preflights succeed.
  - Routes audits through `_run_phase(..., "audit", ...)` so failures retain
    domain-qualified `EnumGovernanceError` wrapping.
  - Includes audits in all PostgreSQL result paths and leaves non-PostgreSQL
    results with an empty audit tuple.
- `storage/enum_governance_adapter.py`
  - Added the optional `audit` callback contract, preserving existing domain
    adapter constructors until later domain reporting work implements catalog
    audits.
- `test/storage/test_enum_governance.py`
  - Added coverage for successful dry-run audit ordering, preflight failure
    preventing every audit callback, and empty SQLite audit output.

## Tests Run

- `uv run pytest test/storage/test_enum_governance.py -k audit -v`
  - Passed: 3 selected tests; 14 deselected.
- `uv run pytest test/storage/test_enum_governance.py`
  - Passed: 10 tests; 7 PostgreSQL-dependent tests skipped because
    `TEST_POSTGRESQL_URL` was unavailable.
- `uv run ruff check storage/enum_governance.py storage/enum_governance_adapter.py test/storage/test_enum_governance.py`
  - Passed: no lint errors.
- `uv run ruff format --check storage/enum_governance.py storage/enum_governance_adapter.py test/storage/test_enum_governance.py`
  - Passed: all files formatted.
- `uv run mypy storage/enum_governance.py storage/enum_governance_adapter.py`
  - Passed: no type errors.
- `git diff --check`
  - Passed: no whitespace errors before the implementation commit.

## Self-Review

- The preflight loop remains before audit collection, preserving fail-fast
  dry-run behavior and no-DDL-on-preflight-failure semantics.
- Audit callbacks execute before the dry-run early return and before either
  mutation path, so they cannot run after partial DDL.
- SQLite returns immediately before both preflight and audit work, preventing
  fabricated PostgreSQL catalog facts.
- Existing domain adapters remain compatible because `audit` defaults to
  `None`; later domain reporting can supply concrete callbacks without another
  coordinator API change.
- The audit dataclasses contain only strings, booleans, tuples, and `None`, so
  `dataclasses.asdict` output remains JSON serializable.

## Commit

- `3f28762 Add enum governance audit contract`
