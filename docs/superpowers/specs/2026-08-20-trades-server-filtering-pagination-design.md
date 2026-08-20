# Issue #76: Server-backed trade-date filtering and pagination

## Goal

Bring the paper-trading Trades history workflow to parity with the existing
Orders history workflow. Trades remain read-only, while filtering and
pagination are performed by the server and represented reproducibly in the
page URL.

## Scope and non-goals

In scope:

- Paginated, date-filtered Trades API responses.
- Repository support for inclusive date filtering, stable ordering, counting,
  and page slicing.
- Trades client types and query serialization.
- Today, trailing 7-natural-day, trailing 30-natural-day, and custom inclusive
  date controls using Asia/Shanghai calendar semantics.
- URL state for account, date range, explicit-range state, and page.
- Loading, API error, no-account, filtered-empty, and stale-response handling.
- API, repository, client/page, and documentation updates.

Out of scope:

- Trade mutations or new TradeTable actions.
- New filter dimensions beyond start/end trade dates.
- Changes to Orders behavior or shared abstractions unrelated to Trades parity.

## Backend design

Extend `GET /paper/accounts/{account_id}/trades` with the same query contract
used by Orders: inclusive `start_date` and `end_date`, one-indexed `page`, and
bounded `page_size`. Return the existing pagination envelope shape with trade
items, total item count, current page, page size, and total pages.

The repository query filters `PaperTrade.trade_date` inclusively, orders by
`trade_date DESC, id DESC` for deterministic results, counts the filtered
query, and slices the requested page. The API normalizes an over-large page to
the last valid page. If no rows match, it returns page 1 and zero total pages.
Invalid dates, reversed ranges, and invalid pagination values follow the
existing Orders validation behavior.

## Frontend design

Change `listTrades` and its types from a flat trade list to the pagination
envelope and serialize the same query parameters as `listOrders`.

`TradesPage` follows the established Orders interaction model:

- Fixed page size of 25.
- Presets for Today, trailing 7 natural days, and trailing 30 natural days.
- Custom inclusive start/end dates.
- Asia/Shanghai calendar-day calculations.
- Account, dates, explicit-range state, and page synchronized to `/trades`.
- Account or date-range changes reset the page to 1.
- Invalid custom ranges show validation feedback and do not issue a request.
- Account/request identity guards prevent stale responses from overwriting the
  current account, range, or page.
- The existing `TradeTable` remains read-only.

## Error and empty states

The page preserves the existing no-account and loading behavior, adds API error
handling for the paginated request, and distinguishes an empty filtered result
from an account with no trades. Pagination controls are shown only when the
response has multiple pages and remain consistent with normalized server
metadata.

## Verification

Add or extend tests for:

- Repository date filtering, stable ordering, counts, page slicing, empty
  results, and page normalization.
- API query validation, response envelope, filtered results, empty results,
  and final-page normalization.
- Client query serialization and response typing.
- Page URL restoration, default and custom date ranges, invalid ranges with no
  request, account/range/page pagination behavior, empty filtered results,
  errors, and stale responses.
- Updated paper-trading documentation describing Trades filtering and
  pagination.

## Acceptance criteria

Issue #76 is complete when Trades supports the Orders-equivalent server-backed
date filtering and pagination contract, URL state is reproducible, invalid
ranges make no request, stale responses cannot corrupt visible state, the
Trades table remains read-only, relevant tests pass, and the documentation
matches the implemented behavior.
