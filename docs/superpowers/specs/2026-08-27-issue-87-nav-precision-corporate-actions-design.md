# Issue #87: NAV Precision and Corporate Actions Design

## Scope

Complete the paper-trading NAV contract after issues #84, #85, and #86. The
work covers high-precision accounting, auditable cash-flow rounding, internal
corporate-action processing, API exposure, documentation, and final backend,
frontend, and integration verification.

Corporate actions are entered through the application and are not synchronized
from an external market-data provider in this issue.

## Goals and Decisions

- Internal NAV, share, quantity, price, and money calculations use `Decimal`.
- Persisted accounting values use 12 decimal places (`Numeric(30, 12)`), while
  existing display formatting remains unchanged.
- Cash-flow share rounding uses the repository's explicit, documented rounding
  mode. The persisted residual is the requested amount minus the amount
  represented by the persisted share delta multiplied by the effective NAV.
- Existing ledger rows receive a zero residual during migration; historical
  amounts and snapshots are not rewritten.
- Corporate actions are single-security events with an account, security code,
  timezone-aware event timestamp, event type, idempotency key, and
  type-specific parameters.
- Supported types are dividend, split, reverse split, bonus share, and rights
  issue.
- A successful event and all resulting ledger/position changes are committed in
  one transaction. Invalid input, insufficient cash, invalid holdings, or an
  idempotency conflict rolls back the complete request and leaves no rejected
  business event row.
- Replaying an identical idempotency key returns the original result without
  applying the event twice. Reusing the key with different content is a
  conflict.

## Corporate-Action Semantics

### Dividends

Dividend cash equals the eligible pre-event quantity multiplied by the
per-share dividend. It is credited to available cash and recorded as an
internal corporate-action cash-flow ledger entry. It is not classified as an
external deposit or withdrawal and is excluded from external cash-flow TWR
adjustments.

### Splits and reverse splits

The position quantity is multiplied by the supplied ratio. Reverse splits use
the same ratio representation with a factor below one, or an equivalent
validated ratio contract. The position's cost basis per share is adjusted
inversely so total cost basis remains continuous. No cash flow is created.

### Bonus shares

Bonus quantity equals the eligible pre-event quantity multiplied by the bonus
ratio and is added to the holding. Total cost basis is unchanged and cost basis
per share is diluted accordingly. No cash flow is created.

### Rights issues

The event supplies a subscription ratio and subscription price. The system
automatically subscribes the eligible pre-event holding in full, deducts the
required cash, and adds the subscribed quantity. Insufficient available cash
rejects the complete event. Rights issues are internal corporate-action
activity, not external deposits or withdrawals.

Events for which the account has no target holding remain auditable with zero
position/cash impact. Rights issues also have zero impact when there is no
eligible holding.

## Data Model and API

Add a corporate-action event model and governed enum migration. The event row
stores account/security identity, event type, event timestamp, idempotency key,
validated type parameters, processing metadata, before/after quantity and
cost/cash summaries, and the affected date range. Add indexes for account,
security, event time, and the unique account/idempotency-key pair.

Extend the cash ledger with a 12-decimal `rounding_residual` field and expose
the residual in audit-oriented responses. Add a `corporate_action` event type
to the analytics audit event series. Corporate-action events are auxiliary
audit events; only valid NAV snapshots are chart points.

Provide:

- `POST /accounts/{account_id}/corporate-actions` to validate and apply one
  event.
- `GET /accounts/{account_id}/corporate-actions` with optional security,
  event-type, and event-time range filters, sorted by `(event_at, id)`.

The create response includes the persisted event, its accounting impact, and
snapshot recalculation results. The query response includes event parameters,
impact summaries, and audit timestamps. API validation requires finite,
strictly positive values where applicable and timezone-aware `event_at`.

## Processing and Recalculation

The service locks the account and target holding, validates the idempotency
key and event parameters, calculates all changes with high-precision Decimal,
then writes the corporate-action row and ledger/position/account changes in a
single transaction. The event timestamp participates in the existing
`(event_at, id)` ordering contract.

After commit, bounded snapshot recalculation covers the event date and all
later existing snapshot or valuation-gap dates affected by the change. The
operation is idempotent and preserves explicit valuation gaps and existing
data-quality rules.

Corporate actions do not alter external cash-flow totals or introduce external
TWR discontinuities. The resulting NAV series must remain continuous for
split, reverse-split, and bonus-share quantity changes; dividend and rights
issue effects are represented by the internal ledger and resulting holdings.

## Migration and Compatibility

PostgreSQL and SQLite startup upgrades add the corporate-action enum/table,
indexes, precision widening, and cash residual column. Existing values remain
semantically unchanged; residual defaults to zero. Migration is repeatable and
must preserve legacy account repair markers, snapshots, cash ledger history,
and analytics availability decisions.

Update `tools/db_common.sh` for any new persistent table so database export and
import remain synchronized.

## Documentation

Update the affected paper-trading documentation and the stale NAV baseline
analysis note to define:

- UTC-normalized event timestamps and trading-date/calendar interpretation.
- Event ordering and idempotency.
- Internal precision, display rounding, rounding mode, and residual meaning.
- Dividend, split, reverse split, bonus-share, and rights-issue semantics.
- The distinction between internal corporate-action cash and external TWR cash
  flows.
- Valuation gaps, stale prices, snapshot recalculation, migration, and data
  quality limitations.

## Verification

### Domain and service tests

Cover high-precision NAV/share/money operations, both cash-flow rounding
directions and residuals, repeated idempotency, conflicting idempotency keys,
each corporate-action type, cost-basis continuity, no-holding zero impact,
rights-issue full subscription, insufficient-cash rollback, and snapshot
recalculation.

### Storage and migration tests

Cover enum/table/column upgrades, precision widening, zero residual defaults,
unique constraints, indexes, repeatable migration, transaction rollback, and
legacy history preservation.

### API and frontend tests

Cover create/query schemas, filters, ordering, timezone validation, error
mapping, impact and recalculation responses, corporate-action audit event
rendering, and the invariant that invalid or non-snapshot events never become
chart points.

Run focused paper-trading tests, PostgreSQL migration/integration tests, the
frontend analytics tests, Ruff/mypy, pre-commit, and the full test runner before
closing the issue.

## Delivery Boundaries

1. Implement precision widening and cash-flow residual accounting.
2. Implement corporate-action domain, storage, transactions, migration, API,
   and audit events.
3. Complete frontend support, documentation updates, and full verification.

No automatic provider synchronization, unrelated refactoring, or changes to
DAG schedules, dependencies, retries, task boundaries, or SLAs are included.
