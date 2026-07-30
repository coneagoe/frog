# Resilient A-Share EOD Matching Design

## Goal

Make weekday A-share daily-history processing reproducible by business date,
observable when individual symbols lack daily bars, and safe for end-of-day
paper-trading matching.

## Scope

This design implements the approved ticket graph: business-date history
downloads, durable provider diagnostics, warning-tolerant summaries, queued
explicit-date paper orders, safe batch matching, daily workflow integration,
and observable partial-data snapshots.

TuShare `suspend_d` remains supporting evidence only. It does not establish a
full-day effective suspension status and therefore cannot cause automatic order
rejection in this scope.

## Business Date

The A-share business date is the Airflow logical date converted to `LOCAL_TZ`
and reduced to a calendar date. This date is the sole date used for BFQ and
HFQ history requests, diagnostics, Redis summaries, and paper-trading batch
matching. Worker wall-clock time must not select any of those dates.

If the business date is not an A-share trading date, the entire weekday
workflow is skipped: it does not download history, write a summary, or run
matching.

## Daily-History Outcomes

Each BFQ and HFQ partition returns a structured outcome. A per-symbol outcome
distinguishes:

- a successfully persisted daily-history result;
- an all-provider empty-data result;
- a provider-error result, retaining all provider outcomes;
- a fatal persistence or workflow failure.

The aggregate preserves a durable diagnostic for each symbol/date/adjustment
context that lacks usable data or has provider errors. Diagnostics retain the
business date, symbol, classification, bounded provider evidence, observed
timestamps, and resolution/retry state. Database export and import include the
diagnostic table.

A run with only isolated missing-data or provider-warning outcomes is a
successful warning run. Its Redis summary keeps `result=success` for existing
consumers and adds `status=warning`, the business date, missing symbols, and a
bounded provider-evidence summary. Fatal infrastructure or diagnostic
persistence failures remain workflow failures.

## Queued Orders

Paper-trading order creation requires an explicit `trade_date`. The service
validates that date against the market calendar. Historical trade dates are
allowed only when they are eligible unresolved retry dates.

Creating an accepted order reserves cash or position quantity but does not
invoke matching and does not create a trade. A repeated request with the same
idempotency key returns the original order and does not create a second
reservation.

## Batch Matching

Batch matching processes accepted orders for one business date and account
scope. Duplicate requests for the same scope queue behind an active matching
run. Eligible accepted orders are protected from concurrent processing so that
no run can create duplicate trades, cash events, or position mutations.

Matching fetches only an exact-date BFQ daily bar. A symbol with a usable bar
follows existing daily-range matching behavior. A symbol without a bar leaves
its order accepted and records a missing-market-data warning; matching
continues for other symbols. A rerun retries only still-accepted orders;
filled and rejected orders remain terminal.

Matching runs expose warning-level missing market data separately from fatal
failures. Run and diagnostic state must survive partial processing sufficiently
to support investigation and safe retry.

## Daily Workflow Integration

After a complete or warning-only A-share daily-history result, the workflow
invokes batch matching using the same business date. It does not invoke
matching after a closed-date skip or fatal daily-history failure.

This makes matching per-symbol: orders for symbols with available exact-date
bars can fill, while orders without daily data remain accepted for a later
business-date retry.

## Snapshot Behavior

End-of-day snapshot processing provides an explicit snapshot or valuation-gap
outcome for accounts with positions or same-date activity. Missing exact-date
data never becomes a prior-close execution price. Partial matching and snapshot
failures remain auditable and a retry must not duplicate already completed
fills.

## Deferred Suspension Handling

The existing suspension event table stores `S` and `R` events, not an
authoritative effective per-symbol daily trading status. Until a verified
full-day suspension source is available, missing daily data does not reject an
order. It remains accepted with diagnostics.

When an authoritative full-day status is introduced, a confirmed suspension
may use the existing rejected-order path. Rejection must release buy-side
frozen cash or sell-side frozen quantity exactly once and must remain terminal
on retries.

## Testing

The primary high-level seams are:

1. The daily-history Airflow workflow run with a supplied logical date and
   fake provider outcomes. Tests assert task state, persisted data and
   diagnostics, Redis summaries, and matching invocation behavior.
2. The authenticated paper-trading order and matching API. Tests assert queued
   accepted orders, idempotency replay, exact-date matching, pending
   missing-data orders, same-date retries, and duplicate-run serialization.

Focused persistence and service tests support these seams for all-empty,
mixed empty/error, successful fallback, fatal persistence failure, retry
resolution, concurrent matching, and snapshot valuation gaps. Tests assert
observable behavior rather than private helper calls.

## Out of Scope

- Treating TuShare suspension events as authoritative full-day or multi-day
  suspension status.
- Rejecting an order solely because its exact-date bar is missing.
- A new external exchange-notice ingestion service.
- Using prior closes or other stale prices as execution prices.
- Broad changes to paper-trading order types, fee rules, or settlement rules;
  market-specific calendar behavior remains intact.
- Retrofitting task logs for historical Airflow `upstream_failed` instances.
