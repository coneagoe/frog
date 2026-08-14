# Issue 59 Final-Close MA Crossover Design

## Goal

Add an A-share-only `close_cross_ma` monitor condition that detects a confirmed
upward MA20 crossover from final HFQ daily bars. The ordinary daily monitor
uses an explicit China-local business date for this condition without changing
its DAG topology. Existing `price_cross_ma` and `price_vs_ma` behavior remains
unchanged.

## Boundaries

`close_cross_ma` is an additive condition type. It is valid only for daily
A-share targets and supports the existing MA condition fields:

```json
{"type":"close_cross_ma","direction":"above","period":20}
```

This issue does not migrate, remove, or alter `price_vs_ma`. It does not alter
the data-source contract, evaluation semantics, alerts, or state handling of
`price_cross_ma`.

The existing `monitor_stock_daily` DAG retains its schedule, dependencies,
retries, task boundaries, and SLA. Its callable resolves the Airflow run's
China-local business date and passes it to `run_monitor(frequency="daily",
as_of_date=...)`. Direct callers that omit `as_of_date` use the current
China-local date only when evaluating `close_cross_ma`.

## Evaluation Flow

For each enabled `close_cross_ma` target, the monitor runner:

1. Rejects targets whose frequency is not daily or whose market is not the
   supported A-share market.
2. Loads at least 21 daily bars from storage using `AdjustType.HFQ`, bounded
   through the resolved evaluation date.
3. Does not call a realtime price provider for the target.
4. Requires the newest returned bar date to equal the evaluation date.
5. Requires 21 valid close values from one HFQ series.
6. Computes the previous MA20 from bars 1 through 20 and the current MA20 from
   bars 2 through 21. It triggers only when
   `previous_close <= previous_ma20` and `current_close > current_ma20`.

The current close from the final HFQ bar is used for alert display. A sustained
above-MA state is not a crossover and does not trigger this condition.

## Insufficient Data And State

Non-A-share targets, missing values, fewer than 21 valid bars, and a newest-bar
date different from the evaluation date produce `INSUFFICIENT_DATA`. The
runner increments the skipped count, sends no email, and does not update
`last_state` or `triggered_at` for that target.

For a conclusive non-trigger, the existing reset-mode behavior remains in
effect. A true upward crossover alerts only on the existing false-to-true
state transition.

## Implementation Shape

Keep storage/date and market validation in the monitor-runner retrieval path;
keep numerical crossover calculation in the condition evaluator. This retains
the evaluator's data-only boundary and isolates the new final-close contract
from the legacy realtime and historical retrieval paths.

The storage retrieval helper accepts the date bound and HFQ adjustment needed
by the new condition. Existing callers retain their current default behavior.
The daily DAG callable passes an explicit date through the runner rather than
introducing a dependency on forecast synchronization or any other DAG.

## Verification

Focused tests use mocked storage and providers and establish:

- a true upward crossover triggers exactly once;
- prior-close equality with prior MA20 is eligible, while current-close equality
  with current MA20 is not;
- missing closes, fewer than 21 bars, non-A targets, and stale final bars are
  insufficient data;
- insufficient data sends no email and preserves `last_state`;
- the new condition reads HFQ storage bars and never calls realtime pricing;
- the daily DAG forwards its China-local evaluation date without changing its
  dependency graph;
- current `price_cross_ma` retrieval, fallback, evaluation, and alert behavior
  remain unchanged.

Run focused monitor condition, monitor runner, price-fetcher, and relevant DAG
tests. Run Ruff formatting/checks and relevant mypy checks after the change.

## Non-Goals

- Migrate or remove `price_vs_ma`.
- Change `price_cross_ma` semantics or sources.
- Support `close_cross_ma` for HK, ETF, or other non-A-share targets.
- Use realtime prices for final-close crossover evaluation.
- Change ordinary daily monitor DAG scheduling or dependency topology.
