# Paper Trading Validity Analysis Design

## Context

Paper trading should support recording real trading intent and analyzing whether each operation was valid for the specified trading day. The system should preserve the user's original input, evaluate validity against market data, and keep the matching simulation available as a separate capability.

Existing paper trading code already validates limit prices against a daily bar during matching in `paper_trading/domain/rules.py` and `paper_trading/services/matching_service.py`. The new requirement moves this into a first-class analysis workflow that is visible on orders and queryable with evidence.

## Goals

- Preserve original user-entered trading intent, including invalid or suspicious inputs.
- Analyze each order's validity for the user-specified `trade_date`.
- Mark whether the entered price is inside the day's low/high range.
- Detect daily limit-up and limit-down touches using daily-bar approximation in the first version.
- Distinguish order lifecycle from trade-validity analysis.
- Keep default matching behavior unchanged, while leaving room for strict matching later.

## Non-Goals

- Do not implement minute-level or tick-level limit-touch detection in the first version.
- Do not change DAG schedules, task boundaries, or unrelated trading workflows.
- Do not make strict validity gating the default matching behavior.
- Do not replace existing paper trading account, fee, cash, or position models.

## User Decisions

- Use both order-level summary fields and a separate analysis detail table.
- Use daily bars now, with a data model that can later support minute or tick evidence.
- Treat daily limit touches as suspicious by default, and hard-invalid only when the input price is also at the relevant limit area.
- Default validity analysis does not affect funds, positions, or matching; strict mode may be added later.
- `trade_date` means the operation date. Validity analysis and default matching run against that same day.
- A-share T+1 remains a sellable-position rule, not a reason to shift matching to the next day.

## Data Model

### Order Summary

Add validity summary fields to `paper_orders`:

- `validity_status`: current validity status for quick list/detail display.
- `validity_reason`: short reason code or concise reason text.
- `validity_checked_at`: timestamp when the latest validity analysis was generated.

These fields summarize analysis only. Existing order status values such as accepted, rejected, filled, and cancelled continue to represent the order lifecycle.

### Analysis Detail

Add a `paper_trade_validity_checks` table with one row per generated order validity analysis.

Suggested fields:

- `id`
- `order_id`
- `account_id`
- `symbol`
- `trade_date`
- `side`
- `input_price`
- `daily_low`
- `daily_high`
- `limit_up_price`
- `limit_down_price`
- `touched_limit_up`
- `touched_limit_down`
- `price_in_range`
- `status`
- `reason_code`
- `reason_detail`
- `data_granularity`
- `created_at`

`data_granularity` starts as `daily` and can later support `minute` or `tick` without changing the table shape.

## Validity Statuses

- `valid`: the order passes available validity checks.
- `suspicious`: available data indicates risk or uncertainty, but not a hard invalid condition.
- `invalid`: the operation is invalid for the specified trading day.
- `unchecked`: the system could not complete validity analysis, usually because required market data is missing.

## Rule Design

### Daily Price Range

If `input_price < daily_low` or `input_price > daily_high`, mark the order `invalid` with reason `PRICE_OUT_OF_DAILY_RANGE`.

### Daily Limit Touch Approximation

The first version uses daily bars:

- `daily_high >= limit_up_price` means the symbol touched limit-up that day.
- `daily_low <= limit_down_price` means the symbol touched limit-down that day.

Limit prices should be computed through a dedicated rule/helper so future exchange-specific details can be centralized.

### Limit Touch Severity

- If a buy order's day touched limit-up, mark it at least `suspicious`.
- If a sell order's day touched limit-down, mark it at least `suspicious`.
- If a buy order's input price is near or equal to the limit-up price and the day touched limit-up, mark it `invalid`.
- If a sell order's input price is near or equal to the limit-down price and the day touched limit-down, mark it `invalid`.

The exact tolerance for "near or equal" should be implemented as an explicit decimal tick-size rule, not a floating-point comparison.

### Missing Market Data

If the order can be saved but required market data is missing, keep the original order and mark validity as `unchecked`. The analysis detail should record which data was unavailable.

### Matching Semantics

Default matching remains same-day matching against the order's `trade_date`. Validity analysis does not block matching by default.

Future strict mode can use validity state this way:

- Skip `invalid` orders.
- Allow `suspicious` orders to match while retaining the risk label.
- Continue normal handling for `valid` orders.
- Leave `unchecked` handling configurable.

## Service Design

Add a `TradeValidityService` responsible for generating validity analysis.

Inputs:

- Saved `PaperOrder`
- Daily market bar for the order symbol and trade date
- Limit-price helper output

Outputs:

- Order-level summary update
- `paper_trade_validity_checks` detail row

`OrderService.place_order()` should save the original order first, then call `TradeValidityService` and update the order summary. This preserves invalid, suspicious, and unchecked user input for later review.

`MatchingService` may read validity state in the future for strict mode, but the first version should avoid changing default matching behavior except where existing behavior already rejects or skips orders.

## API Design

Order creation responses should include validity summary fields so the frontend can show validity immediately after submission.

Add a detail endpoint for full evidence by order, for example:

- `GET /paper/accounts/{account_id}/orders/{order_id}/validity-checks`

Future query filters can list invalid or suspicious trades by account, date range, symbol, or status.

## Testing

### Domain Tests

Cover:

- Price below daily low.
- Price above daily high.
- Valid price inside daily range.
- Buy order on a daily limit-up touch.
- Sell order on a daily limit-down touch.
- Suspicious limit touch without hard-invalid price.
- Hard-invalid limit-touch price.
- Missing market data produces `unchecked`.

### Service Tests

Cover:

- Orders preserve original input even when invalid.
- Order summary fields are updated after validity analysis.
- Analysis detail rows include daily range, limit-touch flags, status, and reason.
- Invalid and suspicious validity states do not change default order lifecycle status.

### Matching Tests

Cover:

- Default matching behavior remains same-day.
- Validity status does not block default matching.
- Strict-mode behavior is not enabled by default.

### API Tests

Cover:

- Order creation returns validity summary fields.
- Validity detail endpoint returns evidence for an order.
- Missing market data returns an `unchecked` validity state rather than losing the order.

## Documentation

Update `docs/paper_trading.md` to describe paper trading as:

- A trading-intent recording system.
- A trade-validity analysis system.
- An optional matching simulation system.

The documentation should explain:

- Same-day validity analysis and same-day default matching.
- A-share T+1 as a sellable-position constraint.
- Daily-bar approximation for limit-up and limit-down detection.
- The meanings of `valid`, `suspicious`, `invalid`, and `unchecked`.

## Open Implementation Notes

- Confirm the existing market-data provider can expose previous close or a reliable limit price source. If not, the first implementation should add a narrow helper boundary and mark limit-touch checks `unchecked` when limit prices cannot be computed safely.
- Keep exchange-specific limit rules isolated from `OrderService` and `MatchingService`.
- Update database export/import table lists if a new storage table is added.
