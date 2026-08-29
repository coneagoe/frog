# Task 1 Report: Freeze Replay and Baseline Contract

## Modified files

- `paper_trading/domain/enums.py`
  - Added `NavReplayEventType` with the fixed replay event precedence categories.
  - Added `NavBaselineEligibility`.
- `paper_trading/domain/nav_replay.py`
  - Added immutable `ReplayEvent`, `NavPoint`, and `ReplayResult` interfaces.
  - Added `NavSeriesReplay.replay(events, initial_state)`.
  - Normalizes event timestamps to UTC and sorts by UTC `event_at`, fixed precedence, and source ID.
  - Applies cash-flow pricing at the previous valid NAV, falling back to `1`, without creating investment return.
  - Rejects `None`, non-finite, zero, and negative NAV values as invalid.
- `paper_trading/services/nav_series.py`
  - Added `NavSeriesBuilder.build(account_id, start_date=None, end_date=None)`.
  - Added baseline eligibility checks requiring a provable creation, ledger, or history source.
  - Does not derive a legacy baseline from current `account.share_count`.
  - Filters replayed points by the requested trade-date range.
- `test/paper_trading/domain/test_nav_replay.py`
  - Added contract tests for ordering, cash-flow pricing, no-return behavior, and invalid NAV values.
- `test/paper_trading/services/test_nav_series.py`
  - Added contract tests for baseline eligibility, date filtering, and legacy share-count rejection.

## Interfaces

- `ReplayEvent(event_at, trade_date, event_type, source_id, source_kind, payload, quality_status)`
- `NavPoint`
- `ReplayResult`
- `NavSeriesReplay.replay(events, initial_state)`
- `NavSeriesBuilder.build(account_id, start_date=None, end_date=None, initial_state=None)`

## Tests

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py -v
```

Complete result:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/issue-82-nav-series
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 10 items

test/paper_trading/domain/test_nav_replay.py::test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id PASSED [ 10%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return PASSED [ 20%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[None] PASSED [ 30%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value1] PASSED [ 40%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value2] PASSED [ 50%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value3] PASSED [ 60%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value4] PASSED [ 70%]
test/paper_trading/services/test_nav_series.py::test_baseline_requires_provable_creation_ledger_or_history_source PASSED [ 80%]
test/paper_trading/services/test_nav_series.py::test_builder_filters_events_by_requested_date_without_using_account_share_count PASSED [ 90%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_legacy_baseline_from_current_account_share_count PASSED [100%]

============================== 10 passed in 0.21s ==============================
```

An initial pre-implementation run was also performed and correctly failed during collection because the new enum and interfaces did not yet exist.

## Unresolved concerns

- `NavSeriesBuilder` is intentionally a minimal contract coordinator. Repository-backed event loading and integration with existing services are deferred to later tasks.
- The replay contract does not alter matching or settlement behavior.
- No safe additional simplification was identified during the final manual simplify review; no local `simplify` skill file was available in `.agents/skills`.

## Remediation pass

### Changes

- Baseline eligibility now requires a non-empty mapping containing finite `opening_cash` and positive finite `opening_shares`. Empty lists, empty mappings, malformed values, and current-account share-count-only state are rejected.
- `NavSeriesBuilder.build` keeps the requested public signature (`account_id`, `start_date`, and `end_date`) and constructs replay baseline state internally from a qualifying initial event source.
- Replay ordering now rejects duplicate `(UTC event_at, precedence, source_id)` keys as ambiguous instead of relying on stable input ordering.
- Cash-flow payloads now use pre-event state. `total_assets` and `post_total_assets` are rejected, while `pre_total_assets` must agree with replay state when supplied, preventing double counting.
- `ReplayResult.points` is now a tuple, matching the immutable result contract.
- Added regression coverage for non-UTC timestamp normalization, ambiguous ordering, baseline construction and validation, and conflicting cash-flow payloads.

### Focused test command and complete result

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py -v
```

Complete result:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/issue-82-nav-series
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 15 items

test/paper_trading/domain/test_nav_replay.py::test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id PASSED [  6%]
test/paper_trading/domain/test_nav_replay.py::test_replay_rejects_events_with_identical_complete_ordering_key PASSED [ 13%]
test/paper_trading/domain/test_nav_replay.py::test_replay_normalizes_non_utc_event_timestamp_before_sorting PASSED [ 20%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return PASSED [ 26%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_pre_and_post_asset_payload PASSED [ 33%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_total_assets_that_could_be_double_counted PASSED [ 40%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[None] PASSED [ 46%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value1] PASSED [ 53%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value2] PASSED [ 60%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value3] PASSED [ 66%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value4] PASSED [ 73%]
test/paper_trading/services/test_nav_series.py::test_baseline_requires_provable_creation_ledger_or_history_source PASSED [ 80%]
test/paper_trading/services/test_nav_series.py::test_builder_filters_events_by_requested_date_without_using_account_share_count PASSED [ 86%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_legacy_baseline_from_current_account_share_count PASSED [ 93%]
test/paper_trading/services/test_nav_series.py::test_builder_constructs_baseline_state_from_provable_source PASSED [100%]

============================== 15 passed in 0.17s ==============================
```

