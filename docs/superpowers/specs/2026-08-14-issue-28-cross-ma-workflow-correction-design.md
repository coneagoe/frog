# Issue 28 Forecast Snapshot and Close-Cross Workflow Design

## Goal

Correct the forecast and social-security-fund candidate workflow without
changing the ordinary daily stock-monitor DAG topology. A separately completed
and auditable forecast snapshot supplies candidate input. The existing
`monitor_stock_daily` process evaluates enabled targets, including workflow
targets, using a new final-close MA crossover condition.

## Workflow Boundaries

`forecast_ssf_ma20_sync` remains an independent candidate-synchronization DAG.
It has no dependency edge to `monitor_stock_daily`. It selects a completed
forecast snapshot, screens candidates, and synchronizes only daily targets
owned by `workflow: "forecast_ssf_ma20"`.

`monitor_stock_daily` remains the sole target evaluator and alert sender. Its
Airflow execution date is passed to `run_monitor(frequency="daily",
as_of_date=...)`. Existing monitor conditions, including `price_cross_ma`,
retain their current retrieval and evaluation behavior. The new condition is
used only where a final-close A-share signal is required.

## Close-Cross Condition

Add `close_cross_ma`; do not alter `price_cross_ma`. The latter is an existing
general-purpose condition using its current price-source behavior. The new
condition provides a distinct, final-bar contract:

- It is available only for A-share daily targets.
- It obtains at least 21 daily bars from storage with `AdjustType.HFQ`, bounded
  by the explicit `as_of_date`.
- The final bar date must equal `as_of_date`; otherwise evaluation is
  `INSUFFICIENT_DATA`.
- It uses a single HFQ series. The previous close is bar 20, the previous MA20
  is bars 1 through 20, the current close is bar 21, and current MA20 is bars
  2 through 21.
- An upward trigger requires `previous_close <= previous_ma20` and
  `current_close > current_ma20`. Missing values or fewer than 21 valid bars
  yield `INSUFFICIENT_DATA`.
- `INSUFFICIENT_DATA` does not change `last_state` and cannot send an alert.
- With no explicit `as_of_date`, direct `run_monitor()` callers use the current
  China-local date for this condition only.

The workflow condition is:

```json
{"type":"close_cross_ma","direction":"above","period":20,"workflow":"forecast_ssf_ma20"}
```

A new or requalified target that is already above MA20 does not receive a
catch-up alert. Targets retain `last_state` across synchronization, disable,
and re-enable transitions. The existing runner resets it only after an
evaluated `NOT_TRIGGERED` result; a later real crossover may then alert.

## Price-Versus-MA Migration

Remove `price_vs_ma` from application validation, evaluation, PostgreSQL
condition constraints, enum migration, tests, and documentation. Add
`close_cross_ma` to each supported condition contract.

Before replacing the PostgreSQL CHECK constraint, migration must rewrite every
existing `price_vs_ma` target, including manual, ETF, and HK targets:

- Preserve ID, market, frequency, workflow, note, reset mode, trigger
  timestamp, and candidate linkage.
- Replace its condition type with `close_cross_ma` while retaining direction,
  period, and any workflow marker.
- Preserve `last_state=false`; set `last_state=true` for an existing true state
  so the semantic replacement cannot immediately create a catch-up alert.
- For a non-A-share target, set `enabled=false` and log target ID and market.
  `close_cross_ma` is A-share only; users must explicitly choose another
  supported condition before re-enabling it.
- Assert no `price_vs_ma` records remain before applying the new CHECK
  constraint. The migration is safe to rerun on PostgreSQL and SQLite.

## Candidate Lifecycle

Workflow ownership remains unique on
`(stock_code, market, frequency, workflow)`. Manual and intraday targets are
never synchronized.

Conclusive negative outcomes retain the linked workflow target and candidate
link but disable the target in the same stock-level transaction:

- active blackroom
- missing SSF holder in a fresh disclosure
- omission from a successfully selected snapshot's qualified universe
- delisted or unlisted status
- reporting-period supersession

Missing, stale, or failed shareholder evidence produces `deferred` and leaves
a previously enabled target unchanged. A paused target remains disabled; sync
updates its evidence but cannot re-enable it until an operator resumes it and
a later successful screen qualifies it.

Replace deletion-oriented transition methods with one disable-oriented atomic
storage operation. It validates that the target is a daily
`forecast_ssf_ma20` target with exactly one linked candidate, then updates
candidate state, reason, and evidence, retains `monitor_target_id`, and sets
`target.enabled=false`. Invalid ownership or linkage returns false without
mutation. Candidate synchronization and alert-time blackroom protection both
use this operation; alert-time bans suppress email without deleting the target.

Each stock transition is atomic. A database error rolls back that stock's
candidate and target mutation only. Earlier stock transitions remain committed;
the run records the failed stock and error detail, continues other stocks where
possible, then fails the DAG summary.

## Immutable Forecast Snapshots

Candidate synchronization never treats the mutable `forecasts` table or a
single daily incremental download as evidence that a reporting period is
complete. Add persistent snapshot models:

