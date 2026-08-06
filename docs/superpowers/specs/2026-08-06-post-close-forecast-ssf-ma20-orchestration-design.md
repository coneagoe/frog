# Post-Close Forecast SSF MA20 Orchestration Design

## Goal

Run the forecast, social-security-holder, blackroom, and MA20 monitoring workflow at 20:00 on every calendar day, but evaluate only A-share trading days. The workflow must verify final daily-bar availability before mutating candidates or targets, make its outcome operationally visible, and prevent a workflow security added to the blackroom after synchronization from sending a technical alert.

## Scope

- Add a separate additive Airflow DAG named `forecast_ssf_ma20_post_close` scheduled at `0 20 * * *` with `max_active_runs=1`.
- Preserve `monitor_stock_daily` without changing its schedule, dependencies, retries, task boundaries, or SLA.
- Verify A-share daily-bar completeness for the logical trading date before candidate synchronization.
- Synchronize `forecast_ssf_ma20` candidates and then evaluate only that workflow's daily monitor targets.
- Emit a structured operational summary that separates a valid empty result from a failed run.
- Recheck blackroom status immediately before a workflow alert email is sent, disable a newly banned target, and suppress its email.
- Include forecast and social-security-holder evidence in workflow alert emails.

## DAG Design

The DAG runs at 20:00 (`0 20 * * *`) with a single active run. On non-trading days, the daily-bar verification task skips the run before any synchronization or monitoring action.

On a trading day, the DAG uses three ordered Python tasks:

1. `verify_daily_bar_completeness` verifies that the finalized front-adjusted A-share daily bars required by the daily monitor are available for the logical trading date. A missing, stale, or failed verification raises an error and blocks all later tasks.
2. `sync_forecast_ssf_targets` invokes `ForecastSSFMonitorSyncService.sync(as_of_date)`. Its existing systemic validation and source failures raise before candidate or workflow-target mutation. A successful empty forecast universe remains a successful synchronization and is returned as a zero-count summary.
3. `run_forecast_ssf_daily_monitor` invokes the monitor runner with `frequency="daily"` and workflow `forecast_ssf_ma20`. It combines its trigger, skip, and error counts with the synchronization summary for a structured operational result in task logs and the return value.

The DAG sequence is strictly completeness verification, synchronization, then monitor evaluation. Existing monitor targets without the workflow owner are excluded from the final task.

## Runner Integration

`run_monitor` gains an optional workflow filter. With no filter, it keeps current behavior for all existing callers. With `forecast_ssf_ma20`, it evaluates only daily targets whose durable workflow owner matches that value.

Before sending an edge-trigger email for a workflow-owned target, the runner asks `BlackroomService` for its current A-share status:

- A successful banned result disables the workflow target and records candidate lifecycle state `blackroom` with reason `active_blackroom`; no email is sent and the target is not marked triggered.
- A failed blackroom lookup is a monitor error; no email is sent and the target is not marked triggered.
- A non-banned result permits the normal email path.

Workflow alert bodies augment the existing technical-condition information with evidence retained by the candidate state: forecast reporting period, forecast lower growth bound, forecast announcement date, matching social-security/retirement-fund holder, and shareholder announcement date. Missing evidence fields are omitted without failing otherwise valid alert delivery.

The runner writes a triggered state only after `send_email` succeeds. An email exception contributes to the run error summary and leaves the previous edge-trigger state intact.

## Operational Summary And Errors

The final task returns a JSON-serializable summary with these sections:

- `daily_bar`: logical date and completeness result.
- `synchronization`: the existing source, screening, blackroom, SSF-match, deferred, creation/update/disable/no-op, and error counts.
- `monitor`: evaluated-target, triggered, skipped, and error counts with representative error details.

The DAG fails for daily-bar verification failures, synchronization failures, or monitor errors. It succeeds for a complete daily bar and a valid empty candidate result, clearly reporting zero synchronization and monitor counts. Per-stock shareholder deferrals remain successful synchronization outcomes and are visible in the synchronization section.

## Testing

- DAG tests mock Airflow, daily-bar verification, synchronization, and monitor execution. They verify the `0 20 * * *` schedule, task order, trading-day skip, completeness failure short-circuiting, synchronization failure short-circuiting, and structured valid-empty summary.
- Runner tests mock storage, price data, blackroom lookup, and email delivery. They verify workflow filtering, blackroom suppression and disablement, blackroom lookup failures, email evidence enrichment, and no state update after email failure.
- Existing unfiltered monitor-runner behavior remains regression-covered.
- All provider, database, Airflow, and email integrations are mocked in unit and DAG tests; no live external calls are made.

## Out Of Scope

- Any change to the existing `monitor_stock_daily` DAG's schedule, dependencies, retries, task boundaries, or SLA.
- Changes to the forecast-SSF candidate eligibility, lifecycle, pause/resume, or monitor-target ownership rules implemented by prior issues.
- Automatic trading, portfolio actions, or paper-trading integration.
- Alerts for manually owned monitor targets beyond their existing behavior.
