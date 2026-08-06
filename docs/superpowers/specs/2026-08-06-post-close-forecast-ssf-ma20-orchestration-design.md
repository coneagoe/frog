# Forecast SSF MA20 Candidate Synchronization Design

## Goal

Synchronize forecast, social-security-holder, and blackroom-qualified A-share candidates into the existing stock monitor before its daily scan. The synchronizer runs at 15:05, while the existing 15:30 stock monitor remains the sole MA20 evaluator and alert sender.

## Scope

- Add a separate Airflow DAG named `forecast_ssf_ma20_sync` scheduled at `5 15 * * *` with `max_active_runs=1`.
- The new DAG only synchronizes candidates; it does not validate daily-bar completeness, calculate MA20, evaluate monitor targets, or send email.
- Preserve the existing `monitor_stock_daily` 15:30 schedule and daily technical-condition scan. Remove only its forecast SSF synchronization task, so this workflow has one target-mutation path.
- Emit a structured synchronization summary that separates a valid empty result from a failed run.
- Recheck blackroom status immediately before a workflow alert email is sent, delete a newly banned target, and suppress its email.
- Include forecast and social-security-holder evidence in workflow alert emails.

## Candidate Synchronization

The DAG runs at 15:05 (`5 15 * * *`) with a single active run. On non-trading days it skips before candidate mutation.

On a trading day, its single `sync_forecast_ssf_targets` task invokes `ForecastSSFMonitorSyncService.sync(as_of_date)`. Systemic source and validation failures raise before candidate or target mutation. A successful empty forecast universe is a successful zero-count result.

Candidates that qualify create or update one owned daily monitor target with `workflow="forecast_ssf_ma20"`. A candidate that becomes ineligible, blackroom-blocked, delisted, superseded, or leaves the qualified universe has its owned daily monitor target physically deleted. Its `forecast_ssf_candidate` record remains, with its state, reason, and evidence updated for audit. Deferred shareholder evidence still preserves any existing target, because it does not safely establish ineligibility.

## Runner Integration

The existing `monitor_stock_daily` DAG runs at 15:30 after the 15:05 synchronization. It remains the only daily MA20 evaluator and alert sender for both manual and workflow-owned targets. `run_monitor(frequency="daily")` retains the existing all-enabled-target behavior.

Before sending an edge-trigger email for every target whose durable owner is `forecast_ssf_ma20`, including an ordinary unfiltered daily-monitor run, the runner asks `BlackroomService` for its current A-share status:

- A successful banned result deletes the workflow target and records candidate lifecycle state `blackroom` with reason `active_blackroom`; no email is sent and the target is not marked triggered.
- A failed blackroom lookup is a monitor error; no email is sent and the target is not marked triggered.
- A non-banned result permits the normal email path.

Workflow alert bodies augment the existing technical-condition information with evidence retained by the candidate state: forecast reporting period, forecast lower growth bound, forecast announcement date, matching social-security/retirement-fund holder, and shareholder announcement date. Missing evidence fields are omitted without failing otherwise valid alert delivery.

The runner writes a triggered state only after `send_email` succeeds. An email exception contributes to the run error summary and leaves the previous edge-trigger state intact.

## Operational Summary And Errors

The synchronization task returns a JSON-serializable source, screening, blackroom, SSF-match, deferred, target creation/update/deletion/no-op, and error summary. A successful empty result and per-stock shareholder deferrals remain successful outcomes. Systemic source or validation failures fail the DAG before candidate or target mutation.

## Testing

- DAG tests mock Airflow and synchronization. They verify the `5 15 * * *` schedule, trading-day skip, synchronization failure, and valid-empty summary.
- Runner tests mock storage, price data, blackroom lookup, and email delivery. They verify workflow filtering, blackroom suppression and target deletion, blackroom lookup failures, email evidence enrichment, and no state update after email failure.
- Runner tests verify that workflow-owned targets receive the blackroom recheck and evidence enrichment in an ordinary unfiltered `run_monitor(frequency="daily")` call, while manual targets retain existing behavior.
- All provider, database, Airflow, and email integrations are mocked in unit and DAG tests; no live external calls are made.

## Out Of Scope

- Changing the existing `monitor_stock_daily` schedule, retries, SLA, or its monitoring and countdown paths.
- Changes to the forecast-SSF candidate eligibility, lifecycle, pause/resume, or monitor-target ownership rules implemented by prior issues.
- Automatic trading, portfolio actions, or paper-trading integration.
- Physical deletion of `forecast_ssf_candidate` audit records.
