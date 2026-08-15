# Issue 61 Snapshot Candidate Synchronization Design

## Goal

Synchronize qualified A-share forecast candidates from one deterministically
selected, completed immutable forecast snapshot into daily workflow-owned
`close_cross_ma` monitor targets. The independent synchronization workflow
must never provide input to, or become an upstream dependency of,
`monitor_stock_daily`.

## Boundaries

`forecast_ssf_ma20_sync` remains a single scheduled synchronization task. Its
business date is the existing China-local Airflow interval-end date. It selects
only snapshot data and performs candidate lifecycle transitions; the ordinary
daily monitor evaluates enabled targets and sends alerts independently.

The synchronization service no longer reads mutable `forecasts` data. It uses
only `ForecastSnapshotRun` and `ForecastSnapshotRecord` data selected at the
storage boundary. Existing candidate state, blackroom handling, current
listing/ST screening, SSF matching, freshness handling, pause semantics, and
workflow target ownership remain in the synchronizer.

## Snapshot Selection

Storage exposes a completed-snapshot selection method accepting `as_of_date`.
It considers only completed runs with `announcement_end_date <= as_of_date`.
The selected run is ordered by:

1. greatest `announcement_end_date`;
2. latest `completed_at`;
3. greatest run ID.

The run's `report_end_date` defines the only reporting period considered for
that synchronization run. Failed and running snapshot attempts are never
selectable. A completed run with an announcement range ending after the
business date is never selectable.

When no eligible run exists, the service raises
`NoEligibleForecastSnapshotError` before listing, blackroom, shareholder,
candidate, or monitor-target work. The DAG therefore fails visibly with no
candidate or target mutation.

## Immutable Candidate Input

Storage exposes records for the selected run and its reporting period only. It
excludes records whose `announcement_date` is after the business date. For each
stock, it selects the latest remaining announcement date and, for duplicate
records on that date, the greatest provider `source_order`. Qualification is
applied only after this latest-revision selection.

A selected revision is eligible only when all of these conditions hold:

- its code is a supported A-share code and belongs to the existing A-share
  strategy universe;
- current listing data marks it listed and not ST;
- `forecast_type` is exactly `预增`; and
- `growth_min` is numeric and at least `50`.

An older qualifying revision cannot remain active when a later selected
revision does not qualify. Stocks omitted from the selected snapshot's
qualified universe take the existing ineligible lifecycle path.

## Shareholder Evidence

The top-10 floating-holder storage lookup receives `as_of_date` and returns
only the latest disclosure whose announcement date is on or before that date.
The existing SSF holder-name matching and two-calendar-month freshness rule
operate on that disclosure. Missing, stale, or query-failed shareholder
evidence remains deferred and does not alter a previously enabled target.

## Target Lifecycle And Evidence

Qualified stocks create or update exactly one daily A-share target owned by
`workflow: "forecast_ssf_ma20"`. Its condition is:

```json
{"type":"close_cross_ma","direction":"above","period":20,"workflow":"forecast_ssf_ma20"}
```

The existing atomic workflow-candidate transition methods retain linked targets
and disable them for conclusive negative outcomes such as a blackroom ban,
non-SSF holder, delisting, reporting-period supersession, or snapshot
omission. Manual, non-workflow, and non-daily targets are not synchronized.

Every candidate evidence payload records immutable forecast provenance:

- selected snapshot ID;
- selected snapshot reporting period and announcement-date range;
- selected snapshot completion time;
- selected forecast announcement date; and
- selected provider source order.

It continues to retain forecast values, shareholder evidence, blackroom state,
and lifecycle information. Existing pause behavior remains: synchronization
updates evidence but cannot re-enable a paused target.

## Errors And Atomicity

Snapshot selection and immutable-record retrieval fail before all mutations.
After input is successfully loaded, existing per-stock transition atomicity
applies: a storage failure rolls back only that stock's candidate/target update,
other stocks may continue, and the task reports failure after recording the
error. A shareholder lookup failure is deferred under the existing policy.

## Verification

Focused service, storage, and DAG-callable tests establish:

- completed snapshot selection excludes running, failed, and future-ending
  ranges, with range-end, completion-time, and ID tie breaking;
- no eligible snapshot raises the distinct exception and makes no candidate or
  target mutation;
- candidate records use one selected run/reporting period, reject future
  announcements, replace older revisions, and resolve same-day duplicates by
  final source order;
- qualification requires supported/listed/non-ST A-share status, exact `预增`,
  and numeric lower growth of at least `50`;
- as-of shareholder lookup excludes future disclosures while preserving SSF
  matching and freshness behavior;
- created or updated targets are daily workflow-owned `close_cross_ma` targets;
- candidate evidence includes snapshot and selected-record provenance;
- manual and unrelated targets remain unmodified; and
- `monitor_stock_daily` retains no synchronization dependency.

Run focused storage, monitor synchronization, and DAG tests with `uv run
pytest`; run PostgreSQL storage contract coverage through `tools/run_tests.sh`;
then run Ruff formatting/checking and relevant mypy checks.

## Non-Goals

- Change the `monitor_stock_daily` DAG schedule, dependencies, retries, task
  boundary, or SLA.
- Change final-close crossover evaluation or alert semantics.
- Use mutable forecast records as candidate evidence.
- Add historical listing or ST-status snapshots.
- Add automated trading, order placement, or position management.
