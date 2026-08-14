# Catalogue ETF Paper Order Classification Design

## Goal

Classify every new six-digit Paper Trading order whose symbol appears in the
ETF catalogue as `etf` at order entry. The order must then use the existing ETF
eligibility gate and the existing ETF trading and raw daily-market-data paths.

This implements GitHub issue #55, a child of #53. Raw ETF daily pricing is
already available from the completed issue #54 work.

## Scope

The change is limited to new orders submitted through
`OrderService.place_order`. The service owns market resolution for API, CLI,
and direct Python callers, so every order-entry path observes one rule.

`ETFBasic` is the ETF catalogue. A symbol is catalogue-backed only when it is a
bare six-digit string and has an `ETFBasic` row. For such a symbol, the resolved
market is always `Market.ETF`:

- Omitted `market` resolves to `etf`.
- Explicit `market="a_share"` resolves to `etf`.
- Explicit `market="etf"` remains `etf`.

The catalogue is authoritative for ETF market identity. It does not authorize
trading. After market resolution, the existing `ETFEligibilityService` remains
the policy gate for listing status, exchange, review state, money-market
classification, and disabled ETFs.

Symbols absent from the ETF catalogue retain the current behavior: omitted
`market` resolves to A-share; explicitly selected Hong Kong Stock Connect and
A-share markets follow their current validation and routing rules.

## Design

`OrderService.place_order` will resolve the requested market before its
idempotency lookup and all market-specific validation. It will parse a supplied
market value as today, then replace the resolved value with `Market.ETF` when
the symbol is a catalogue-backed ETF. The existing explicit-market rejection
for known ETF symbols will be removed.

Resolving before idempotency is required because repeated requests must compare
against the market actually persisted on the order. A first request with an
omitted or conflicting A-share market and a repeat request with the same
idempotency key must therefore identify the same ETF order rather than report a
false market conflict.

The existing ETF branch then remains responsible for all ETF-specific behavior:

- reviewed ETF eligibility validation;
- ETF lot and tick validation;
- ETF commission calculation and frozen cash;
- ETF T+1 sellability and settlement behavior;
- market-qualified validity checks;
- matching against the raw `etf_daily` route introduced by issue #54.

No new public schema or CLI option is necessary. `CreateOrderRequest.market`
and the CLI `--market` option remain optional, and existing callers may still
provide `etf` explicitly.

## Error Handling

Invalid supplied market values retain the existing rejected-order behavior and
`INVALID_MARKET` code. Catalogue-backed ETF classification supersedes only a
valid or omitted requested market value; it does not hide invalid input.

When a catalogue ETF fails the existing eligibility check, the rejected order
persists with `market="etf"` and the existing ETF rejection code, such as
`ETF_ELIGIBILITY_UNREVIEWED` or `UNSUPPORTED_ETF_TYPE`. This records the
correct identity while preserving the approval lifecycle.

## Tests

Focused order-service coverage will prove:

- an omitted-market catalogue ETF is accepted when reviewed as supported and
  persists with market `etf`;
- an explicitly A-share catalogue ETF resolves and persists as `etf`;
- an unreviewed catalogue ETF is rejected by existing eligibility rules while
  retaining market `etf`;
- a six-digit symbol absent from the catalogue retains its A-share behavior;
- an order for catalogue ETF `518880`, created without an explicit market,
  matches through raw `etf_daily` data using the existing matching-service
  seam.

Existing ETF tests remain the regression evidence for fee, lot, tick, T+1,
settlement, and market-qualified validity behavior. Existing A-share and Hong
Kong Stock Connect tests remain the regression evidence that non-catalogue
market decisions do not change.

## Out Of Scope

- ETF eligibility review policy and catalogue ingestion.
- ETF fee, tick, lot, T+1, and settlement rules.
- Raw ETF market-data routing, adjusted ETF history, and fallback behavior.
- Existing persisted orders and historical market-identity repair, which are
  handled by separate issue #53 child work.
- A prefix-based market inference rule, UI changes, schema changes, and CLI
  interface changes.
