# Paper Trading Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split paper trading frontend responsibilities so `/trade` only submits orders, `/accounts` owns positions and cash ledger by selected account, and `/orders` and `/trades` own historical data.

**Architecture:** Keep the existing Next.js App Router and direct client-side API calls. Reuse existing table/form/chart components, add two thin history pages, and move account detail loading into the accounts workspace without changing backend APIs.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript, Vitest, Testing Library, existing `/api/paper` proxy client.

## Global Constraints

- Use `npm` scripts inside `frontend/paper-trading`; use `uv run` only for repository Python commands.
- Do not change backend paper trading APIs.
- Do not change order matching behavior.
- Do not add filters, pagination, account detail routes, or tabbed history.
- Do not alter analytics behavior except for navigation coexistence.
- Keep table components in `features/trading/trading-tables.tsx` for this change.
- Do not commit unless the user explicitly asks.

---

## File Structure

- Modify `frontend/paper-trading/app/layout.tsx`: add `Orders` and `Trades` links to the main nav.
- Modify `frontend/paper-trading/app/trade/page.tsx`: keep route wrapper as-is unless imports require cleanup.
- Modify `frontend/paper-trading/features/trading/trade-page.tsx`: remove positions, orders, trades, cash ledger state/loading/rendering; keep account loading, chart, and order form.
- Modify `frontend/paper-trading/features/accounts/account-list.tsx`: support selectable rows or a select button while preserving delete behavior.
- Modify `frontend/paper-trading/features/accounts/accounts-page.tsx`: add selected account state and load/display positions and cash ledger.
- Modify `frontend/paper-trading/features/accounts/accounts-page.test.tsx`: cover account detail loading and selection.
- Create `frontend/paper-trading/app/orders/page.tsx`: Suspense route wrapper for historical orders.
- Create `frontend/paper-trading/features/history/orders-page.tsx`: account-scoped orders history with cancellation.
- Create `frontend/paper-trading/features/history/orders-page.test.tsx`: verify loading, rendering, cancellation refresh, and errors.
- Create `frontend/paper-trading/app/trades/page.tsx`: Suspense route wrapper for historical trades.
- Create `frontend/paper-trading/features/history/trades-page.tsx`: account-scoped read-only trades history.
- Create `frontend/paper-trading/features/history/trades-page.test.tsx`: verify loading and account switching.
- Optionally modify `frontend/paper-trading/app/globals.css`: add focused styles for selected account rows/buttons only if needed.

---

### Task 1: Simplify Trade Workspace

**Files:**
- Modify: `frontend/paper-trading/features/trading/trade-page.tsx`
- Test: add or update `frontend/paper-trading/features/trading/trade-page.test.tsx`

**Interfaces:**
- Consumes: `listAccounts()`, `OrderForm`, `PriceChart`, `useSearchParams()`.
- Produces: `TradePage` that no longer imports or calls `listPositions`, `listOrders`, `listTrades`, `listCashLedger`, or `cancelOrder`.

- [ ] **Step 1: Write the failing test**

Create `frontend/paper-trading/features/trading/trade-page.test.tsx` with mocks for `next/navigation`, `lightweight-charts`, and `@/lib/api-client`. Assert that the page renders `Submit paper orders`, `Chart symbol`, and `Limit Order`, and does not render `Positions`, `Orders`, `Trades`, or `Cash Ledger` headings. Also assert only `listAccounts` is called during load.

- [ ] **Step 2: Run the failing test**

Run: `npm test -- features/trading/trade-page.test.tsx`

Expected: FAIL because the current trade page still renders account state/history panels and calls history/account-state API functions.

- [ ] **Step 3: Implement the simplified trade page**

Update `TradePage` to keep only `accounts`, `selectedAccountId`, `symbol`, `loading`, and `error` state. Load accounts in `useEffect`, resolve the requested `accountId` from search params, and render only the chart symbol input, `PriceChart`, and `OrderForm`. Pass `onSubmitted={() => undefined}` to `OrderForm` so submission does not refresh history data.

- [ ] **Step 4: Run the focused test**

Run: `npm test -- features/trading/trade-page.test.tsx`

Expected: PASS.

---

### Task 2: Add Account Detail Selection

**Files:**
- Modify: `frontend/paper-trading/features/accounts/account-list.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.tsx`
- Modify: `frontend/paper-trading/features/accounts/accounts-page.test.tsx`
- Optionally modify: `frontend/paper-trading/app/globals.css`

**Interfaces:**
- Consumes: `listAccounts()`, `listPositions(accountId: number)`, `listCashLedger(accountId: number)`, `deleteAccount(accountId: number)`.
- Produces: `AccountList({ accounts, selectedAccountId, onSelect, onDelete })` where `selectedAccountId?: number | null` and `onSelect?: (account: Account) => void`.

- [ ] **Step 1: Write failing account detail tests**

Extend `accounts-page.test.tsx` mock to include `listPositions` and `listCashLedger`. Add a test that initial load selects the first account, calls `listPositions(1)` and `listCashLedger(1)`, and renders `Positions` plus `Cash Ledger`. Add a second test with two accounts that clicks/selects the second account and expects `listPositions(2)` and `listCashLedger(2)`.

- [ ] **Step 2: Run the failing tests**

Run: `npm test -- features/accounts/accounts-page.test.tsx`

Expected: FAIL because `AccountsPage` does not load positions or cash ledger yet.

- [ ] **Step 3: Extend `AccountList`**

Update `AccountList` props to accept optional `selectedAccountId` and `onSelect`. In the actions column, render a secondary `View` button when `onSelect` exists. Give the selected account a visible label such as `Selected` or a disabled selected button state. Preserve the existing delete button and its `Delete ${account.name}` aria-label.

