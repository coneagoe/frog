# Paper-Trading Valuation Gaps Design

## Scope

Implement GitHub issue #85, "Handle valuation gaps, stale prices, and snapshot recalculation." The work extends the established paper-trading NAV baseline contract without changing order matching, settlement, account lifecycle, market calendars, DAG behavior, or the initial `NAV=1.0` point.

Daily trading snapshots remain close-based. A final daily NAV is published only when every required position has a defensible close valuation.

## Valuation Outcomes

For each active position on a requested trade date, snapshot valuation resolves one of three outcomes:

1. **Current price**: an exact-date daily close exists. The snapshot uses it and records normal valuation quality.
2. **Stale suspended price**: the market-data source explicitly identifies the instrument as suspended for the requested date, and a latest valid close on or before that date exists. The snapshot uses that prior close and records a stale-price marker, the source price date, and affected instrument details.
3. **Unavailable valuation**: no exact-date close exists and either suspension is not explicitly identified or no earlier valid close exists. The service does not publish a final daily NAV. It creates or updates an unresolved valuation gap with the missing instruments and diagnostic details.

An absent bar alone is never treated as a suspension. This preserves the distinction between a normal suspended holding and a data outage or unsupported pricing source.

## Snapshot Persistence And Recalculation

The existing initial baseline remains immutable and independent of this flow. Trading snapshots have a controlled account/date identity for recalculation:

- A first successful valuation creates the trading snapshot.
- A retry with unchanged data updates the same logical trading snapshot or leaves it unchanged; it never adds a duplicate point.
- A late bar resolves a prior valuation gap and creates or updates the affected snapshot.
- A revised bar recomputes and updates the existing trading snapshot for the same account and date.
- If recomputation becomes unavailable, the final trading NAV is withdrawn or marked invalid according to the established valid-NAV contract, and the valuation gap becomes unresolved again.

All persistence operations are transactional and idempotent. Recalculation must not alter the initial point, cash-flow events, or unrelated trade dates.

## Service And API Boundaries

`SnapshotService` owns price resolution and snapshot-quality determination. It obtains exact-date bars first, permits prior-close fallback only after an explicit suspension signal, and delegates durable writes to the repository.

The repository owns idempotent trading-snapshot update-or-create behavior and valuation-gap lifecycle updates. A valuation gap is keyed and updated consistently so repeated failed calculations do not duplicate records.

A dedicated operator-facing recalculation API accepts a bounded account and date scope. It reuses snapshot valuation logic only; it does not rerun matching or rebuild order ledgers. The endpoint reports which dates were updated, remain unavailable, or could not be processed.

Snapshot API responses expose valuation quality, stale-price metadata, and unresolved-gap visibility needed by consumers. Analytics responses surface unresolved valuation gaps and quality information separately from the valid NAV series. Analytics and risk metrics continue to operate only on valid unit-NAV points and never substitute `total_assets` for a missing NAV.

## Error Handling And Data Integrity

- Per-position errors include enough symbol, market, requested-date, and source-date detail for operators to diagnose gaps.
- A stale result is valid only when the source explicitly declares suspension; it is not an invalid NAV.
- An unavailable result is an explicit gap, not a zero, previous NAV carry-forward, or absolute-assets fallback.
- Recalculation validates the same finite, positive NAV constraints as ordinary snapshot generation.
- Recalculation is scoped and repeatable so retries are safe after partial operational failures.

## Tests

Tests use existing service and API seams with mocked market data. They cover:

- exact-date valuation and normal quality;
- explicitly suspended positions using the latest valid close with stale markers;
- unmarked missing bars and missing historical closes producing visible unresolved gaps and no final NAV;
- matching's existing snapshot path respecting the same outcomes;
- late bars resolving a gap without duplicate snapshots;
- revised bars updating the existing affected snapshot idempotently;
- repeated recalculation calls preserving one logical trading point per account/date;
- snapshot and analytics API exposure of stale markers and unresolved gaps;
- analytics excluding unavailable or invalid NAV points while retaining the established initial baseline.

Focused verification runs the snapshot service, matching service, snapshot API, analytics service, and analytics API test modules, with PostgreSQL-dependent coverage through `tools/run_tests.sh` when required.

## Non-Goals

- Inferring suspension from a missing bar.
- Treating an arbitrary prior close as a valid price during an unclassified outage.
- Re-running matching, changing fill behavior, or changing settlement to repair valuations.
- Altering cash-flow, baseline, corporate-action, calendar, or timestamp contracts outside the narrow behavior needed for valuation quality and recalculation.