### Unresolved concerns

- Repository-backed event loading and integration with existing services remain deferred to later tasks.
- Matching and settlement behavior remains unchanged.

## Scoped re-review remediation

### Changes

- `_baseline_from_events` now requires `SnapshotQualityStatus.VALID`; invalid-quality INITIAL events cannot establish a baseline.
- Cash-flow events now reject state-bearing `share_count`. The explicitly named `pre_share_count` is allowed only when it matches the replay state.
- Removed the duplicate, unreachable `MARKET_VALUATION` branch from `_apply_event`.
- Added regression tests for invalid-quality baseline events and conflicting cash-flow share-count payloads.

### Focused test command and complete output

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py -v
```

Complete output:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/issue-82-nav-series
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 17 items

test/paper_trading/domain/test_nav_replay.py::test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id PASSED [  5%]
test/paper_trading/domain/test_nav_replay.py::test_replay_rejects_events_with_identical_complete_ordering_key PASSED [ 11%]
test/paper_trading/domain/test_nav_replay.py::test_replay_normalizes_non_utc_event_timestamp_before_sorting PASSED [ 17%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return PASSED [ 23%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_pre_and_post_asset_payload PASSED [ 29%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_total_assets_that_could_be_double_counted PASSED [ 35%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_share_count_payload PASSED [ 41%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[None] PASSED [ 47%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value1] PASSED [ 52%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value2] PASSED [ 58%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value3] PASSED [ 64%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value4] PASSED [ 70%]
test/paper_trading/services/test_nav_series.py::test_baseline_requires_provable_creation_ledger_or_history_source PASSED [ 76%]
test/paper_trading/services/test_nav_series.py::test_builder_filters_events_by_requested_date_without_using_account_share_count PASSED [ 82%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_legacy_baseline_from_current_account_share_count PASSED [ 88%]
test/paper_trading/services/test_nav_series.py::test_builder_constructs_baseline_state_from_provable_source PASSED [ 94%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_invalid_quality_initial_as_baseline PASSED [100%]

============================== 17 passed in 0.08s ==============================
```

### Concerns

- Repository-backed event loading and later service integration remain deferred to subsequent tasks.
- Matching and settlement remain unchanged.

## Important findings remediation

### Changes

- A cash-flow payload containing `pre_share_count` now requires an existing replay `share_count` and must match it; missing state is rejected.
- Cash-flow payloads now reject state-bearing `nav`, ensuring pricing uses only the previously confirmed valid replay NAV or the `1` fallback.
- Added regression tests covering both rejection rules. Existing state-bearing `share_count` rejection and all prior contract tests remain covered.

### Focused test command and complete output

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py -v
```

Complete output:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /data/frog/.worktrees/issue-82-nav-series/.venv/bin/python
cachedir: .pytest_cache
rootdir: /data/frog/.worktrees/issue-82-nav-series
configfile: pyproject.toml
plugins: anyio-4.14.0
collecting ... collected 19 items

test/paper_trading/domain/test_nav_replay.py::test_replay_orders_same_timestamp_by_fixed_precedence_then_source_id PASSED [  5%]
test/paper_trading/domain/test_nav_replay.py::test_replay_rejects_events_with_identical_complete_ordering_key PASSED [ 10%]
test/paper_trading/domain/test_nav_replay.py::test_replay_normalizes_non_utc_event_timestamp_before_sorting PASSED [ 15%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_uses_previous_valid_nav_or_one_and_does_not_create_return PASSED [ 21%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_pre_and_post_asset_payload PASSED [ 26%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_total_assets_that_could_be_double_counted PASSED [ 31%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_conflicting_share_count_payload PASSED [ 36%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_pre_share_count_without_replay_share_state PASSED [ 42%]
test/paper_trading/domain/test_nav_replay.py::test_cash_flow_rejects_payload_nav_instead_of_overriding_replay_nav PASSED [ 47%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[None] PASSED [ 52%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value1] PASSED [ 57%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value2] PASSED [ 63%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value3] PASSED [ 68%]
test/paper_trading/domain/test_nav_replay.py::test_invalid_nav_values_produce_invalid_points[value4] PASSED [ 73%]
test/paper_trading/services/test_nav_series.py::test_baseline_requires_provable_creation_ledger_or_history_source PASSED [ 78%]
test/paper_trading/services/test_nav_series.py::test_builder_filters_events_by_requested_date_without_using_account_share_count PASSED [ 84%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_legacy_baseline_from_current_account_share_count PASSED [ 89%]
test/paper_trading/services/test_nav_series.py::test_builder_constructs_baseline_state_from_provable_source PASSED [ 94%]
test/paper_trading/services/test_nav_series.py::test_builder_rejects_invalid_quality_initial_as_baseline PASSED [100%]

============================== 19 passed in 0.09s ==============================
```

### Concerns

- Repository-backed event loading and later service integration remain deferred to subsequent tasks.
- Matching and settlement remain unchanged.