- [ ] **Step 4: Implement account detail loading**

Update `AccountsPage` to track `selectedAccountId`, `positions`, `cashLedger`, and detail error state. After accounts load, select the first account when available and load its positions/cash ledger with `Promise.allSettled`. On account selection, clear old detail arrays before loading new account data. Keep the account list visible if detail loading fails.

- [ ] **Step 5: Render account detail cards**

Import `PositionTable` and `CashLedgerTable` from `features/trading/trading-tables`. Render two panels beside or below `Paper Accounts`: `Positions` and `Cash Ledger`. Use existing empty table states when arrays are empty.

- [ ] **Step 6: Run the focused tests**

Run: `npm test -- features/accounts/accounts-page.test.tsx`

Expected: PASS.

---

### Task 3: Add Historical Orders Page

**Files:**
- Create: `frontend/paper-trading/app/orders/page.tsx`
- Create: `frontend/paper-trading/features/history/orders-page.tsx`
- Create: `frontend/paper-trading/features/history/orders-page.test.tsx`

**Interfaces:**
- Consumes: `listAccounts()`, `listOrders(accountId: number)`, `cancelOrder(orderId: number)`, `OrderTable`.
- Produces: `OrdersPage` client component and `/orders` App Router route.

- [ ] **Step 1: Write failing orders page tests**

Create `orders-page.test.tsx` with mocks for `next/navigation` and `@/lib/api-client`. Test that the page loads the first account, calls `listOrders(1)`, renders an order row, calls `cancelOrder(orderId)` when clicking `Cancel`, and refreshes `listOrders(1)` after cancellation. Add an error test for cancellation failure showing `ErrorBanner` text.

- [ ] **Step 2: Run the failing tests**

Run: `npm test -- features/history/orders-page.test.tsx`

Expected: FAIL because `OrdersPage` does not exist.

- [ ] **Step 3: Implement `OrdersPage`**

Create `features/history/orders-page.tsx` as a client component using the same account-selection and stale-request protection pattern as analytics. Render header `Orders`, muted copy `Review and cancel historical paper orders.`, an account selector, loading/empty account states, `ErrorBanner`, and `OrderTable orders={orders} onCancel={onCancel}`.

- [ ] **Step 4: Add route wrapper**

Create `app/orders/page.tsx` that imports `Suspense` and `OrdersPage`, then renders `<Suspense fallback={<div className="panel">Loading orders...</div>}><OrdersPage /></Suspense>`.

- [ ] **Step 5: Run the focused tests**

Run: `npm test -- features/history/orders-page.test.tsx`

Expected: PASS.

---

### Task 4: Add Historical Trades Page

**Files:**
- Create: `frontend/paper-trading/app/trades/page.tsx`
- Create: `frontend/paper-trading/features/history/trades-page.tsx`
- Create: `frontend/paper-trading/features/history/trades-page.test.tsx`

**Interfaces:**
- Consumes: `listAccounts()`, `listTrades(accountId: number)`, `TradeTable`.
- Produces: `TradesPage` client component and `/trades` App Router route.

- [ ] **Step 1: Write failing trades page tests**

Create `trades-page.test.tsx` with mocks for `next/navigation` and `@/lib/api-client`. Test that the page loads the first account, calls `listTrades(1)`, renders a trade row, and switching the account calls `listTrades(2)` while the page remains read-only with no `Cancel` button.

- [ ] **Step 2: Run the failing tests**

Run: `npm test -- features/history/trades-page.test.tsx`

Expected: FAIL because `TradesPage` does not exist.

- [ ] **Step 3: Implement `TradesPage`**

Create `features/history/trades-page.tsx` as a client component using account selection and `requestIdRef` stale-response protection. Render header `Trades`, muted copy `Review historical paper executions.`, an account selector, loading/empty account states, `ErrorBanner`, and `TradeTable trades={trades}`.

- [ ] **Step 4: Add route wrapper**

Create `app/trades/page.tsx` that imports `Suspense` and `TradesPage`, then renders `<Suspense fallback={<div className="panel">Loading trades...</div>}><TradesPage /></Suspense>`.

- [ ] **Step 5: Run the focused tests**

Run: `npm test -- features/history/trades-page.test.tsx`

Expected: PASS.

---

### Task 5: Update Navigation And Full Frontend Verification

**Files:**
- Modify: `frontend/paper-trading/app/layout.tsx`
- Modify: `frontend/paper-trading/app/globals.test.ts` or create `frontend/paper-trading/app/layout.test.tsx` if navigation coverage is missing.

**Interfaces:**
- Consumes: existing `RootLayout`.
- Produces: global navigation links to `/accounts`, `/trade`, `/orders`, `/trades`, and `/analytics`.

- [ ] **Step 1: Add navigation coverage**

Create or update a layout test that renders `RootLayout` with sample children and expects links named `Accounts`, `Trade`, `Orders`, `Trades`, and `Analytics` with matching hrefs.

- [ ] **Step 2: Run the failing navigation test**

Run: `npm test -- app/layout.test.tsx`

Expected: FAIL until `Orders` and `Trades` links are added.

- [ ] **Step 3: Update `RootLayout` navigation**

Add `<Link href="/orders">Orders</Link>` and `<Link href="/trades">Trades</Link>` between `Trade` and `Analytics`.

- [ ] **Step 4: Run all frontend tests**

Run: `npm test`

Expected: PASS.

- [ ] **Step 5: Run lint and build**

Run: `npm run lint && npm run build`

Expected: PASS.

---

## Self-Review

- Spec coverage: Tasks cover trade simplification, account-selected positions/cash ledger, `/orders`, `/trades`, navigation, error handling, and verification.
- Placeholder scan: No `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: New props and page component names are consistent across tasks.
