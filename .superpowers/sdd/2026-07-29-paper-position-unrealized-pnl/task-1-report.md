# Task 1 Report: Real-Time-First Position Valuation API

## Changed Files

- `paper_trading/services/position_valuation_service.py`: Added injectable per-position valuation with valid real-time-first pricing, BFQ DB-close fallback, market routing, PnL calculation, and per-symbol failure isolation.
- `paper_trading/api/deps.py`: Added the injectable `get_position_valuation_service` dependency.
- `paper_trading/api/routers/accounts.py`: Enriched `list_positions` responses with valuation fields while retaining stock-name enrichment.
- `paper_trading/schemas/accounts.py`: Added nullable `mark_price`, `price_source`, and `unrealized_pnl` fields to `PositionResponse`.
- `test/paper_trading/api/test_accounts_api.py`: Added API coverage for real-time precedence and PnL, DB fallback and market routing, and mixed valued/unvalued positions.

## RED Verification

Command:

```text
uv run pytest test/paper_trading/api/test_accounts_api.py -k real_time -v
```

Result: RED during collection before production implementation. Pytest collected 0 tests and stopped with:

```text
ImportError: cannot import name 'get_position_valuation_service' from 'paper_trading.api.deps'
```

This confirmed the new test dependency was absent before implementation.

## GREEN Verification

Command:

```text
uv run pytest test/paper_trading/api/test_accounts_api.py -k list_positions -v
```

Result: GREEN, 5 passed, 27 deselected, 1 warning.

Command:

```text
uv run pytest test/paper_trading/api/test_accounts_api.py -v
```

Result: GREEN, 32 passed, 6 warnings.

Command:

```text
uv run ruff check paper_trading/api/deps.py paper_trading/api/routers/accounts.py paper_trading/schemas/accounts.py paper_trading/services/position_valuation_service.py test/paper_trading/api/test_accounts_api.py
```

Result: All checks passed.

Command:

```text
git diff --check
```

Result: Passed with no whitespace errors.

## Test Coverage

- Real-time valid quote takes precedence and computes `(mark_price * quantity) - cost_amount`.
- DB-close fallback is used for unavailable valuation and preserves `a_share` and `hk_connect` routing.
- Missing valuation leaves all three new fields null without failing other positions.
- Existing stock-name enrichment and all existing Accounts API tests remain passing.
- Realized PnL is not used in unrealized PnL calculation.

## Commit

`14957ba` (`feat: value paper positions with live price fallback`)

## Concerns

- Pytest reports existing dependency deprecation warnings from Starlette/httpx and FastAPI/AnyIO; no new test failures or lint errors were introduced.
- The unrelated untracked plan file `docs/superpowers/plans/2026-07-29-paper-position-unrealized-pnl.md` was intentionally left untouched.

## Ticket #2 Correction

### Files Changed

- `paper_trading/services/position_valuation_service.py`: Replaced cost-per-share division with the exact total-cost PnL formula and switched DB fallback to one latest-close provider call.
- `paper_trading/storage/market_data.py`: Extended the narrow market-data seam with latest BFQ close retrieval while preserving A-share and HK Connect routing.
- `storage/storage_db.py`: Added efficient descending, single-row latest BFQ close queries for A-share and HK Connect history.
- `test/paper_trading/services/test_position_valuation_service.py`: Added service-level tests using injectable live-price and market-data fakes.
- `test/paper_trading/storage/test_market_data.py`: Added latest-close routing and single-call coverage.
- `task-1-report.md`: Appended this correction record.

### RED Verification

Command:

```text
uv run pytest test/paper_trading/services/test_position_valuation_service.py -v
```

Result: RED, 3 failed and 1 passed. The failures demonstrated the division-path precision error, missing latest-close seam, and date-walking fallback incompatibility before the correction implementation.

### GREEN Verification

Commands:

```text
uv run pytest test/paper_trading/services/test_position_valuation_service.py -v
uv run pytest test/paper_trading/services/test_position_valuation_service.py test/paper_trading/storage/test_market_data.py test/paper_trading/api/test_accounts_api.py -v
uv run ruff check paper_trading/services/position_valuation_service.py paper_trading/storage/market_data.py storage/storage_db.py test/paper_trading/services/test_position_valuation_service.py test/paper_trading/storage/test_market_data.py
git diff --check
```

Results: Service tests passed, 4 passed. Focused service/storage/API suite passed, 43 passed with 6 existing dependency deprecation warnings. Ruff passed and `git diff --check` passed.

### Exact Coverage

- Valid live price takes precedence over stored data and computes `Decimal(total_quantity) * mark_price - Decimal(cost_amount)` for a non-divisible total cost.
- Missing, invalid, nonpositive, and failed live prices use the latest stored BFQ close through one provider call.
- Latest-close storage queries route separately to A-share and HK Connect history and return the newest row at or before the valuation date.
- Missing stored prices remain unvalued, while failures remain isolated to the affected symbol.
- Existing Accounts API behavior remains passing; its service override tests remain thin router serialization coverage.

### Commit

`2e8f46e` (`fix: correct paper position valuation fallback`)

### Remaining Concerns

- Pytest reports the same existing Starlette/httpx and FastAPI/AnyIO deprecation warnings.
- The unrelated untracked plan file `docs/superpowers/plans/2026-07-29-paper-position-unrealized-pnl.md` remains untouched.
