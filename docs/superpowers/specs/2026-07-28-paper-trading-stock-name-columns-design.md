# Paper Trading Stock Name Columns Design

## Goal

Show the human-readable security name next to the trading symbol in the Account Positions card, Orders page, and Trades page. This lets investors reconcile holdings and executions without relying solely on ticker recognition.

## Scope

The backend enriches the existing position, order, and trade list responses with a nullable `stock_name` field. The paper-trading frontend adds a `Stock` column immediately after `Symbol` in the three corresponding shared tables.

This is a dense operational trading interface. The stable ticker remains visible and independently scannable; the name is not folded into, or substituted for, the symbol.

## API and Metadata Resolution

`PositionResponse`, `OrderResponse`, and `TradeResponse` gain `stock_name: str | None = None`.

When building each response row, the backend attempts a market-specific lookup in the authoritative security metadata available to the repository. A-share names use the A-share security master. Hong Kong Connect names use its security metadata. Other supported or future markets use their own authoritative metadata when one is available.

Lookup failure, missing metadata, delisted symbols, and markets without a supported metadata source are normal display cases. They must return `stock_name: null`; the list endpoints must continue returning their otherwise valid rows. The backend must not infer, duplicate, or fabricate a name from the symbol.

## Frontend Presentation

The shared `PositionTable`, `OrderTable`, and `TradeTable` each add the left-aligned header `Stock` immediately after `Symbol`.

The value is `row.stock_name` when present, otherwise `-`. The name remains one line, truncates with an ellipsis when constrained, and exposes its complete text using a native `title` attribute. Numeric columns retain their current right alignment and tabular-number treatment.

The existing horizontal table scrolling is retained on narrow screens. No table becomes a card layout, and no identifier column is hidden. The compact Positions table constrains the name cell so it cannot dominate the numeric columns.

No global palette, typography, spacing, or component-system changes are part of this work. The distinctive information hierarchy is the adjacent `Symbol | Stock` pair: one is the immutable trading identifier and the other is the recognition aid.

## Types and Tests

The frontend `Position`, `Order`, and `Trade` contracts gain nullable `stock_name` fields matching the API responses.

Focused backend tests verify:

1. A-share rows return the A-share stock name.
2. Hong Kong Connect rows return the HK stock name.
3. Missing, unsupported, or unavailable metadata returns `null` without failing the list endpoint.

Focused frontend tests verify:

1. Positions, orders, and trades render a populated `Stock` value in the column immediately after `Symbol`.
2. A missing name renders `-`.
3. Long stock names preserve full text in `title` while the cell uses the intended truncation class or style.

The verification path is the focused backend router/service tests and relevant frontend table/page tests, followed by the paper-trading frontend lint and production build to confirm the extended TypeScript contracts.

## Non-goals

- No new standalone metadata endpoint or frontend name-lookup request.
- No changes to stored position, order, or trade records.
- No automatic symbol-to-market inference.
- No changes to the analytics Round Trips table or other unrequested symbol displays.
- No global visual redesign.
