# Paper Trading Frontend Design

## Context

The repository already includes an MVP FastAPI backend for A-share paper trading. The backend supports accounts, limit orders, matching runs, positions, trades, cash ledger entries, and account snapshots under `/paper/*` endpoints protected by one deployment-level bearer token.

This spec defines the first frontend for that backend. The frontend should provide a complete but thin paper trading console built with Next.js, TypeScript, and Lightweight Charts. The goal is a usable manual trading and review interface, not a polished multi-user product.

## Goals

- Add an isolated Next.js frontend app for paper trading.
- Keep backend API tokens server-side and out of browser code.
- Support account creation and account selection.
- Support manual limit-order creation and cancellation.
- Show account positions, orders, trades, cash ledger entries, and snapshots.
- Show Lightweight Charts for trade context and account analytics.
- Keep the MVP small enough to implement and verify quickly.

## Non-Goals

- Multi-user login or role-based permissions.
- Real broker integration.
- Real-time streaming market data.
- Tick-level or intraday order-book trading UI.
- Strategy authoring or strategy execution UI.
- Advanced portfolio analytics, benchmarking, or report export.

## Chosen Approach

Create a standalone Next.js TypeScript app under `frontend/paper-trading/` using the App Router. The app calls local Next.js route handlers under `/api/paper/*`; those handlers proxy requests to the FastAPI backend and inject the deployment-level bearer token from server-side environment variables.

This keeps the Python backend and Node frontend cleanly separated while allowing them to live in the same repository. It also avoids exposing `PAPER_TRADING_API_TOKEN` to browser JavaScript, which is important even for an internal MVP.

## Configuration

Frontend runtime configuration:

```bash
PAPER_TRADING_API_BASE_URL=http://localhost:8000
PAPER_TRADING_API_TOKEN=change-me
```

The browser never reads these values directly. Next.js route handlers use them when forwarding requests to FastAPI.

## App Layout

```text
frontend/paper-trading/
  app/
    accounts/
      page.tsx
    trade/
      page.tsx
    analytics/
      page.tsx
    api/
      paper/[...path]/route.ts
    layout.tsx
    page.tsx
  components/
    account-selector.tsx
    chart-panel.tsx
    data-table.tsx
    empty-state.tsx
    error-banner.tsx
    money-text.tsx
    status-badge.tsx
  features/
    accounts/
    trading/
    analytics/
  lib/
    api-client.ts
    format.ts
    types.ts
```

Responsibilities:

- `app/`: routing, page composition, and local API proxy handlers.
- `components/`: shared presentational components.
- `features/accounts/`: account list, account creation, and account state cards.
- `features/trading/`: order form, position table, order table, trade table, and matching controls.
- `features/analytics/`: snapshot chart, asset breakdown, cash ledger, and trade review views.
- `lib/`: typed API helpers, shared formatting, and backend response types.

## Routes

### `/accounts`

Purpose: create and inspect paper accounts.

MVP features:

- List paper accounts.
- Create a new account with `name` and `initial_cash`.
- Show account status, initial cash, and latest known asset summary when available.
- Link each account to `/trade?accountId=...` and `/analytics?accountId=...`.

### `/trade`

Purpose: primary manual trading workspace.

MVP features:

- Account selector.
- Symbol input.
- Lightweight Charts candlestick panel for daily price context.
- Buy and sell limit-order form.
- Matching run control with trade date and current account.
- Position table.
- Order table with cancellation action for cancellable orders.
- Trade table.
- Cash ledger summary or compact ledger table.

Layout:

- Desktop: chart and order form in the main row, tables below.
- Mobile: chart first, then order form, then tables stacked vertically.

### `/analytics`

Purpose: review account performance and trading history.

MVP features:

- Account selector.
- Lightweight Charts line chart for total assets from account snapshots.
- Cash, frozen cash, market value, realized PnL, and unrealized PnL summary cards.
- Snapshot table.
- Trade history table.
- Cash ledger table.

## API Proxy

`app/api/paper/[...path]/route.ts` forwards supported HTTP methods to the FastAPI backend:

```text
/api/paper/accounts                -> /paper/accounts
/api/paper/accounts/1/orders       -> /paper/accounts/1/orders
/api/paper/orders/10/cancel        -> /paper/orders/10/cancel
/api/paper/matching/runs           -> /paper/matching/runs
```

