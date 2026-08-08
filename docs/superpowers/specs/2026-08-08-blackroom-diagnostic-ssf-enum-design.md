# Blackroom, Diagnostic, and SSF Enum Governance Design

## Goal

Make Blackroom records, daily-bar diagnostics, and SSF change signals enforce
their application-defined finite values at both application persistence
boundaries and PostgreSQL persistence boundaries. Preserve all existing
observable labels and workflows while adding this domain to the unified enum
governance command introduced by issue #34.

## Domain Contracts

Add a storage-owned domain enum module as the canonical application definition
for these readable persisted labels:

- `BlackroomMarket`: `A`, `HK`, `ETF`.
- `BlackroomSource`: `manual`, `shareholder_selling`, `shareholder_reduction`.
- `DailyBarDiagnosticAdjust`: `bfq`, `qfq`, `hfq`.
- `DailyBarDiagnosticClassification`: `missing_market_data`,
  `missing_exact_date`, `downloaded`, `resolved`.
- `ProviderOutcomeStatus`: `downloaded`, `empty`, `error`.
- `SSFChangeSignalStatus`: `signal`, `no_signal`.
- `SSFEventType`: `increase`, `decrease`, `new_entry`, `exit`.

All definitions use `StrEnum`. SQLAlchemy maps the five scalar table columns
to named native PostgreSQL enums and persists member `.value` labels:

- `blackroom_records.market` uses `blackroom_market`.
- `blackroom_records.source` uses `blackroom_source`.
- `daily_bar_diagnostics.adjust` uses `daily_bar_diagnostic_adjust`.
- `daily_bar_diagnostics.classification` uses
  `daily_bar_diagnostic_classification`.
- `ssf_change_signals.status` uses `ssf_change_signal_status`.

The current Blackroom defaults remain `A` and `manual`; SSF status remains
`signal`. Existing APIs, CLIs, services, DAGs, and queries continue receiving
and exposing the same strings.

## JSON Contracts

`provider_outcomes` remains a JSON array of provider evidence objects. At the
daily-diagnostic repository write boundary, input must be a list whose entries
are objects with a `status` from `ProviderOutcomeStatus`. The provider name and
detail remain unbounded provider evidence.

`event_types` remains a JSON array. At the SSF storage write boundary, input
must be a list whose entries are strings from `SSFEventType`. An empty array
for `no_signal` remains valid.

PostgreSQL adds two stable checks for direct-SQL protection:

- `ck_daily_bar_diagnostics_provider_outcome_status` requires
  `provider_outcomes` to be an array and rejects any element that is not an
  object with a valid status.
- `ck_ssf_change_signals_event_types` requires `event_types` to be an array
  and rejects every unrecognized entry.

Application validation remains the portable authority for these structures;
the checks provide PostgreSQL defense in depth. Invalid values fail before a
SQLite or PostgreSQL write is issued through supported application paths.

## Adapter and Migration

Add a dedicated Storage enum-governance adapter, registered after the existing
Paper Trading and Monitor adapters. It owns exactly `blackroom_records`,
`daily_bar_diagnostics`, and `ssf_change_signals`; daily diagnostics are not
folded into the Paper Trading adapter merely because that ORM model is located
there.

The unified command preflights every adapter before any DDL. The Storage
adapter preflight rejects partially present governed tables, incompatible
column facts, unexpected pre-existing enum labels, invalid legacy scalar
values, invalid legacy JSON documents, and conflicting JSON-check definitions.
It verifies expected defaults for Blackroom market and source.

Normal PostgreSQL migration creates or verifies the five named scalar types,
explicitly casts legacy strings through text to enum columns, restores defaults, installs
the two checks, and verifies types, labels, defaults, and checks. A successful
rerun is idempotent. SQLite remains a no-DDL path; it uses the same
application-level validation.

Rollback converts the five enum columns to their documented `VARCHAR` forms,
drops both JSON checks, verifies no unmanaged dependencies remain, and only
then drops the named enum types. Adapter errors propagate through the existing
unified transaction so preflight or verification failures leave every governed
domain unchanged.

## Verification

SQLite coverage proves supported application paths reject invalid Blackroom
market/source, diagnostic adjustment/classification/provider-outcome status,
and SSF status/event type before persistence. It also proves valid existing
Blackroom CRUD, daily diagnostic upserts, and SSF signal/no-signal flows
preserve their observable output.

PostgreSQL integration coverage uses an isolated schema to prove legacy
conversion, complete enum labels, defaults, JSON-check creation, idempotent
reruns, and rollback. Direct SQL attempts with invalid scalar enum values,
provider-outcome statuses, and SSF event types must fail. Invalid existing
JSON blocks migration during preflight before any adapter performs DDL.

Unified-command tests extend the shared fixture with the three governed
tables, assert the `storage` adapter follows Paper Trading and Monitor, and
prove an invalid storage-domain preflight preserves the converted state of
neither preceding adapter.

## Out of Scope

- Constraining provider names, diagnostic evidence details, or `detail_json`.
- Changing Blackroom, daily-history, or SSF business behavior and outputs.
- Creating an independent production migration command.
- Adding labels at application startup or silently coercing legacy values.
- Changing DAG schedules, dependencies, retries, task boundaries, or SLAs.
