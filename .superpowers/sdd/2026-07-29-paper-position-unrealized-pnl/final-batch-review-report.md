# Final Batch Valuation Review Report

## Scope

Applied the final-review corrections for the position valuation service/router and focused tests. The pre-existing untracked plan document was left untouched.

## TDD Evidence

### RED

Command:

```text
uv run pytest test/paper_trading/services/test_position_valuation_service.py::test_value_many_always_honors_injected_batch_adapter
```

Result: RED. The new regression failed because the service selected the single-item adapter path and never invoked the injected batch adapter (`batch_calls == []`).

### GREEN

Command:

```text
uv run pytest test/paper_trading/services/test_position_valuation_service.py test/paper_trading/api/test_accounts_api.py
```

Result: GREEN. All 40 focused tests passed.

## Changes

- `paper_trading/services/position_valuation_service.py`
  - Made `fetch_prices` the sole valuation adapter used by `value_many`.
  - Removed fragile identity-based mode selection and the single-row `fetch_price` injection path.
  - Preserved `value(position)` as delegation to `value_many([position])`.
  - Removed dead `_real_time_price` and its unused `fetch_current_price` import.
  - Preserved order, per-row price validation, DB BFQ-close fallback, isolation on adapter failure, and the existing PnL formula.
- `paper_trading/api/routers/accounts.py`
  - Calls `valuation.value_many(rows)` unconditionally.
  - Removed the `hasattr` compatibility fallback.
- `test/paper_trading/services/test_position_valuation_service.py`
  - Added default module-level `fetch_price_map` monkeypatch coverage for A-share and `hk_connect` rows.
  - Asserted one ordered batch call and per-row fallback for invalid/missing live prices.
  - Added coverage proving an injected batch adapter is always honored.
  - Updated service tests to the batch adapter contract.
- `test/paper_trading/api/test_accounts_api.py`
  - Added `value_many` to the fake valuation service while retaining `value` compatibility delegation.

## Validation

Commands and results:

```text
uv run pytest test/paper_trading/services/test_position_valuation_service.py test/paper_trading/api/test_accounts_api.py
40 passed, 6 warnings

uv run ruff format --check paper_trading/services/position_valuation_service.py paper_trading/api/routers/accounts.py test/paper_trading/services/test_position_valuation_service.py test/paper_trading/api/test_accounts_api.py
4 files already formatted

uv run ruff check paper_trading/services/position_valuation_service.py paper_trading/api/routers/accounts.py test/paper_trading/services/test_position_valuation_service.py test/paper_trading/api/test_accounts_api.py
All checks passed

git diff --check
Passed
```

## Concerns

- The focused test run emits six existing Starlette/AnyIO deprecation warnings; no test failed.
- The pre-existing untracked plan file remains in the worktree and is excluded from the commit.
