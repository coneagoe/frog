# Task 10 Report

## Status

Implemented and verified the cash-only replay regression fix.

## Changes

- `SnapshotRecalculationService` skips market-calendar date discovery when `market_data` is `None`, while retaining snapshot, valuation-gap, and replay-event dates.
- Added a cash-only backdated deposit replay regression test proving replay succeeds without market data and preserves both event and snapshot dates.
- Completed the `EmptyMarketData` fixture with `is_trade_date`.

## Commit

`4a9b122` (`Fix cash-only snapshot replay without market data`).

## Tests

- `uv run pytest test/paper_trading/services/test_cash_service.py -q`: 62 passed.
- `uv run pytest test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/api/test_snapshot_recalculation_api.py -q`: 24 passed, 2 skipped.
- `uv run ruff format ...`: passed after formatting.
- `uv run ruff check ...`: passed.
- `uv run mypy paper_trading/services/snapshot_recalculation_service.py paper_trading/services/cash_service.py`: passed.

## Concerns

- Snapshot recalculation with `market_data=None` still cannot value positive holdings. `CashService._replay_from` retains the existing explicit error for that case.
- Snapshot recalculation tests emitted an existing Starlette/httpx deprecation warning.

## P2 Test Fixture Cleanup

### Changes

- `EmptyMarketData` now inherits `MarketDataProviderCompatibility` and overrides only its non-trading-day behavior, supplying the complete `MarketDataProvider` protocol with harmless inherited defaults.

### Exact Verification Results

- `uv run pytest test/paper_trading/services/test_cash_service.py -q`: `62 passed in 26.39s`
- `uv run ruff format --check test/paper_trading/services/test_cash_service.py`: `1 file already formatted`
- `uv run ruff check test/paper_trading/services/test_cash_service.py`: `All checks passed!`
- `uv run mypy`: `Success: no issues found in 235 source files`

### Concerns

- None.
