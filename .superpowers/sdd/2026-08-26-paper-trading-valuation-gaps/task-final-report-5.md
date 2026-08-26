# Task Final Report 5

## Status

Implemented the final review fix for paper-trading valuation fake market data.

## Changes

- Updated `FakeMarketDataProvider.get_latest_daily_close()` to return `None` for unconfigured symbol/date keys instead of the synthetic close of `50`.
- Updated `FakeMarketDataProvider.get_latest_daily_close_with_date()` with the same missing-data behavior while preserving explicit bars and suspended-bar caching.
- Added a direct regression test covering an unconfigured prior-close lookup through both methods.

No production code, protocol, or repository documentation required changes.

## Verification

- Affected paper-trading tests: passed, 99 tests.
- `uv run pre-commit run --all-files`: passed.
- `git diff --check`: passed.
- `uv run mypy`: blocked by pre-existing missing optional dependencies and stubs (`dash`, `swifter`, and Plotly typing), with 12 errors in 9 unrelated `tools/` files.
