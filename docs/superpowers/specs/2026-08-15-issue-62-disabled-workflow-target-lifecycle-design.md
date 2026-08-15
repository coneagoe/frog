# Issue 62 Disabled Workflow Target Lifecycle Design

## Goal

Retain the identity and candidate link of every workflow-owned daily
`forecast_ssf_ma20` target through conclusive negative lifecycle outcomes.
Synchronization and alert-time blackroom protection must disable the retained
target atomically instead of deleting it or replacing its candidate link.
Subsequent qualification must reuse that target unless it remains manually
paused.

## Boundaries

This work completes the lifecycle behavior established by forecast snapshot
ingestion and candidate synchronization. It does not change immutable snapshot
selection, forecast qualification, shareholder matching, the daily monitor DAG
schedule, or close-crossover evaluation semantics.

The storage boundary is authoritative for workflow target ownership, candidate
linkage, candidate evidence, target enabled state, and transaction atomicity.
The synchronization service determines business outcomes and evidence. The
monitor runner uses the same storage transition for its alert-time blackroom
guard.

## Atomic Lifecycle Transition

Storage will expose one stock-level workflow lifecycle transition for candidate
state, reason, evidence, and requested target enablement. In one transaction,
it will:

1. Locate the A-share candidate for the stock.
2. Preserve its existing `monitor_target_id`.
3. When a target is linked, require exactly one target with that ID, workflow
   `forecast_ssf_ma20`, and daily frequency.
4. Update candidate state, reason, and evidence, then enable or disable that
   retained target as requested.
5. Keep a paused target disabled regardless of requested enablement, and
   preserve the evaluated automatic outcome in evidence.

An absent candidate, absent or mismatched linked target, wrong ownership,
wrong frequency, or duplicate candidate linkage fails the transition with no
candidate or target mutation. Target lifecycle transitions never reset
`last_state`; only monitor evaluation may reset edge state after a valid
not-triggered condition. A newly created workflow target retains its normal
initial `last_state` value of `False`.

The target-ID alert-time blackroom adapter delegates to this same transition.
It derives the blackroom lifecycle evidence from the transaction-local
candidate rather than a detached pre-read.

## Synchronization Behavior

The synchronization service continues to pre-load immutable snapshot input,
listing data, and blackroom status before any candidate mutation. Failures in
that shared input remain fail-fast and leave all candidates and targets
unchanged.

After successful preflight, each stock is processed independently. The service
builds snapshot, forecast, shareholder, blackroom, and lifecycle evidence and
performs one storage-owned transition per stock:

- Active blackroom, non-SSF evidence, snapshot omission or non-qualification,
  delisted/unlisted classification, and reporting-period supersession set the
  applicable conclusive state and disable the linked target without deleting
  it.
- Missing, stale, or failed shareholder evidence records `deferred`. It leaves
  an enabled target enabled; a paused target remains disabled while evidence is
  refreshed.
- A qualified stock re-enables its retained target and updates the candidate to
  `eligible`, except that a paused target remains disabled and candidate state
  `paused` records the automatic eligible outcome in evidence.
- Workflow target creation occurs only for a qualifying stock with no existing
  candidate or target-link integrity failure. Recovery reuses the previously
  retained target identity.

The service must not fall back to an unlinked candidate upsert after a failed
or invalid linked transition. Linkage or ownership failure is itself a
stock-level persistence failure and leaves the affected records unchanged.

## Partial Failures

Each persistence exception rolls back only the affected stock transaction. The
service records a structured error item with stock code, attempted lifecycle
state, reason, exception type, and exception message, then continues with
independent stocks.

Once all stock transitions have been attempted, the service raises
`ForecastSSFMonitorSyncPartialFailure` when one or more stock transitions
failed. The exception carries the completed summary, including the structured
errors, so the caller can retain operational detail while the Airflow task
fails visibly. A fully successful run keeps the existing successful result
shape.

## Alert-Time Blackroom Guard

Before sending an edge-triggered email for a `forecast_ssf_ma20` target, the
monitor runner checks current blackroom status. An active ban calls the shared
retaining-disable transition, suppresses email, and counts the target as
skipped. If the transition cannot validate or persist the linked target, the
runner records an error and does not send an email.

The runner reads candidate evidence only after the initial blackroom guard has
passed. It performs no duplicate blackroom lookup before sending the email.
Manual and unrelated workflow targets retain their existing alert behavior.

## Verification

Focused tests will prove:

- disable transitions retain target identity, candidate linkage, evidence, and
  `last_state`;
- invalid ownership, frequency, missing linkage, and duplicate linkage roll
  back without mutating either record;
- every conclusive synchronization outcome disables the retained target;
- deferred evidence leaves active targets enabled and paused targets disabled;
- requalification re-enables the same retained target unless paused;
- snapshot, lifecycle, and automatic paused-outcome evidence is preserved;
- a failed stock transition is recorded structurally, other stocks complete,
  and the synchronization call raises the partial-failure exception;
- alert-time blackroom protection disables through the shared transition,
  suppresses email, and performs one blackroom lookup; and
- manual, non-daily, and unrelated workflow targets remain unmodified.

Run focused monitor and storage tests with `uv run pytest`, PostgreSQL storage
contract coverage through `tools/run_tests.sh`, then Ruff formatting/checking
and the relevant mypy scope.

## Non-Goals

- Change the `monitor_stock_daily` DAG schedule, dependencies, retries, task
  boundary, or SLA.
- Change `close_cross_ma` technical evaluation or existing `price_cross_ma`
  behavior.
- Add candidate transition history beyond the current evidence payload.
- Repair invalid historical candidate-to-target links automatically.
- Add automated trading, order placement, or portfolio actions.
