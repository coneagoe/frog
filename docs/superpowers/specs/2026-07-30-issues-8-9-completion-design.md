# Issues 8 and 9 Completion Design

## Goal

Close the remaining acceptance gaps for warning-tolerant daily-history
aggregation and repeatable paper-trading matching without replacing the
existing business-date, diagnostic, or duplicate-run mechanisms.

## Scope

### Issue 8: Daily-History Summary

Retain the existing partition aggregation contract in
`dags/download_stock_history_daily.py`:

- Complete and warning-only outcomes write a Redis summary with
  `result=success`.
- Warning summaries set `status=warning` and include the business date,
  sorted unique missing symbols, and no more than 20 deterministically ordered
  provider-evidence records.
- Invalid partition data, infrastructure errors, and diagnostic-persistence
  errors remain task failures and therefore prevent matching.

Focused DAG tests will explicitly preserve the complete-success,
warning-success, and fatal-failure contracts. No Redis schema or downstream
matching trigger redesign is included.

### Issue 9: Batch Matching Failure Semantics

Keep the current one-date matching flow and its accepted-order query,
exact-date BFQ lookup, retry behavior, and active-run serialization. Tighten
only the missing outcome distinctions:

- A missing exact-date daily bar is a warning. The affected order remains
  accepted, and a `DailyBarDiagnostic` is upserted with
  `missing_exact_date` evidence.
- An exception while filling, settling, recording a trade, or updating
  related state is fatal to the matching run. Its failure details are persisted
  on the run; it must not be reported as `completed` or
  `completed_with_warnings` merely because snapshots succeeded.
- `match_order` uses the same missing-bar diagnostic behavior as the batch
  path. It returns a warning-class outcome for unavailable exact-date data,
  while unexpected market-data and fill errors remain failed outcomes.

The run status precedence is: fatal order or snapshot failures produce
`failed`; otherwise one or more missing-data or valuation-gap warnings produce
`completed_with_warnings`; otherwise the run is `completed`.

## Data Flow

The daily-history DAG persists a warning-capable Redis result before invoking
matching for the same business date. Matching loads only accepted orders and
processes each independently. Missing daily bars generate durable diagnostics
and preserve retry eligibility; available bars can fill. Once processing is
finished, the run aggregates its counts, warning count, and fatal error details
into a status using the defined precedence.

## Error Handling

Missing market data is a normal, recoverable warning only when the provider
explicitly reports that the exact-date bar is absent. All other provider,
persistence, trade, cash, position, and snapshot exceptions remain fatal.
Fatal errors must include enough account/order context in `error_details` to
support operational investigation while retaining the existing per-order loop
so independent orders can still be attempted.

## Testing

Focused tests cover:

1. Daily-history complete, warning-only, and fatal aggregation behavior.
2. Mixed matching where available orders fill and missing-bar orders remain
   accepted with persisted evidence.
3. A fatal order-processing error produces a failed matching run rather than a
   warning or completed run.
4. `match_order` persists the same missing-bar diagnostic as batch matching.
5. Existing same-date retry, terminal-order exclusion, and duplicate-active-run
   tests remain green.

## Out of Scope

- Replacing PostgreSQL locking or the active-run uniqueness strategy.
- Expanding the matching API response with new diagnostic payload fields.
- Altering order types, fee calculations, settlement behavior, or DAG schedule
  and dependency boundaries.
- Retrospective changes to historical matching runs or Redis records.
