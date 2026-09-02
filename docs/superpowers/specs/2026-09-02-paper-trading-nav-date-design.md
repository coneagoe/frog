# Paper Trading NAV Date Repair Design

## Problem

Historical paper-trading NAV snapshots have correct business dates in
`trade_date`, but some rows have an `event_at` equal to the batch recalculation
time. The analytics chart currently uses `event_at`, causing multiple historical
NAV points to appear on one date, such as `2026-09-01`.

## Goals

- Make trading snapshot timestamps deterministic and derived from their
  business date.
- Expose `trade_date` explicitly in analytics snapshot events.
- Make the NAV chart use `trade_date` rather than a mutable processing time.
- Provide an authenticated, scoped, dry-run-by-default repair for existing
  trading snapshots.
- Preserve snapshot IDs and leave non-target accounts and dates unchanged.

## Design

### Canonical snapshot timestamp

For `point_type=trading` snapshots, the canonical timestamp is
`datetime.combine(trade_date, time.max, tzinfo=timezone.utc)`. The repository
will enforce this invariant for all trading snapshot upserts, including normal
matching and recalculation. Initial snapshots remain lifecycle events and keep
their existing creation-time semantics.

Snapshot recalculation will stop preserving an existing wall-clock `event_at`
for trading rows. Recalculation will pass the canonical timestamp derived from
each `trade_date`.

### Analytics contract and chart

`SnapshotAnalyticsEvent` will include a required `trade_date: date`, populated
from the persisted snapshot. The frontend analytics type will mirror this
field. `AssetChart` will construct each daily chart point from the date at a
deterministic UTC time, retaining its existing monotonic adjustment for multiple
events that share a date. The analytics route and API client remain unchanged.

### Existing-data repair

Add a repair service and authenticated endpoint under the existing repairs
router. The repair accepts an account ID and an inclusive date or date range,
targets only trading snapshots, and supports dry-run by default plus explicit
apply mode. It updates rows in place only when `event_at` differs from the
canonical value, reports bounded counts/results, and is idempotent.

Extend `tools/paper_trading_cli.py` with a matching repair subcommand using the
existing JSON output, date validation, authentication, and explicit apply
conventions. The operator will run the repair for account 6's affected range,
then may run it for other accounts as needed.

## Error handling and safety

- Reject invalid dates and inverted ranges at the request/CLI boundary.
- Reject unknown accounts.
- Use the existing account lock and transaction/rollback conventions for repair
  writes.
- Dry-run performs no writes.
- Repair updates only rows matching the requested account, date range, and
  trading point type.

## Verification

- Unit tests verify canonical timestamps in snapshot generation and repository
  upserts, including recalculation and repeated execution.
- API tests verify analytics `trade_date` serialization and repair
  authentication, scoping, dry-run/apply behavior, and idempotence.
- CLI tests verify date validation and exact repair payloads.
- Frontend tests verify chart dates come from `trade_date` and preserve ordering.
- Run focused backend/frontend tests, then the repository's formatting, lint,
  type-check, and integration test gates as appropriate.

## Out of scope

- Changing the meaning or storage of `trade_date`.
- Changing analytics route shape beyond adding the event field.
- Altering DAG schedules, matching boundaries, or valuation calculations.
