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