The proxy should:

- Preserve method, path, query string, and JSON body.
- Add `Authorization: Bearer ${PAPER_TRADING_API_TOKEN}`.
- Return backend status codes and JSON bodies unchanged when possible.
- Convert backend network failures into a consistent frontend error response.
- Avoid logging tokens or request bodies that may contain sensitive trading details.

## Frontend Data Flow

Browser components call `lib/api-client.ts`, which calls local `/api/paper/*` endpoints. The API client returns typed data or throws a normalized error object with `status`, `code`, `message`, and optional `details`.

Initial MVP data refresh rules:

- Account creation refreshes account list.
- Order creation refreshes orders, positions, account/cash data, and trades for the selected account.
- Order cancellation refreshes orders, positions, and cash data.
- Matching run refreshes orders, positions, trades, cash ledger, and snapshots.
- Manual refresh buttons are acceptable for the MVP; polling is not required.

Use client-side fetching for interactive views. Do not introduce React Query or SWR unless the implementation becomes repetitive enough to justify the dependency.

## Charting

Use Lightweight Charts in browser-only chart components.

Trade page chart:

- Intended data: daily OHLC bars for the selected symbol.
- If the backend does not expose a daily bar endpoint yet, show a clear `Market data unavailable` empty state and keep order entry usable.
- The chart component should be isolated so a future market-data endpoint can be wired without changing page layout.

Analytics page chart:

- Data source: `GET /paper/accounts/{account_id}/snapshots`.
- Series: total assets over trade date.
- Optional future series: cash, market value, realized PnL, and unrealized PnL.

## User Interaction Rules

Order form:

- Required fields: account, symbol, side, quantity, limit price, trade date.
- Quantity must be a positive integer and should show a local warning when not a 100-share lot.
- Limit price must be positive.
- Submit button is disabled while submitting.
- Backend rejections remain authoritative and are shown to the user.

Matching run:

- Requires trade date.
- Defaults to the selected account when one is selected.
- Shows processed, filled, skipped, rejected, and failed counts after completion when returned by the backend.

Order cancellation:

- Only show cancel action for statuses that may still be cancellable.
- Backend `ORDER_NOT_CANCELLABLE` errors are displayed without local guessing beyond the visible action state.

## Error Handling

The backend uses structured domain errors shaped like:

```json
{
  "code": "INSUFFICIENT_CASH",
  "message": "Insufficient available cash for the order",
  "details": {}
}
```

Frontend behavior:

- Show global connection/authentication failures in the app shell.
- Show form-specific validation and submission errors near the form.
- Show table fetch failures in the affected panel with a retry action.
- Preserve backend error `message` for business-rule failures.
- Fall back to a generic message only when the backend response is not structured JSON.

## Styling And Responsiveness

Use a pragmatic internal-tool style: dense but readable, optimized for scanning trading state quickly.

Design constraints:

- Desktop-first trading workspace with responsive mobile stacking.
- Clear numeric alignment for money, quantity, and price columns.
- Status badges for account, order, and matching statuses.
- Empty states for accounts, positions, orders, trades, snapshots, and unavailable chart data.
- Avoid heavy visual polish until the end-to-end workflow is verified.

## Testing Strategy

Frontend tests should focus on behavior and integration seams:

- API proxy: token injection, path forwarding, query forwarding, backend error passthrough, network failure response.
- API client: success parsing and normalized error handling.
- Formatting: money, quantity, date, and status labels.
- Account flow: account creation refreshes list and exposes navigation targets.
- Trading flow: order form validation, submit success refresh behavior, backend rejection display, cancellation action.
- Analytics flow: snapshots render into chart-ready data and empty states are shown when no snapshots exist.

Verification commands should be defined by the generated Next.js app, expected as:

```bash
npm run lint
npm run test
npm run build
```

## Open Decisions Resolved

- Scope: complete frontend skeleton with accounts, trading, and analytics rather than a single-page-only dashboard.
- Security: browser calls a Next.js proxy; bearer token remains server-side.
- Charting: Lightweight Charts for both daily price context and account asset curve.
- Market data: missing daily bar endpoint should not block trading UI; show an explicit chart empty state.
- State management: local client-side fetching first; no default React Query/SWR dependency.
- Authentication: no frontend login in the MVP.
