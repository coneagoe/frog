# Paper Trading Ledger Desk Redesign

## Context

`frontend/paper-trading` is a Next.js operational interface for paper accounts, order entry, historical order and trade review, and analytics. Its current dark, panel-heavy presentation does not prioritize daily historical review. The current history APIs return all records, and the Activity section exposes raw daily, weekly, and monthly buckets rather than the requested average summaries.

This redesign replaces the visual world while preserving the product's account, order, trade, and analytics functions. It adopts the confirmed **Ledger Desk** direction: a light, ledger-like operating surface designed for high-density scanning and regular review.

## Goals

- Replace the current dark visual system with a responsive Ledger Desk operating interface.
- Remove the Accounts cash ledger panel while preserving deposit and withdrawal behavior.
- Remove the standalone chart-symbol panel from Trade and place its input in the chart workspace toolbar.
- Add server-backed date filtering and pagination to Orders and Trades.
- Replace Analytics Activity detail tables with average order activity summaries supplied by the backend.
- Keep current business operations and existing data meanings intact except for the approved API contract extensions below.

## Non-Goals

- Do not alter order matching, account lifecycle, fee calculation, or portfolio valuation behavior.
- Do not change the fields or semantics of order submission.
- Do not add general column sorting, configurable page sizes, account-specific time zones, or a cash-ledger history replacement page.
- Do not report failed orders beyond the existing `rejected` order status.

## Visual Direction

### Mode and World

The surface mode is **Operate**. The workspace must optimize for accurate, repeated review, not marketing expression.

Ledger Desk uses a light neutral background, dark ink/green typography, fine grey-green rules, compact tabular layouts, and a restrained confirmation green. Red is reserved for rejected, failed, and risk states. Content is organized as a working ledger with clear contextual toolbars, not stacked floating-card sections. Numeric columns use tabular figures and align right. Desktop tables may be dense; mobile preserves toolbar and pagination operability and scrolls wide tables horizontally.

### Shared Layout

- Retain navigation for Accounts, Trade, Orders, Trades, and Analytics.
- Page headers establish route title, purpose, and the currently selected account.
- Historical pages use a persistent toolbar for account context and date selection.
- Use visible selected states and compact status treatment; do not use decoration that competes with data values.
- Preserve loading, error, empty, and unavailable states with distinct wording and appearance.

## Page Changes

### Accounts

- Preserve account creation, selection, deletion, fee editing, position import, deposits, and withdrawals.
- Remove the `Cash Ledger` card and stop loading its full history solely for display.
- Continue showing the selected account's positions and account actions.
- Expose `cash_available` in the account summary/detail data used by the page so the withdrawal modal can retain client-side availability validation without loading cash-ledger entries.
- Present account selection as a clear master-detail relationship.

### Trade

- Preserve account selection, `PriceChart`, and `OrderForm` fields and behavior.
- Remove the standalone `Chart symbol` card.
- Move the symbol input into a compact chart-workspace toolbar.
- Keep the order form in a stable, clearly separated action region on desktop; stack it below the chart on narrow viewports.

### Orders and Trades

Both pages receive the same history controls:

- Account selector.
- Preset date controls: past day, past week, and past month.
- Custom inclusive start and end `trade_date` inputs.
- Server-backed pagination with a fixed page size of 25.
- Default stable order: `trade_date DESC, id DESC`.
- URL state for `accountId`, selected range or explicit `start` and `end`, and `page`.

Preset ranges use the `Asia/Shanghai` calendar:

- Past day: today.
- Past week: today and the preceding six natural days.
- Past month: today and the preceding 29 natural days.

Changing account or date range resets to page 1. Invalid custom ranges show a local validation message and do not issue a request. Orders retain cancellation, deletion, and comment editing. After a mutation, reload the current query; if its page is now empty and its page number exceeds 1, load the preceding page. Trades remain read-only.

### Analytics

Keep Overview, Execution, Trade Quality, and Risk & Drawdown. Replace Activity's raw period tables with three summary units:

- Average daily orders, successful orders, and failed orders.
- Average weekly orders, successful orders, and failed orders.
- Average monthly orders, successful orders, and failed orders.

All three metrics use the same unit: orders. Successful means `filled`; failed means `rejected`. The interface also displays the reporting coverage range when available.

