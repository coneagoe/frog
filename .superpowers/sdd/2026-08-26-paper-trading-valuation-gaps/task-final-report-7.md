# Task Final Report 7

## Status

Implemented both final-review findings for replay valuation warnings and suspended prior-close provenance.

## Changes

- `OrderDeleteService` now consumes the replay snapshot outcome and records one matching warning when the filled-order replay creates a valuation gap.
- Suspended prior-close valuation now requires a valid non-future `date` source date. Missing, malformed, datetime, and future source dates create an `invalid_source_date` valuation gap instead of a stale snapshot.
- Added regression coverage for replay matching-run warning status/count and persisted valuation gaps, plus deterministic invalid source-date gap details.

## Verification

- `uv run pytest test/paper_trading/services/test_order_delete_service.py test/paper_trading/services/test_snapshot_service.py -q`: passed, 71 tests.
- Issue-focused valuation suite: passed, 304 tests.
- PostgreSQL paper-trading migration suite: passed, 73 tests.
- `uv run ruff format . && uv run ruff check .`: passed.
- `uv run pre-commit run --all-files`: passed.
- `uv run mypy`: blocked by 12 existing unrelated missing import/stub errors in `tools/` modules (`dash`, `swifter`, and `plotly`); the repository mypy pre-commit hook passed.

## Simplify Review

No safe simplification identified. The explicit unavailable valuation preserves deterministic diagnostic details without conflating invalid source dates and provider failures.
