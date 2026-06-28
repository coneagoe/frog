# Paper Trading Frontend Redesign

## Context

The current paper trading frontend uses Next.js App Router under `frontend/paper-trading`. The `/trade` route currently owns several unrelated responsibilities: account selection, charting, order submission, positions, orders, trades, and cash ledger display. This makes the trading workspace too broad and duplicates history review concerns that should live in dedicated pages.

## Goals

- Make `/trade` responsible only for paper order placement.
- Move positions and cash ledger into `/accounts`, driven by the selected account in the `Paper Accounts` card.
- Add separate history pages for orders and trades.
- Preserve existing API behavior and table rendering where possible.
- Avoid broad visual or data-layer refactors beyond this page responsibility split.

## Non-Goals

- Do not change backend paper trading APIs.
- Do not change order matching behavior.
- Do not add filters, pagination, account detail routes, or tabbed history unless separately requested.
- Do not alter analytics behavior except for navigation coexistence.

## Page Responsibilities

### Trade

`/trade` should only support placing orders. It keeps account selection, chart symbol input, `PriceChart`, and `OrderForm`. It should stop loading or rendering positions, orders, trades, and cash ledger data. The page copy should describe order placement rather than account inspection.

### Accounts

`/accounts` should continue to create, list, and delete paper accounts. The `Paper Accounts` card becomes selectable: clicking an account sets the selected account and loads that account's positions and cash ledger. The selected account's details render beside or below the account list using the existing `PositionTable` and `CashLedgerTable` components. When no account exists, the page should keep the current create-account guidance.

### Orders

Add `/orders` for historical orders. The page loads accounts, lets the user select an account, renders `OrderTable`, and preserves cancellation for cancellable orders. After a successful cancellation, the page refreshes the current account's orders.

### Trades

Add `/trades` for historical executions. The page loads accounts, lets the user select an account, and renders `TradeTable`. This page is read-only.

### Navigation

The global navigation should include `Accounts`, `Trade`, `Orders`, `Trades`, and `Analytics`.

## Data Flow

- Each page loads its own account list through `listAccounts`.
- Account-specific pages select the requested `accountId` from the URL if present and valid; otherwise they default to the first available account.
- Account switching clears stale account-specific data before loading the next account.
- Slow responses must not overwrite newer account selections; pages should follow the current `requestIdRef` pattern used by trade and analytics pages.
- `Trade` should call only the API functions it needs for account selection and order submission.

## Components

- Reuse `OrderForm`, `PriceChart`, `OrderTable`, `TradeTable`, `PositionTable`, and `CashLedgerTable`.
- Keep table components in `features/trading/trading-tables.tsx` for this change to minimize file movement risk.
- Extend `AccountList` or its parent page so clicking an account selects it without breaking delete behavior or existing trading/analytics links.

## Error Handling

- Page-level account loading failures should show `ErrorBanner`.
- Account detail failures on `/accounts` should not prevent the account list from rendering.
- Order cancellation failures on `/orders` should show `ErrorBanner` and leave existing order rows visible.
- Empty states should remain table-specific: no positions, no cash ledger entries, no orders, or no trades.

## Verification

- Run focused frontend checks from `frontend/paper-trading` when available, prioritizing lint, tests, and build.
- If no frontend-specific verification is available or it is insufficient, use the repository's existing `uv run` verification commands as a fallback.
- Manually verify navigation and account switching behavior in the frontend if a browser run is available.
