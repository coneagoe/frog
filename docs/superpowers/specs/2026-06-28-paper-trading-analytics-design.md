# Paper Trading Analytics Design

## Goal

Expand the paper trading frontend analytics page into a trading-oriented dashboard that combines execution statistics, QuantStats-style portfolio metrics, and round-trip trade quality metrics. The feature spans backend analytics derivation and frontend presentation so metrics such as win rate, payoff ratio, and profit factor use an auditable full-position round-trip definition instead of approximate trade-list math.

## Current Context

- The current frontend analytics page fetches accounts, snapshots, trades, and cash ledger entries, then shows asset summary cards, an asset curve, and raw tables.
- Frontend types already include orders with `status`, `filled_quantity`, `rejection_code`, and `rejection_reason`, but the analytics page does not currently load orders.
- Backend snapshots already expose asset, realized PnL, unrealized PnL, order count, and trade count.
- Backend matching updates aggregate position-level realized PnL using FIFO lot settlement, but it does not persist closed trade or round-trip PnL records.

## Chosen Approach

Use backend-persisted full-position round trips as the source of truth for trade quality metrics.

Alternatives considered:

- Replaying trades on every analytics request would avoid a new table but would make historical analytics harder to audit and test.
- Showing only equity-curve metrics would be faster but would omit the requested win rate and payoff ratio.

## Backend Design

### Round-Trip Model

Add a `paper_position_round_trips` table that records open and closed full-position cycles per account and symbol. A round trip opens when a symbol position moves from zero to positive quantity and closes when that symbol returns to zero.

Suggested fields:

- `id`
- `account_id`
- `symbol`
- `open_trade_id`
- `close_trade_id`
- `open_trade_date`
- `close_trade_date`
- `entry_amount`
- `exit_amount`
- `fees`
- `realized_pnl`
- `return_pct`
- `holding_days`
- `status`
- `created_at`
- `updated_at`

Only rows with `status = "closed"` participate in win rate, payoff ratio, profit factor, and consecutive win/loss metrics. Partial exits update the still-open position cycle but do not close it or include it in closed round-trip metrics.

### Round-Trip Generation

Create an open round-trip row when a buy fill changes total quantity for an account and symbol from zero to positive. Update the open row as additional buys or partial sells change aggregate entry cost, exit proceeds, fees, and realized PnL. When a sell fill settles and the post-settlement total quantity becomes zero, mark the current cycle closed and persist final return percentage and holding days.

Provide a rebuild routine for existing accounts. It replays trades grouped by `account_id + symbol`, ordered by `trade_date + trade_id`, and identifies repeated zero-to-positive-to-zero cycles. This routine supports historical data backfill and test fixture generation.

### Analytics API

Add `GET /paper/accounts/{account_id}/analytics`.

The response groups data into:

- `overview`: current asset metrics and total return.
- `activity`: daily, weekly, and monthly buckets for submitted orders, trades, filled orders, and rejected orders.
- `execution`: fill rate, rejection rate, reject reason distribution, and counts by order status.
- `trade_quality`: round-trip metrics and recent round-trip rows.
- `risk`: equity-curve return, max drawdown, current drawdown, and risk-adjusted metrics when enough snapshot data exists.
- `data_quality`: null reasons such as `insufficient_data` for metrics that should not be computed yet.

### Metric Definitions

Execution and activity:

- `order_count`: submitted order count.
- `trade_count`: executed trade count.
- `fill_rate`: filled orders divided by submitted orders.
- `rejection_rate`: rejected orders divided by submitted orders.
- Daily, weekly, and monthly frequency: bucketed order and trade counts by trade date.

Round-trip trade quality:

- `win_rate`: profitable closed round trips divided by closed round trips.
- `avg_win`: average positive round-trip realized PnL.
- `avg_loss`: average negative round-trip realized PnL.
- `payoff_ratio`: `avg_win / abs(avg_loss)`.
- `profit_factor`: gross winning PnL divided by absolute gross losing PnL.
- `consecutive_wins`: longest streak of profitable closed round trips ordered by close date.
- `consecutive_losses`: longest streak of losing closed round trips ordered by close date.
- `avg_holding_days`: average holding days across closed round trips.

QuantStats-style equity metrics:

- `total_return`: latest snapshot total assets versus the account's `initial_cash`; if initial cash is unavailable, use the earliest available snapshot and return a baseline reason.
- `max_drawdown`: largest peak-to-trough decline from snapshot total assets.
- `current_drawdown`: current total assets versus historical peak.
- `sharpe`, `sortino`, and `calmar`: computed only when snapshot count and cadence are sufficient.

## Frontend Design

Update `frontend/paper-trading/features/analytics/analytics-page.tsx` to fetch the new analytics endpoint as the primary source for derived metrics. Keep raw snapshots only if the existing asset chart continues to consume the current `Snapshot[]` shape during the first implementation pass.

Organize the page into five sections:

1. `Overview`: total assets, cash, market value, realized PnL, unrealized PnL, and total return.
2. `Activity`: daily, weekly, and monthly order/trade frequency.
3. `Execution`: fill rate, rejection rate, reject reason distribution, and status counts.
4. `Trade Quality`: win rate, payoff ratio, profit factor, average win/loss, consecutive wins/losses, average holding days, and a round-trip detail table.
5. `Risk & Drawdown`: equity curve, max drawdown, current drawdown, and optional Sharpe, Sortino, and Calmar values.

For metrics with insufficient data, show a clear unavailable state rather than zero. For example, Sharpe and Sortino should display an `insufficient data` explanation when snapshots are too sparse.

## Error Handling

- Backend analytics should return `null` plus a reason for unavailable derived metrics instead of silently returning misleading zeros.
- Rebuild failures should not corrupt existing round-trip records; use transactional rebuild per account where practical.
- Frontend should preserve existing partial panel loading behavior and display available sections even if one analytics group fails.

## Testing Strategy

Backend tests:

- Round-trip generation when a symbol position fully closes.
- No round trip for partial exits.
- Multiple cycles for the same account and symbol.
- Historical rebuild from ordered trades.
- Win rate, average win/loss, payoff ratio, profit factor, and consecutive streak calculations.
- Fill rate, rejection rate, and reject reason distribution from orders.
- Total return, max drawdown, and current drawdown from snapshots.
- Insufficient-data handling for Sharpe, Sortino, and Calmar.

Frontend tests:

- Analytics page renders the five sections.
- Empty account or empty analytics state is readable.
- Insufficient-data reasons are shown instead of misleading zeros.
- Reject distribution and round-trip table render correctly.
- Existing summary and asset chart behavior remains intact or is deliberately replaced by equivalent analytics API data.

## Out of Scope

- Live broker execution analytics such as latency and slippage.
- Short selling and short-side round trips unless the paper trading engine later supports short positions.
- Gross and net exposure by market value unless position-level market values become available from the backend.