`forecast_snapshot_runs` stores `id`, `report_end_date`,
`announcement_start_date`, `announcement_end_date`, `attempt`, status
(`running`, `completed`, `failed`), source and normalized row counts, qualified
row count, duplicate conflict counts, timestamps, and error detail.

`forecast_snapshot_records` stores each normalized provider row associated with
its snapshot, including `stock_code`, `end_date`, `ann_date`, forecast fields,
and the provider response's zero-based `source_order`. Snapshot records are
immutable after creation.

A full snapshot is started only through explicit inputs:

- `tools/backfill_forecast.py snapshot --report-end-date YYYYMMDD
  --announcement-start-date YYYYMMDD --announcement-end-date YYYYMMDD`
- `forecast_snapshot` Airflow DAG, which requires the same three values in
  `dag_run.conf` and fails when any is absent.

The existing rolling 30-day `download_forecast_daily` DAG remains an incremental
refresh; it cannot mark a snapshot complete. A completed snapshot becomes
eligible only on a later synchronization window. The first candidate sync
requires at least one completed snapshot.

For each date in the explicit announcement range, snapshot ingestion calls the
existing forecast provider. An empty result is a successful covered date. Every
returned row must contain required schema fields and normalize its `ann_date`
to exactly the requested date. Schema errors, date mismatches, invalid required
dates/numbers, provider failures, and persistence errors fail the snapshot.
Non-A-share rows, ST rows, and other strategy-universe exclusions remain
auditable counts rather than snapshot failures.

Failed runs retain diagnostic snapshot records but are never selectable. A
completed run commits its final validation and summary atomically. It may still
write ordinary mutable `forecasts` data during ingestion; candidate sync reads
only immutable records from completed snapshots.

Run identity is `(report_end_date, announcement_start_date,
announcement_end_date, attempt)`. Only one `running` run may exist for a given
report-period/range. A completed matching range returns its stored result;
failed ranges may start the next attempt. Snapshot selection is deterministic:
among `completed` runs with `announcement_end_date <= as_of_date`, choose the
greatest `announcement_end_date`, then the latest completion timestamp and run
ID. Store the chosen snapshot ID, range, completion time, selected forecast
announcement date, and source order in current candidate evidence.

The snapshot's announcement range is a verified input range, not a claim that
all possible announcements for a report period have been captured. Operators
must build later snapshots to include later forecast revisions.

## Forecast Candidate Selection

The selected snapshot's `report_end_date` is the only report period screened.
Other report periods can remain in immutable records for audit but cannot enter
that run's candidate universe.

For each stock, select the latest row with `ann_date <= as_of_date`; on same-day
duplicates select the greatest `source_order`. Record conflict counts and the
selected order in evidence. Only after this selection apply supported A-share
universe, current listing/ST, `type == "预增"`, and numeric
`p_change_min >= 50` criteria. A later revision that no longer qualifies
therefore disables a previously eligible target rather than allowing an older
forecast to survive.

Snapshot selection prevents forecast look-ahead. Shareholder lookup must also
accept `as_of_date` and return only the latest top-10 floating-holder disclosure
with `ann_date <= as_of_date`; the existing two-month freshness rule then uses
that disclosure. Listing and ST status remain current-table checks in this
iteration; historical listing status for backtests is explicitly out of scope.

## Verification

Coverage establishes the following contracts with mocked external providers:

- `close_cross_ma` detects only the defined two-day MA crossover from a single
  HFQ series, rejects non-A targets, and preserves state on missing or
  date-mismatched bars.
- Existing `price_cross_ma` behavior remains unchanged.
- Migration converts every `price_vs_ma` record before constraint tightening;
  it preserves target metadata and disables non-A targets.
- Candidate transitions disable and retain the same workflow target and
  `monitor_target_id`; recovery re-enables that same ID; blackroom alert guards
  suppress email without deletion.
- A disabled/re-enabled target already above MA20 does not alert; a later
  down-and-up crossover alerts once.
- Snapshot ingestion verifies each requested date, persists source order,
  records failures, handles retry/concurrency identity, and makes only completed
  runs selectable.
- Snapshot selection blocks future snapshots, uses deterministic ties, and
  screens the latest forecast revision before qualification.
- Shareholder lookup ignores future disclosure records.
- `monitor_stock_daily` remains independent of candidate synchronization while
  forwarding its Airflow evaluation date to `run_monitor`.
- Focused unit tests, PostgreSQL storage-contract tests through
  `tools/run_tests.sh`, Ruff, and relevant mypy checks provide the execution
evidence.

## Non-Goals

- Do not change the ordinary `monitor_stock_daily` schedule, dependencies,
  retries, task boundaries, or SLA.
- Do not change existing `price_cross_ma` behavior.
- Do not retain `price_vs_ma` compatibility.
- Do not add automated orders, position sizing, or trading execution.
- Do not build historical listing/ST effective-date snapshots in this change.
- Do not make the complete snapshot claim coverage beyond its explicit
  announcement-date range.
