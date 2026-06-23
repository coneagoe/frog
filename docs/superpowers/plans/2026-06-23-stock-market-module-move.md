# Stock Market Module Move Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move market calendar helpers from `common.stock_market` to `stock.market` with no backward-compatible `common` exports.

**Architecture:** `stock/market.py` becomes the only implementation module for market calendar helpers. All callers import the helpers directly from `stock.market`; `common/__init__.py` stops exporting them and `common/stock_market.py` is deleted.

**Tech Stack:** Python 3.11+, pandas, pandas-market-calendars, Ruff, pytest, uv.

## Global Constraints

- Use `uv run` for Python commands; do not use bare `python` or `python3` for project tasks.
- Do not change market calendar behavior.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA settings.
- Do not refactor unrelated `common` or `stock` modules.
- Do not keep a compatibility shim for `common.stock_market` or package-level market helper exports from `common`.

---

## File Structure

- Create: `stock/market.py` — owns A-share and Hong Kong market helper functions currently in `common/stock_market.py`.
- Delete: `common/stock_market.py` — old module must no longer exist.
- Modify: `common/__init__.py` — remove imports and `__all__` entries for market helpers.
- Modify: affected DAG, task, tool, and test files — replace `from common import <market helper>` with `from stock.market import <market helper>`.

### Task 1: Move Market Helpers

**Files:**
- Create: `stock/market.py`
- Delete: `common/stock_market.py`
- Modify: `common/__init__.py:1-20`
- Modify: `task/trend_follow_etf.py`
- Modify: `task/monitor_fallback_stock.py`
- Modify: `task/obos_hk.py`
- Modify: `task/download_hk_stock_data.py`
- Modify: `tools/monitor_fallback_stocks.py`
- Modify: `tools/compare_securities.py`
- Modify: `dags/download_etf_daily.py`
- Modify: `dags/download_daily_basic_a_stock_daily.py`
- Modify: `dags/download_stock_general_info_daily.py`
- Modify: `dags/download_stk_limit_a_stock_daily.py`
- Modify: `dags/download_suspend_d_a_stock_daily.py`
- Modify: `dags/monitor_stock_daily.py`
- Modify: `dags/monitor_stock_intraday.py`
- Modify: `dags/download_hk_ggt_history_daily.py`
- Modify: `dags/download_stock_history_daily.py`
- Modify: `test/task/test_obos_hk.py`

**Interfaces:**
- Consumes: existing helper functions from `common/stock_market.py`.
- Produces: `stock.market.is_testing() -> bool`, `stock.market.is_market_open() -> bool`, `stock.market.get_last_trading_day() -> str`, `stock.market.is_a_market_open(date_str: str) -> bool`, `stock.market.is_a_market_open_today() -> bool`, `stock.market.is_hk_market_open(date_str: str) -> bool`, `stock.market.is_hk_market_open_today() -> bool`.

- [ ] **Step 1: Write import regression expectation**

Update `test/task/test_obos_hk.py` so any asserted import string expects direct `stock.market` usage:

```python
"from stock.market import is_hk_market_open_today"
```

- [ ] **Step 2: Run focused test to verify current failure**

Run: `uv run pytest test/task/test_obos_hk.py -q`

Expected: FAIL while source code still imports from `common`.

- [ ] **Step 3: Move implementation**

Copy the full contents of `common/stock_market.py` into new file `stock/market.py`, preserving function names and behavior exactly, then delete `common/stock_market.py`.

- [ ] **Step 4: Remove common exports**

Replace `common/__init__.py` contents with only the encoding header if no other exports exist:

```python
# -*- coding: utf-8 -*-
```

- [ ] **Step 5: Update production imports**

For every affected DAG, task, and tool file, replace market helper imports from `common` with direct imports from `stock.market`. Example:

```python
from stock.market import is_hk_market_open_today
```

- [ ] **Step 6: Verify stale references are gone**

Run: `rg "common\.stock_market|common/stock_market|from common import (is_testing|is_market_open|get_last_trading_day|is_a_market_open|is_a_market_open_today|is_hk_market_open|is_hk_market_open_today)" .`

Expected: no matches.

- [ ] **Step 7: Run focused tests**

Run: `uv run pytest test/task/test_obos_hk.py -q`

Expected: PASS.

- [ ] **Step 8: Run lint on changed Python files**

Run: `uv run ruff check common stock task tools dags test/task/test_obos_hk.py`

Expected: PASS or only unrelated pre-existing failures outside changed imports.

### Task 2: Final Verification

**Files:**
- Verify: all files changed in Task 1.

**Interfaces:**
- Consumes: `stock.market` helper exports from Task 1.
- Produces: confirmed import migration with no stale `common` market-helper usage.

- [ ] **Step 1: Search for old helper exports from common**

Run: `rg "is_testing|is_market_open|get_last_trading_day|is_a_market_open|is_a_market_open_today|is_hk_market_open|is_hk_market_open_today" common`

Expected: no matches.

- [ ] **Step 2: Search for direct stock market imports**

Run: `rg "from stock\.market import" task tools dags test`

Expected: matches in each caller that previously imported market helpers from `common`.

- [ ] **Step 3: Inspect working tree**

Run: `git diff -- common stock task tools dags test/task/test_obos_hk.py docs/superpowers/specs/2026-06-23-stock-market-module-move-design.md docs/superpowers/plans/2026-06-23-stock-market-module-move.md`

Expected: diff contains only the module move, import rewrites, spec update, and plan addition.

---

## Self-Review

- Spec coverage: covered module creation, old module deletion, `common/__init__.py` cleanup, direct caller imports, stale reference checks, and focused tests.
- Placeholder scan: no placeholders or deferred implementation instructions remain.
- Type consistency: all produced helper function names match the existing implementation and the target `stock.market` module path.
