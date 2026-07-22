# Paper Trading Hong Kong Stock Connect Design

## Context

The paper trading backend currently models A-share trading assumptions throughout the order, matching, fee, validity, and market-data paths. Those assumptions include 100-share board lots, A-share T+1 sell restrictions, A-share daily price limits, A-share fee presets, and A-share BFQ market-data routing.

The download and storage layers already contain Hong Kong Stock Connect daily-history support, including HK GGT routing in storage and provider fallback in the downloader. The paper trading layer should reuse those market-data capabilities while making market-specific simulation rules explicit.

## Goals

- Support Southbound Hong Kong Stock Connect ordinary-stock paper trading in the existing backend.
- Allow one paper account to hold and trade both A-shares and Hong Kong Stock Connect securities with a single RMB cash pool.
- Persist the market of each order, trade, position-affecting event, and validity check so historical records remain auditable.
- Add account-level configurable Hong Kong Stock Connect fees while preserving existing A-share defaults and APIs.
- Keep existing A-share behavior unchanged.

## Non-goals

- No frontend redesign in this phase.
- No ETF, REIT, warrant, derivative, or non-ordinary-share Hong Kong product support.
- No Stock Connect quota simulation.
- No RMB/HKD foreign-exchange cash ledger or broker-specific exchange-rate modeling.
- No intraday auction, VCM, or order-book microstructure simulation from daily bars.
- No automatic live download of missing Hong Kong market data during order or matching flows.

## Approach

Use explicit market-aware strategies instead of inferring behavior from code shape or duplicating the paper trading subsystem. Orders must carry a market identifier, and services dispatch to A-share or Hong Kong Stock Connect rule, fee, and market-data implementations.

This keeps the existing service boundary intact while removing hard-coded A-share assumptions from shared paths.

## Data Model

### Market field

Add a market field with at least these values:

- `a_share`
- `hk_connect`

Persist the market on:

- paper orders
- paper trades
- paper positions or equivalent position identity records
- paper order validity checks

Existing rows should default to `a_share` during migration or bootstrap.

### Security metadata

Add a minimal Hong Kong Stock Connect security metadata source for ordinary stocks:

- 5-digit symbol
- display name when available
- board lot size
- eligibility flag for Hong Kong Stock Connect ordinary-stock trading
- effective-date handling if the existing metadata source supports it

The first implementation may use storage-backed metadata if already available, or a small repository-local metadata table if not. Missing metadata is a hard rejection for Hong Kong Stock Connect orders because board-lot size cannot be guessed safely.

### Fees

Extend account fee configuration by market. Keep the current A-share shape as the default view for backward compatibility, and add a Hong Kong Stock Connect fee configuration containing:

- commission rate
- minimum commission
- stamp duty rate
- trading fee rate
- SFC transaction levy rate
- AFRC transaction levy rate
- settlement fee rate or amount rule

All fee amounts are recorded in RMB for the paper account. The simulator does not model FX spread or multi-currency cash.

## API and CLI Behavior

- Order creation accepts an explicit `market` argument.
- If omitted, the server keeps backward-compatible behavior by treating the order as `a_share`.
- A-share symbols remain 6-digit codes.
- Hong Kong Stock Connect symbols must be 5-digit codes.
- Market and symbol format mismatches are rejected.
- CLI order creation gains a `--market` flag defaulting to `a_share`.
- API responses include market for orders, trades, positions, and validity checks where those objects are returned.

## Trading Rules

### A-share rules

Existing A-share behavior remains unchanged:

- 100-share lot validation
- A-share T+1 sell restriction
- A-share daily range and limit-touch validity logic
- existing A-share fee calculation
- existing A-share market-data routing

### Hong Kong Stock Connect ordinary-stock rules

Apply these rules for `hk_connect`:

- Buy orders must be board-lot multiples based on the security metadata board lot.
- Sell orders may sell board-lot quantities.
- Odd-lot sell orders are allowed only when they dispose of the full odd-lot remainder held for that security.
- Odd-lot buys are rejected.
- Same-day buy and sell is allowed; do not apply the A-share T+1 sell restriction.
- Market orders are rejected. The existing simulator currently models limit-price orders, so Hong Kong Stock Connect orders continue to require explicit limit prices.
- Limit prices must align with the Hong Kong ordinary-share minimum spread table.
- Do not apply A-share daily up/down limits to Hong Kong Stock Connect orders.
- Reject orders when the security is not recognized as a Hong Kong Stock Connect ordinary stock.

