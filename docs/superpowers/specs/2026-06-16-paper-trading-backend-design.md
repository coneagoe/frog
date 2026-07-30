# Paper Trading Backend Design

## Context

This spec defines the MVP backend for an A-share paper trading system. The first release focuses on manual simulated trading through FastAPI, while keeping the account, order, and matching services reusable for future strategy-driven paper trading.

The existing repository already has PostgreSQL-oriented SQLAlchemy storage and A-share daily market data workflows. The new system should reuse those data sources through an adapter instead of duplicating market data tables.

## Goals

- Provide a FastAPI backend for manual paper trading.
- Support multiple paper accounts protected by one deployment-level API token.
- Support A-share limit orders with basic realistic rules.
- Use daily market data for asynchronous matching by trade date.
- Track cash, frozen funds, positions, lots, orders, trades, and daily account snapshots.
- Keep the service layer independent from FastAPI so future strategy execution can call the same business logic.

## Non-Goals

- Real broker integration.
- Real-time or tick-level matching.
- Multi-user login and permission management.
- Market orders.
- Intraday volume, queue, or partial-fill simulation beyond preserving the state model for future use.
- Strategy execution in the MVP.

## Chosen Approach

Use a modular monolith inside this repository. Add a new `paper_trading/` package with a thin FastAPI API layer, domain services, storage repositories, and market data adapters. PostgreSQL remains the primary database, with TimescaleDB hypertables only for time-series paper trading records where useful.

This approach keeps deployment simple and lets the paper trading module reuse the repository's existing market data and storage conventions. It also avoids coupling trading logic to HTTP, which makes the future strategy mode a caller of the same service layer rather than a rewrite.

## Module Layout

```text
paper_trading/
  api/
    app.py
    deps.py
    routers/
      accounts.py
      orders.py
      matching.py
      snapshots.py
  domain/
    enums.py
    errors.py
    fees.py
    rules.py
  services/
    account_service.py
    order_service.py
    matching_service.py
    snapshot_service.py
  storage/
    models.py
    repository.py
    market_data.py
  schemas/
    accounts.py
    orders.py
    matching.py
    snapshots.py
```

Responsibilities:

- API layer: authentication, request validation, response formatting, and route wiring.
- Service layer: account lifecycle, order state transitions, freezing and releasing assets, matching, and snapshots.
- Repository layer: all paper trading table reads and writes.
- Market data adapter: reads existing daily prices, trade calendar, limit-up/limit-down, and suspension data.
- Domain layer: reusable enums, domain errors, A-share trading rules, and fee calculations.

## Data Model

MVP tables:

- `paper_accounts`: account metadata, including name, initial cash, status, base currency, and timestamps.
- `paper_cash_ledger`: append-only cash events for deposits, freezes, releases, trades, and fees.
- `paper_positions`: account-symbol position summary.
- `paper_position_lots`: buy lots used for T+1 sellability and FIFO realized PnL.
- `paper_orders`: limit order requests and state.
- `paper_trades`: executed trades.
- `paper_account_snapshots`: daily account valuation snapshots.
- `paper_matching_runs`: audit records for matching jobs.

Recommended TimescaleDB hypertables:

- `paper_trades` by `trade_time` or `trade_date`.
- `paper_cash_ledger` by `occurred_at`.
- `paper_account_snapshots` by `trade_date`.

Accounts, orders, positions, lots, and matching runs should remain normal PostgreSQL tables.

## Account and Cash Model

The account table stores identity and static metadata, not just a mutable cash number. Cash changes are represented by `paper_cash_ledger` entries. Available and frozen cash are derived from ledger events or maintained as a carefully updated cache if query performance requires it later.

Buy order acceptance freezes estimated required cash: `quantity * limit_price + estimated_fees`. Matching converts the freeze into actual trade cost and fees. If estimated cash exceeds actual cost, the difference is released. Rejected or cancelled buy orders release the whole freeze.

All monetary values use `Decimal` in Python and `NUMERIC` in PostgreSQL. API responses should serialize money as strings or fixed-scale decimals to avoid floating point drift.

## Position and T+1 Model

`paper_positions` stores summary position data per account and symbol. `paper_position_lots` stores buy lots with `buy_trade_date`, original quantity, remaining quantity, and cost basis.

T+1 sellability is enforced through lots. Shares bought on a trade date become sellable only on the next valid trading day. Sell matching consumes eligible lots FIFO and updates realized PnL. Sell order acceptance freezes sellable quantity; cancellation or rejection releases that frozen quantity.

## Order State Machine

Order statuses:

```text
new -> accepted -> partially_filled -> filled
                 -> cancelled
                 -> rejected
```

- `new`: request received.
- `accepted`: account, rules, and asset freezes succeeded.
- `rejected`: business rule validation failed; reason is recorded.
- `partially_filled`: reserved for later volume-aware matching.
- `filled`: fully matched and settled into cash, trade, and position records.
- `cancelled`: open order cancelled and frozen assets released.

MVP matching normally produces one trade per order, but the state model keeps `partially_filled` so future intraday or volume-based matching can be added without changing the external contract.

## Trading Rules

MVP rules target A-shares:

