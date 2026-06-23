# Stock Market Module Move Design

## Goal

Move the market calendar helper implementation from `common/stock_market.py` to `stock/market.py`, fully remove the old module, and update repository references so `stock.market` is the canonical module path.

## Current State

- `common/stock_market.py` defines A-share and Hong Kong market date/open helpers.
- `common/__init__.py` re-exports those helpers from `common.stock_market`.
- Most production callers import helpers from `common`, not directly from `common.stock_market`.
- `stock/` already exists as a Python package, so `stock/market.py` can be added without package setup changes.

## Chosen Approach

Use `stock.market` as the single implementation module and remove `common.stock_market` completely.

Implementation steps:

1. Create `stock/market.py` with the existing helper functions from `common/stock_market.py`.
2. Delete `common/stock_market.py`.
3. Remove all market helper exports from `common/__init__.py`.
4. Update all callers to import market helpers directly from `stock.market`.
5. Update direct references, string assertions, and tests that mention `common.stock_market`, package-level `common` market imports, or the old file path.
6. Verify no repository references remain to `common.stock_market`, `common/stock_market.py`, or market helper imports from `common`.

## Compatibility

There will be no importable `common.stock_market` module after the change, and `common/__init__.py` will not re-export market helpers. Existing imports such as `from common import is_market_open` must be changed to direct imports from `stock.market`.

## Testing

Run focused checks with `uv run`, following repository rules:

- Search for stale references to `common.stock_market`, `common/stock_market.py`, and market helper imports from `common`.
- Run relevant tests around affected imports, especially `test/task/test_obos_hk.py`.
- Run broader tests only if the focused checks indicate import behavior could affect more modules.

## Non-Goals

- Do not change market calendar behavior.
- Do not change DAG schedules, task boundaries, retries, or SLA settings.
- Do not refactor unrelated `common` or `stock` modules.
