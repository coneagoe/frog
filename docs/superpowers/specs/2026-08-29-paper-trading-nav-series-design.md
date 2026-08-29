# Paper-Trading NAV Series Repair Design

## Goal

Complete issue #82 by making the paper-trading NAV baseline and performance
series consistent across persistence, replay, analytics, API, and frontend
consumers. The system must preserve auditable event history, avoid fabricating
historical returns, and recompute derived state deterministically when late
cash-flow, corporate-action, or market data arrives.

## Scope

The change covers:

- creation and migration of the `initial` NAV point;
- event-ordered replay of cash flows, trades, corporate actions, and valuations;
- bounded, idempotent recomputation after late or revised events;
- cash-only account snapshot selection;
- explicit SQLite legacy compatibility behavior;
- a shared valid NAV series for analytics and risk metrics;
- API data-quality, timestamp, point-type, and valuation-gap contracts;
- frontend repair-state and valuation-gap behavior;
- acceptance-level backend and frontend tests.

Order matching and settlement remain immutable facts. Replay updates derived
account state, snapshots, valuation gaps, and analytics inputs without changing
order or trade semantics.

## Architecture

Introduce an internal event adapter/replay boundary rather than a parallel
accounting model. Existing ledger, order/trade, position, snapshot, and
corporate-action records are converted into ordered replay events:

```text
initial -> cash_flow -> trade_settlement -> corporate_action -> market_valuation
```

Every event has a timezone-aware `event_at`, market `trade_date`, source ID,
event type, and data-quality metadata. Events are normalized to UTC for sorting,
with stable source-ID tie breaking. The replay boundary owns construction of
the valid NAV series used by snapshot persistence, analytics, risk metrics, API
responses, and the chart adapter.

Historical accounts are handled conservatively. A baseline is inserted only
when creation state and initial shares can be proven from existing records. The
current `account.share_count` is never treated as historical initial shares. If
chronology or creation state cannot be reconstructed, the account is marked
`legacy_ordering_uncertain` (or the repository's equivalent repair reason), and
performance analytics remain unavailable.

## Accounting Rules

### Initial point

Account creation persists exactly one idempotent `initial` snapshot at the
creation timestamp with:

- unit NAV `1.000000`;
- initial shares equal to initial cash;
- the account's initial cash and share state;
- explicit valid data quality.

### Cash flows

Deposits mint shares and withdrawals redeem shares at the last valid NAV before
the event, or NAV 1.0 when no prior valid NAV exists. The cash-flow event does
not itself create investment return; unit NAV remains unchanged at the event
boundary. Decimal arithmetic is used for accounting, with distinct accounting,
storage, and display precision. Rounding residuals remain auditable.

An event inserted before existing snapshots triggers replay from the event's
effective timestamp. All affected derived snapshots and analytics inputs are
updated consistently. If the prior state cannot be proved, the operation is
rejected or the account is marked for repair rather than applying an unsupported
historical adjustment.

### Trades and valuations

Existing matching and settlement results remain authoritative. Replay applies
those results in event order and regenerates affected derived snapshots. Daily
valuation uses close prices. Missing required market data produces an explicit
valuation gap and no false continuous valid NAV. Suspended instruments may use
the latest valid close with a stale-price marker.

Cash-only accounts are included in date-driven snapshot selection for the
account's active valuation interval, even when they have no open positions and
no orders on that date.

### Corporate actions

Splits, reverse splits, bonus shares, rights issues, and dividends are replayed
at their effective event time with explicit quantity, cost, and cash rules.
Late actions are applied idempotently and trigger bounded replay from the
affected date. Historical state is replayed in event order; if an action cannot
be ordered relative to a trade, the account enters repair state instead of
guessing. Corporate-action effects remain traceable through existing audit
records and cash-ledger metadata.

## API and Frontend Contract

Snapshot and analytics responses expose timezone-aware event timestamps,
`point_type`, valid NAV/share fields, quality status, repair state, and
valuation gaps. A valuation gap includes its date, missing symbols, details,
and resolved status. Invalid, non-finite, zero, or negative NAV values are
excluded from the valid unit-NAV series and are never replaced with
`total_assets`.

For repair-marked accounts, the analytics API returns an explicit unavailable
response. The frontend hides performance summary, risk, and performance chart
content rather than falling back to raw snapshots that could imply unsupported
returns. It shows the repair explanation and any safe non-performance account
information. Available accounts display valuation gaps, including unresolved
versus resolved state, without treating gaps as valid returns.

## Testing and Verification

Add or update tests at the existing repository, service, API, and frontend
seams. Required scenarios include:

- creation baseline persistence, timezone ordering, and idempotency;
- legacy migration after prior deposits/withdrawals, including correct initial
  shares and repair behavior when chronology is uncertain;
- backdated deposits and withdrawals with consistent later snapshots, shares,
  NAV, and time-weighted return;
- same-day ordering of initial, cash-flow, trade, withdrawal, and corporate
  action events;
- cash-only date-driven snapshots;
- missing, stale, revised, and recalculated valuation data;
- historical corporate-action replay and idempotency;
- explicit SQLite legacy compatibility responses;
- API point types, timestamps, quality, gaps, and unavailable states;
- frontend filtering, repair-state chart suppression, and gap rendering.

Verification uses the repository's required `uv run` Python commands, the
PostgreSQL-aware `tools/run_tests.sh` runner where needed, and the frontend
test/lint commands defined by `frontend/paper-trading/package.json`.

## Non-Goals

- changing order matching, settlement, DAG schedules, task boundaries, retries,
  or SLAs;
- live brokerage integration;
- replacing the existing fund-style NAV/share model;
- guessing uncertain historical cash-flow or corporate-action order;
- building a separate frontend page or a new ingestion system for corporate
  actions.
