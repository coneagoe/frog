# Paper Trading ETF Raw Daily Data Design

## Goal

Use raw ETF daily bars from `etf_daily` consistently for Paper Trading ETF
matching, latest-close valuation, and snapshots. Repair existing Paper Trading
orders that were recorded as A shares when their six-digit symbol is present in
the ETF catalogue.

## Context

`etf_daily` is the maintained raw ETF price table. It contains `518880` through
2026-08-12, including the 2026-08-07 bar with open 8.775, high 8.892, low 8.774,
and close 8.892. The existing Paper Trading ETF market-data route reads
`history_data_daily_etf_qfq`, which has no rows for that symbol. The current
order `41` for account `6` is therefore stored as `a_share`, leaves matching
with a missing-date warning, and has no valid A-share daily bar.

## Price Contract

For `market="etf"`, Paper Trading uses only `etf_daily`:

- Matching reads its exact-date raw open, high, low, and close.
- Latest-close queries load raw ETF data through the requested valuation date
  and use the last available close.
- Snapshots use the same raw close through `MarketDataProvider`.
- ETF daily bars continue to carry no A-share limit prices and are never
  queried from the A-share limit table.

`history_data_daily_etf_qfq` and `history_data_daily_etf_hfq` remain unchanged
for non-Paper-Trading analysis. No raw data is copied into those tables.

## Historical Repair

Use `general_info_etf.基金代码` as the authoritative market-classification
catalogue for six-digit Paper Trading order symbols. A matching code is created
with `market="etf"`; nonmatching codes retain the existing market decision.
`paper_etf_eligibility` continues to own ETF eligibility and governance, but is
not a prerequisite for assigning the ETF market. This prevents future orders
from repeating the historical A-share classification error.

Add an explicit, idempotent Paper Trading repair operation. It identifies every
existing `paper_orders` row whose `market` is `a_share` and whose six-digit
`symbol` exists in `general_info_etf.基金代码`. For each affected order, set the
order market to `etf`. Rebuild each affected account incrementally from its
earliest corrected order date using the existing replay workflow. Execution
history before that date is retained; derived state at and after that date is
rebuilt from persisted orders.

The operation is explicit rather than startup behavior. Its CLI first reports
candidates without writes; `--apply` is required to make changes. It executes
in one locked database transaction per account and returns a structured summary
containing candidate, corrected, skipped, and failed account IDs, corrected
order IDs, and each account's replay start date. A failed account transaction
rolls back independently, and a rerun with no remaining incorrectly classified
orders is a no-op. Matching must not perform market reclassification implicitly.

Current data identifies exactly one affected record: account `6`, order `41`,
symbol `518880`, replay start date `2026-08-07`. With the raw bar, its limit
price 8.818 lies within the [8.774, 8.892] range and should fill when replayed.

## Interfaces

Extend the storage abstraction with a raw ETF daily loader already implemented
by `StorageDB` as `load_etf_daily(etf_id, start_date=None, end_date=None)`. The
Paper Trading market-data provider invokes this method only for `market="etf"`.

Expose the historical repair through the existing Paper Trading API and CLI as
an explicit operator command. The API delegates to a service that owns catalogue
matching, market updates, account grouping, locking, and replay invocation. It
does not accept a caller-provided list of symbols, preventing partial or ad hoc
classification rules.

## Error Handling

An absent raw ETF bar remains a `KeyError` and produces the existing missing
exact-date warning; it does not fall back to adjusted ETF or A-share data.
Malformed or missing raw OHLC fields remain validation errors. If any account
repair fails, that account transaction rolls back and the response reports its
failure without claiming it was repaired. The command returns a nonzero status
when any account fails.

## Testing And Verification

Tests cover raw ETF exact-date matching, raw latest-close lookup, raw ETF
snapshot valuation, absence of adjusted-history and A-share-limit calls, and
missing raw data behavior. They also cover future order market assignment from
the ETF catalogue. Repair tests use a fake ETF catalogue plus orders in both
eligible and ineligible categories to prove only catalogue-matched A-share
orders are converted, each affected account replays once from its earliest
corrected date, dry-run does not write, failed account repairs roll back, and
no-op reruns do not rebuild accounts.

After deployment, run the repair command with `--apply`, inspect its summary,
retrieve order 41, validity checks, matching runs, trades, positions, lots,
round trips, cash ledger, valuation gaps, diagnostics, and the 2026-08-07
snapshot. Confirm that each replayed item has ETF-consistent market data, order
41 has `market="etf"`, it is filled at the matching price, and its account uses
the raw `etf_daily` close for valuation. Preserve the pre-existing A-share
missing-date diagnostic as historical evidence; successful ETF replay must not
create an ETF missing-date diagnostic.

## Scope

This change does not alter ETF order eligibility policy, fee rules, T+1 rules,
the ETF catalogue ingestion process, raw ETF downloads, or the adjusted ETF
history tables. It does not automatically change future order market selection;
existing order-creation eligibility behavior remains authoritative.
