# Monitor and Forecast SSF Enum Governance Design

## Goal

Make Monitor and Forecast SSF finite business values durable database
contracts without changing monitor behavior or Forecast SSF candidate lifecycle
semantics. The implementation is a domain adapter within the unified enum
governance command defined by issue #34; it is not a second production
operator command.

## Domain Contracts

`monitor/domain_enums.py` is the canonical application definition for these
readable persisted labels:

- `MonitorMarket`: `A`, `HK`, `ETF`.
- `MonitorFrequency`: `daily`, `intraday`.
- `MonitorResetMode`: `auto`, `manual`.
- `ForecastSSFCandidateState`: `eligible`, `ineligible`, `deferred`, `paused`,
  `blackroom`, `delisted_or_unlisted`.

`StockMonitorTarget.market`, `StockMonitorTarget.frequency`, and
`StockMonitorTarget.reset_mode` map to named native PostgreSQL enums.
`ForecastSSFCandidate.market` reuses the `monitor_market` type, and its
`state` uses `forecast_ssf_candidate_state`. SQLAlchemy persists enum member
values, so API and CLI contracts continue exposing the existing readable
strings.

Storage write boundaries validate each enum value before opening a transaction:
monitor create and update paths validate market, frequency, and reset mode;
Forecast SSF candidate upsert and lifecycle-transition paths validate market
and state. Valid lifecycle transitions retain their existing behavior.

## Condition JSON Contract

`monitor/condition_validation.py` centrally owns the portable discriminated
condition schema. It accepts only `price_threshold`, `price_cross_ma`,
`price_vs_ma`, `ma_cross`, `change_pct`, and `rsi`.

Threshold and comparison conditions require `above` or `below`; moving-average
cross requires `golden` or `death`. Each condition type requires its applicable
numeric fields. Moving-average periods are positive integers, `ma_cross`
requires `fast < slow`, and RSI defaults its period to 14 and requires a value
between 0 and 100. Invalid condition types, directions, and required fields
fail before persistence through API, CLI, service, or storage paths.

PostgreSQL adds only a stable minimal check named
`ck_stock_monitor_targets_condition_type`: `condition` must be a JSON object
with one of the supported `type` values. Application validation remains the
authority for conditional direction and field rules, which are not represented
in a complex database constraint.

## Unified Migration Adapter

`monitor/storage/enum_migration.py` remains a Monitor and Forecast SSF domain
adapter. It supplies the four enum groups, governed table facts, preflight,
conversion, verification, rollback, and condition-check management to the
unified issue #34 enum-governance command.

The unified command is the only supported production operator interface. It
opens one PostgreSQL transaction, runs every domain preflight before DDL, then
coordinates conversion, verification, rollback, output, and maintenance-window
guidance. The former dedicated `tools/migrate_monitor_enums.py` command is
removed or replaced as part of the unified-command work; it must not remain an
independent operational path.

Normal migration creates or verifies the named types, rejects unexpected enum
labels and unknown legacy values, drops and restores affected defaults and
indexes as needed, casts legacy strings through text to enum values, adds the
condition check, and verifies all resulting facts. Dry runs run the same
preflight without DDL.

Rollback verifies that no unmanaged dependency remains on any managed enum,
converts managed columns back to their documented `VARCHAR` types, restores
legacy defaults and indexes, removes the condition check, and drops types only
after dependencies are gone. Any preflight or verification failure aborts the
shared transaction and leaves every governed domain unchanged.

## Verification

SQLite tests cover the portable write contracts: valid monitor targets and
Forecast SSF candidate lifecycle workflows persist unchanged, while invalid
market, frequency, reset mode, candidate state, condition type, direction, and
required fields fail before commit.

PostgreSQL integration tests cover creation and reuse of the shared market
type, conversion, idempotent rerun, legacy-value rejection, complete labels,
defaults, indexes, the condition check, verification, and rollback. Tests also
prove invalid existing condition documents block migration before DDL.

Unified-command tests cover domain adapter ordering, stable aggregated output
for dry-run, normal, and rollback modes, and atomic failure behavior. Dedicated
monitor CLI tests are removed or converted to unified-command tests when that
command becomes the public migration interface.
