# Paper Trading NAV Baseline Analysis

## Review Assertions

- [x] `UTC` normalization is documented for `event_at`; the UTC calendar date
  anchors affected snapshots and recalculation.
- [x] `event_at` and `(event_at, id)` ordering are documented for event storage
  and listing.
- [x] `idempotency` replay and conflict behavior are documented.
- [x] Internal financial values use `Numeric(30, 12)`; public display precision
  is separately documented.
- [x] The rounding mode is `ROUND_HALF_UP` and the
  `rounding_residual` equation is documented.
- [x] `dividend`, `split`, `reverse_split`, `bonus_share`, and `rights_issue`
  semantics are documented.
- [x] Internal cash is distinguished from external TWR cash flows.
- [x] No-holding events are documented as zero-impact audit events.
- [x] `valuation gap`, `stale price`, and bounded `snapshot recalculation`
  behavior are documented.
- [x] `migration` preservation and data-quality limitations are documented.

## Current Baseline Contract

Account creation persists one valid `initial` snapshot at NAV `1.000000`.
This is the baseline for unit-NAV analytics and is not derived by substituting
`total_assets`. It is created only for a new account with positive initial cash;
the persisted point has a real UTC `event_at` and remains the account's initial
identity.

Later transaction and valuation processing persists `trading` snapshots with
their real dates and UTC `event_at` values. A transaction can affect the
account ledger without becoming a chart point when its event is invalid or
when valuation is unavailable. Invalid snapshots retain their other stored
financial fields, set `net_asset_value` to null with an explicit quality reason,
and do not update account NAV state. A missing price creates a valuation gap;
the gap is reported separately and does not silently fall back to
`total_assets`. A stale suspended price can remain a valid, explicitly marked
valuation with `valuation_quality="stale_suspended"`.

Corporate-action quantity changes preserve NAV continuity where specified:
splits, reverse splits, and bonus shares change quantity while preserving
aggregate cost and the unit-value relationship; rights issues add both shares
and their subscription cost; dividends add internal corporate-action cash and
update unit NAV only when the account has shares. With no eligible holding, an
action is retained for audit but has zero economic impact. Corporate-action
cash is internal portfolio activity, whereas deposits and withdrawals are
external TWR cash flows and change scale rather than return.

## Recalculation And Ordering

Corporate-action processing starts at the UTC event date and performs bounded
snapshot recalculation through the latest affected trading snapshot or
valuation-gap date. The API returns `updated_dates`, `unavailable_dates`,
`failed_dates`, and `errors`. Recalculation preserves the initial baseline,
orders, and ledger facts, retains real trading dates, and can be repeated after
market data is available. It does not invent chart points for non-snapshot
events. Events are deterministic in `(event_at, id)` order, and an
`idempotency_key` replay returns the original result without applying a second
impact; a conflicting reuse is rejected.

## Migration And Limitations

The migration preserves existing snapshot financial values and does not rewrite
history to invent returns or infer provider corporate actions. PostgreSQL can
insert one `initial` NAV `1.000000` point for chronology-safe legacy accounts
that have positive initial cash and no initial point. Accounts with unprovable
ordering remain marked `legacy_ordering_uncertain` and require repair before
performance analytics; SQLite startup does not insert the baseline. Existing
legacy chronology, missing provider events, missing daily bars, stale prices,
and unresolved valuation gaps remain data-quality limitations rather than
being silently corrected.

Provider synchronization and provider-driven corporate-action DAG work are
explicitly excluded. Existing daily-history and matching DAG behavior is not
changed by this contract, and no DAG automatically creates corporate-action
events.