- Quantity must be a multiple of 100 shares.
- The requested trade date must be a valid trading day.
- Suspended symbols cannot be matched.
- Buy orders require enough available cash for limit price plus estimated fees.
- Sell orders require enough T+1 sellable shares.
- Limit orders must respect daily low/high and limit-up/limit-down data.

The rules live in `paper_trading/domain/rules.py` so manual API calls and future strategy calls use identical validation.

## Fees

Use a basic configurable A-share fee model:

- Commission with a configurable rate and minimum commission.
- Stamp duty on sells.
- Transfer fee where applicable.

The MVP uses system-level defaults. Account-level fee configuration can be added later without changing order or trade semantics.

## Matching Flow

`POST /paper/matching/runs` accepts a `trade_date` and optional `account_id`.

Flow:

1. Create a `paper_matching_runs` row with `running` status.
2. Load accepted orders for the trade date and optional account.
3. For each order, load daily OHLC, limit-up/limit-down, and suspension status.
4. If the symbol is suspended or violates hard rules, reject the order and release frozen assets.
5. If the limit price does not touch the day's tradable range, keep the order accepted for a future run.
6. If tradable, execute at the order's `limit_price`, provided it is inside the daily range and does not violate limit-up/limit-down rules.
7. Write `paper_trades`, update order state, write cash ledger events, update positions and lots.
8. Generate or update account snapshots for affected accounts on the trade date.
9. Mark the matching run completed with processed, filled, skipped, rejected, and failed counts.

A single order failure should not roll back the entire run. Use per-order transactions or savepoints. Business-rule failures produce rejected orders; unexpected system failures are recorded in run details and should leave the order in a safe unchanged state.

## Snapshot Flow

After matching, generate daily account snapshots using close prices for the trade date.

Snapshot fields include:

- `cash_available`
- `cash_frozen`
- `market_value`
- `total_assets`
- `realized_pnl`
- `unrealized_pnl`
- `position_count`
- `order_count`
- `trade_count`

Snapshots are persisted so account performance is reproducible and does not depend on future changes to market data.

## API Surface

All MVP endpoints require `Authorization: Bearer <token>`, including reads.

```text
POST   /paper/accounts
GET    /paper/accounts
GET    /paper/accounts/{account_id}
GET    /paper/accounts/{account_id}/positions
GET    /paper/accounts/{account_id}/cash-ledger

POST   /paper/accounts/{account_id}/orders
GET    /paper/accounts/{account_id}/orders
GET    /paper/orders/{order_id}
POST   /paper/orders/{order_id}/cancel

POST   /paper/matching/runs
GET    /paper/matching/runs
GET    /paper/matching/runs/{run_id}

GET    /paper/accounts/{account_id}/snapshots
GET    /paper/accounts/{account_id}/trades
```

Writing endpoints should support `idempotency_key`, at least for order creation and matching run creation, to avoid duplicate orders or duplicate matching caused by retries.

## Error Handling

Domain errors return structured responses:

```json
{
  "code": "INSUFFICIENT_CASH",
  "message": "Insufficient available cash for the order",
  "details": {}
}
```

Example error codes:

- `UNAUTHORIZED`
- `ACCOUNT_NOT_FOUND`
- `ACCOUNT_INACTIVE`
- `INVALID_SYMBOL`
- `INVALID_TRADE_DATE`
- `INVALID_LOT_SIZE`
- `INSUFFICIENT_CASH`
- `INSUFFICIENT_POSITION`
- `SUSPENDED_SYMBOL`
- `PRICE_OUT_OF_RANGE`
- `ORDER_NOT_CANCELLABLE`

Rejected orders should store a rejection code and reason for auditability.

## Strategy Mode Extension

The MVP should not implement strategy execution, but it should keep these extension points:

- Multiple accounts are first-class from day one.
- Future `strategy_id` can be nullable on orders or stored in a `paper_strategy_accounts` binding table.
- Strategy code should call the same `order_service` as manual API orders.
- Strategy batch processing should call the same `matching_service` by trade date.
- Strategy performance reports should use `paper_account_snapshots`.

This supports the future model of one strategy mapped to one account without migrating away from the MVP schema.

## Testing Strategy

Focus tests on domain and service behavior with mocked market data adapters:

- Fee calculations: commission, minimum commission, stamp duty, transfer fee.
- Trading rules: lot size, valid trading day, T+1, suspension, limit-up/limit-down, cash, and sellable position.
- Order service: buy freezes, sell freezes, rejection release, cancellation release, idempotency.
- Matching service: fill at limit price, skip when not touched, reject hard-rule violations, settle cash and fees, consume lots FIFO.
- Snapshot service: close-price valuation, cash available/frozen, market value, total assets, realized and unrealized PnL.
- API layer: token enforcement, request validation, response shape, and route-to-service wiring.

External providers such as akshare, baostock, and tushare must be mocked in tests.

## Open Decisions Resolved

- MVP mode: manual paper trading first; strategy mode later.
- Auth: one deployment-level API token, not multi-user login.
- Account model: multiple paper accounts from the MVP.
- Market data mode: daily data by trade date.
- Order type: limit orders only.
- Matching mode: asynchronous matching runs.
- Fee model: basic system-level A-share fees.
- Asset snapshots: persisted daily snapshots.