When an account has no orders, Activity is unavailable and displays `—`; it must not show a synthetic zero average or reporting range.

## Backend Contracts

### History Lists

Extend account-scoped order and trade list endpoints with optional query parameters:

- `start_date`: inclusive ISO business date.
- `end_date`: inclusive ISO business date.
- `page`: one-indexed page number, default `1`.
- `page_size`: fixed to `25` for the frontend contract; validate an upper bound server-side.

Both endpoints return a shared paginated shape:

```json
{
  "items": [],
  "page": 1,
  "page_size": 25,
  "total_items": 0,
  "total_pages": 0
}
```

Records are filtered by `trade_date` and sorted by `trade_date DESC, id DESC` before pagination. A page request above the final page returns the final valid page and its accurate pagination metadata; an empty result set returns page `1` and `total_pages: 0`. Existing consumers that require a full list must be migrated deliberately or supported through a compatibility path; the contract must not silently break them.

### Account Summary

Expose a decimal `cash_available` field through the account data consumed by the Accounts page. Its source must be the authoritative account balance calculation, not a frontend sum of ledger entries.

### Analytics Activity Summary

The analytics response supplies an Activity summary calculated in the backend:

```json
{
  "coverage_start": "2026-08-01",
  "coverage_end": "2026-08-19",
  "daily": { "order_count": "1.2", "success_count": "0.8", "failure_count": "0.1" },
  "weekly": { "order_count": "6.0", "success_count": "4.0", "failure_count": "0.5" },
  "monthly": { "order_count": "12.0", "success_count": "8.0", "failure_count": "1.0" }
}
```

The precise schema naming may follow local conventions, but it must communicate the coverage range and all three averages. The backend owns all numerator and denominator calculations.

For an account with at least one order, coverage begins on the earliest order `trade_date` and ends on the current `Asia/Shanghai` date. For each average, the denominator includes every intersecting natural period:

- Daily: every natural day, including weekends, holidays, and zero-order days.
- Weekly: every ISO week intersecting the coverage range, including partial first and last weeks.
- Monthly: every calendar month intersecting the coverage range, including partial first and last months.

Order totals, successes, and failures aggregate within their natural periods. A period with no applicable orders contributes zero. `failed` is not a separate order status for this work; failures are rejected orders only. An account with no orders returns no coverage and unavailable Activity values.

## Data Flow and State

- History pages derive query state from URL search parameters and write updated selection state back to the URL.
- Backend query execution owns filtering, sorting, total counts, and pagination. The frontend never derives Analytics summaries from a loaded history page.
- Account or date changes invalidate prior history responses and reset page state. Request identity guards prevent stale responses from overwriting newer selections.
- Orders mutations reload the active query and recover to the preceding valid page when necessary.
- Analytics renders only the summary contract; it does not need raw activity bucket detail data for this surface.

## Error Handling

- Invalid dates and a start date after an end date block the history request and show a local actionable message.
- API errors keep the selected account and current query controls visible, with an error banner near the affected result region.
- Empty filtered pages show an empty-result state distinct from no-account and loading states.
- Page requests beyond the available range resolve to the final valid page using the backend's returned pagination metadata, without presenting a broken pager.
- Accounts page withdrawal behavior surfaces backend errors even though it receives `cash_available` for client-side validation.

## Verification

### Backend

- Test date filtering, `trade_date DESC, id DESC` ordering, total counts, page boundaries, and invalid page/date inputs for orders and trades.
- Test Analytics summaries for zero-order days, weekends and holidays, partial first and last ISO weeks/months, cross-month and cross-year coverage, `Asia/Shanghai` current-date behavior, filled/rejected aggregation, and no-order accounts.
- Test account summary `cash_available` uses the authoritative balance calculation.

### Frontend

- Test history URL initialization and updates, presets, inclusive custom dates, validation, page reset, pager availability, and response rendering.
- Test order cancellation/deletion refresh behavior and automatic previous-page recovery.
- Test Account withdrawal behavior after cash-ledger removal.
- Test Activity summary rendering, coverage display, and unavailable no-order state.
- Update affected API-client, route, page, and table tests for the new response contracts.

### Visual

- Verify desktop and mobile screenshots together after implementation.
- Batch-fix all found visual, spacing, responsive, and control-state defects once, then run one final confirmation round.
- Run the Impeccable detector once on changed UI targets before the finish handoff.
