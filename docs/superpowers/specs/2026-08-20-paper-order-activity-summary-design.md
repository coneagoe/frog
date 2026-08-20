# Paper-Order Activity Summary Design

## Goal

Replace the Analytics Activity period tables with backend-calculated average
paper-order activity summaries. The API and UI must make the reporting range
and unavailable state explicit, while preserving all other Analytics panels.

## API contract

`AnalyticsResponse.activity` becomes nullable. For an account with orders it
contains:

- `coverage_start`: earliest paper-order `trade_date`;
- `coverage_end`: current date in `Asia/Shanghai`;
- `daily`, `weekly`, and `monthly` summary objects;
- each summary object has numeric `total_orders`, `successful_orders`, and
  `failed_orders` values.

For an account with no paper orders, `activity` is `null`. No coverage or zero
averages are fabricated by either the service or frontend.

## Calculation

Activity uses paper orders, not trades. Every order in the coverage contributes
to `total_orders`; only orders with status `filled` contribute to
`successful_orders`, and only orders with status `rejected` contribute to
`failed_orders`. Other statuses contribute only to the total.

The daily denominator is every natural day from coverage start through end,
inclusive. The weekly denominator is every ISO week intersecting that range,
including the partial first and last weeks. The monthly denominator is every
calendar month intersecting the range, including partial first and last
months. Weekends, holidays, and zero-order periods are included. The clock or
current date is injectable in service tests; production uses the current
`Asia/Shanghai` date.

## Frontend behavior

The Activity panel removes the daily, weekly, and monthly detail tables. When
available, it shows the coverage range and the three summary units with total,
successful, and failed average orders. When unavailable, it shows an explicit
unavailable state. Overview, Execution, Trade Quality, and Risk panels retain
their current behavior.

## Testing and documentation

Service tests cover status aggregation, natural-day/ISO-week/calendar-month
denominators, partial boundaries, injected Shanghai current dates, and empty
accounts. API tests assert the new nullable response contract. Page tests cover
available summaries, unavailable activity, and preservation of non-Activity
panels. The paper-trading documentation is updated to describe the new
summary-based Activity behavior.