## Market Data and Matching

- Market data lookup dispatches by market.
- A-share orders keep using the current A-share BFQ daily-bar path.
- Hong Kong Stock Connect orders use the existing HK GGT BFQ daily-history storage route.
- If no daily bar exists for the symbol and trade date, matching marks or rejects the order consistently with existing missing-data behavior.
- Daily-bar matching remains price-range based: a buy or sell limit can fill when the limit price is compatible with the daily low/high range.
- Because only daily bars are available, the simulator will not model intraday Stock Connect order-type distinctions beyond requiring explicit limit prices and valid ticks.

## Settlement and Cash Availability

The account cash pool is RMB-only.

For Hong Kong Stock Connect:

- Buys freeze estimated RMB cash at order creation, including estimated fees.
- Sells freeze position quantity at order creation.
- Same-day sellability includes same-day buys after they are filled, because Hong Kong trading permits day trading.
- Economic settlement uses T+2 as the baseline Hong Kong cash-market cycle.
- Sell proceeds are recorded as pending settlement and do not become available cash until settlement date.
- Buy-side cash deduction is finalized on fill, with any difference between estimated and actual costs released or additionally charged according to existing cash-freeze conventions.

The implementation should introduce the smallest durable settlement representation needed to make pending proceeds observable and repeatable. If current cash-ledger semantics cannot represent pending settlement clearly, add a dedicated pending-settlement record instead of overloading available cash.

## Validity Checks

Validity analysis becomes market-aware.

For A-shares, retain the current daily range and limit-touch classifications.

For Hong Kong Stock Connect:

- Validate symbol eligibility and market-data availability.
- Validate limit price against daily low/high when a daily bar exists.
- Validate tick alignment against the Hong Kong spread table.
- Do not produce A-share limit-up or limit-down conclusions.
- When required metadata is missing, report an invalid or unchecked result with a specific reason rather than silently falling back to A-share logic.

## Error Handling

Use explicit, user-facing rejection reasons for:

- missing market on new market-aware API paths when no compatibility default applies
- unsupported market
- market and symbol format mismatch
- missing Hong Kong Stock Connect security metadata
- non-board-lot buy quantity
- invalid odd-lot sell quantity
- invalid Hong Kong tick size
- missing Hong Kong daily bar
- insufficient settled or available cash
- insufficient sellable quantity

## Compatibility

- Existing API clients that omit market continue to create A-share orders.
- Existing A-share tests should continue to pass without fixture rewrites other than expected response fields that now include `market`.
- Existing persisted orders and trades are interpreted as A-share records.
- No existing DAG schedule, provider order, or storage export/import behavior should change unless a new table is added. If a new table is added, update `tools/db_common.sh`.

## Testing and Verification

Follow test-first implementation.

Minimum failing tests before production changes:

- order creation accepts explicit `hk_connect` and persists market
- existing A-share order creation remains compatible when market is omitted
- Hong Kong Stock Connect rejects unknown metadata
- Hong Kong Stock Connect rejects non-board-lot buys
- Hong Kong Stock Connect allows same-day sell after a buy fill
- Hong Kong Stock Connect odd-lot sell is allowed only for the full odd-lot remainder
- Hong Kong tick-size validation rejects off-tick prices
- Hong Kong fees apply on both buy and sell sides using account-level configurable rates
- Hong Kong matching reads HK GGT BFQ bars instead of A-share bars
- Hong Kong sell proceeds become available only after T+2 settlement
- A-share T+1 and fee behavior remain unchanged

Focused verification commands should start with:

```bash
uv run pytest test/paper_trading
uv run pytest test/tools/test_paper_trading_cli.py
```

If storage migrations or shared storage routing change, also run the relevant storage tests:

```bash
uv run pytest test/storage/test_storage_db.py
```

Broaden to `uv run pytest test` only if focused tests indicate integration uncertainty.

## Open Questions Resolved

- Scope is Hong Kong Stock Connect ordinary stocks only.
- Accounts can mix A-share and Hong Kong Stock Connect assets.
- Market is explicit on orders rather than inferred only from symbol length.
- Fees are account-level configurable by market.
- Cash is RMB-only in this phase.
- Quota, FX, ETF, and intraday microstructure are out of scope.
