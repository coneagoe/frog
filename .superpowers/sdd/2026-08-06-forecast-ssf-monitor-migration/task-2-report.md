# Task 2 Report: Retire Targets Outside Qualified Universe

## Scope

Implemented post-processing in `ForecastSSFMonitorSyncService.sync` to retire
persisted forecast SSF candidates that are no longer present in the current
qualified forecast code set.

## Behavior Delivered

- A persisted candidate absent from the current forecast universe is persisted
  as `ineligible` with reason `forecast_no_longer_qualified`.
- Existing evidence is preserved and extended with lifecycle evidence:
  `{"as_of_date": "YYYY-MM-DD", "reason": "forecast_no_longer_qualified"}`.
- A candidate linked to its matching daily `forecast_ssf_ma20` workflow target
  is disabled with the existing atomic candidate/target upsert API.
- `disabled` increases only when that matched workflow target was enabled.
- Candidates with no target link are retired as candidate-only records and do
  not create a workflow target.
- Manual and intraday targets are never inspected or mutated because retirement
  only accepts the matching daily workflow lookup and matching target id.
- Forecast loading occurs before candidate listing, target lookup, and every
  candidate or target write; a load failure leaves state untouched.
- An empty forecast result uses the same retirement path for all applicable
  persisted daily workflow candidates.

## Tests Added

- Absent daily workflow candidate retirement includes lifecycle evidence and
  atomically disables its target.
- Empty forecast universe retires only the matching daily workflow target,
  leaving unmatched manual/intraday ownership untouched.
- Unlinked absent candidates persist the ineligible lifecycle state without
  creating a target.
- Forecast-load failure now asserts that candidate listing, target lookup, and
  both candidate/target write paths are not invoked.

## Verification

Red test command, before implementation:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'retire or no_longer_qualified or empty_universe' -v
3 failed, 12 deselected
```

Focused retirement verification, after implementation:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'retire or no_longer_qualified or empty_universe' -v
3 passed, 12 deselected
```

Required workflow regression suite:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py -v
56 passed
```

Scoped quality checks:

```text
uv run ruff format --check monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
2 files already formatted

uv run ruff check monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
All checks passed!
```

## Documentation Review

No repository documentation required updates. The changed behavior is internal
to the existing forecast SSF synchronization lifecycle and does not alter
setup, public target-service behavior, DAG configuration, or architecture
guidance.

## Concerns

None identified within Task 2 scope. The full project test suite was not run;
the required focused workflow regression suite passed.

## Review Fix: Stale Target Links

### Defect

Retirement previously skipped an absent candidate when its non-null stored
`monitor_target_id` no longer matched the daily `forecast_ssf_ma20` workflow
lookup. This left the candidate in its prior state with a stale link.

### Correction

When the daily workflow target is absent or its id differs from the stored
candidate link, retirement now persists the candidate-only ineligible state,
adds the standard lifecycle evidence, and clears `monitor_target_id` to
`None`. It does not invoke the atomic target upsert, so a manual or intraday
target cannot be mutated. A matching already-disabled workflow target remains
disabled and does not increment the `disabled` summary count again.

### TDD Evidence

Before the correction:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'stale_target_link or repeated_retirement' -v
2 failed, 1 passed, 15 deselected
```

The failing variants covered a missing daily target and a daily target with a
different id. Both showed no candidate persistence before the fix.

After the correction:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py -k 'stale_target_link or repeated_retirement' -v
3 passed, 15 deselected
```

Focused Task 2 regression and quality checks:

```text
uv run pytest test/monitor/test_forecast_ssf_monitor_sync.py test/storage/test_forecast_ssf_candidate_storage.py test/monitor/test_monitor_target_service.py test/dags/test_monitor_stock_daily.py -v
59 passed

uv run ruff format --check monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
2 files already formatted

uv run ruff check monitor/forecast_ssf_monitor_sync.py test/monitor/test_forecast_ssf_monitor_sync.py
All checks passed!
```

No repository documentation update was needed for this internal corrective
change. The report itself was appended as required by the review round.
