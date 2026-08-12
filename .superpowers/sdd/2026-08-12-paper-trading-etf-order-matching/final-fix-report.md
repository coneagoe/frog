# Issue #46 Final Review Fix Report

## Changes

- Updated `OrderService._accept_sell_order` so current-date ETF T+1 sell rejections use `ETF_T1_VIOLATION` and the ETF-specific message: `Insufficient sellable quantity: ETF T+1 prevents same-day purchases from selling`.
- Preserved the existing A-share T+1 rejection code, message, and details branch.
- Updated the existing ETF admission test to assert the ETF-specific code and message.
- Added a historical ETF buy then next-date sell rebuild lifecycle test.
- Added a same-symbol A-share/ETF collision test proving orders, trades, positions, and lots remain market-qualified during matching.

## Verification

Commands run:

```sh
uv run pytest test/paper_trading/services/test_matching_service.py::test_etf_workflow_fills_buy_rejects_same_date_sell_and_settles_next_date_sell
uv run pytest test/paper_trading/services/test_matching_service.py::test_etf_workflow_fills_buy_rejects_same_date_sell_and_settles_next_date_sell test/paper_trading/services/test_matching_service.py::test_historical_etf_buy_then_next_date_sell_rebuilds_full_lifecycle test/paper_trading/services/test_matching_service.py::test_matching_keeps_same_symbol_a_share_and_etf_orders_positions_and_trades_isolated
uv run pytest test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py test/paper_trading/services/test_order_delete_service.py
uv run ruff format --check paper_trading/services/order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py
uv run ruff check paper_trading/services/order_service.py test/paper_trading/services/test_matching_service.py test/paper_trading/services/test_order_service.py
uv run mypy paper_trading/services/order_service.py
```

Final results: 122 affected service tests passed; Ruff format and lint checks passed; mypy passed for `paper_trading/services/order_service.py`.
