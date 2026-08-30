# Task 3 Report: Shared Replay and NAV Series

## Modified files

- `paper_trading/domain/nav_replay.py`
  - Replay state now remains authoritative between events rather than allowing
    valuation payload fields to overwrite state before event application.
  - Initial events accept both opening-state and legacy total-assets/share-count
    payload shapes.
  - Cash flows price share issuance/redemption from the latest valid replay NAV,
    defaulting to NAV 1 when no valid NAV exists.
  - Market valuation events require an explicit finite valuation input; missing
    valuation produces an invalid point instead of carrying a stale NAV.
  - Settlement and corporate-action cash deltas are replayed against the current
    state.

- `paper_trading/services/nav_series.py`
  - Preserved the existing builder API and formatted the date-range filter.

- `paper_trading/services/snapshot_service.py`
  - Normalizes SQLite-reloaded historical snapshot timestamps to UTC before
    passing them through the timezone/provenance-enforcing repository API.

- `test/paper_trading/domain/test_nav_replay.py`
  - Added backdated cash-flow/later-valuation consistency coverage.
  - Added missing-market-valuation gap coverage.

## Interfaces

- Existing public APIs were preserved:
  - `NavSeriesReplay.replay(events, initial_state)`
  - `NavSeriesBuilder.build(account_id, start_date, end_date)`
  - `SnapshotService.generate_snapshot_or_gap(...)`
  - `SnapshotRecalculationService.recalculate(...)`
- No matching or settlement modules were modified.

## Verification

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

Output:

```text
============================= 77 passed in 16.63s ==============================
```

Command:

```text
uv run ruff check paper_trading/domain/nav_replay.py paper_trading/services/nav_series.py paper_trading/services/snapshot_service.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

Output:

```text
All checks passed!
```

Command:

```text
git diff --check
```

Output: passed with no whitespace errors.

## Concerns

- The existing recalculation service still delegates historical materialization
  to `SnapshotService.generate_snapshot_or_gap`, which reads current account
  state. A broader replay-backed snapshot materialization path, including full
  bounded replacement and cash-only active-date generation, remains for the
  orchestrator/owner to verify against hidden integration coverage.
- No database-dependent test runner was invoked; the focused service tests use
  their existing SQLite fixtures and mocks.
- Documentation skill review found no README/AGENTS/topic-document changes
  warranted by this internal implementation.

## Follow-up implementation

- `paper_trading/services/nav_series.py`
  - The default builder path now requires a repository and calls its
    `list_replay_events(account_id)` adapter; the explicit `event_loader` test
    seam remains supported.
  - Trade settlement facts duplicated in cash-ledger rows are deduplicated by
    `trade_id` before replay.
  - Baseline validation accepts the persisted initial snapshot payload shape as
    well as the opening-state shape.

- `paper_trading/domain/nav_replay.py`
  - Replay points now carry cash, holdings, costs, valuation quality, and
    valuation details.
  - Trade settlements rebuild symbol quantities/costs and cash; corporate
    actions apply quantity, cost, and cash deltas.
  - Missing valuation input invalidates only the current NAV point while
    preserving replay cash/holdings/state for later events.

- `paper_trading/services/snapshot_recalculation_service.py`
  - Recalculation derives affected dates from replay events, snapshots, gaps,
    and the requested bounds.
  - Historical valuation points are generated from replay holdings/cost state,
    then materialized through bounded `replace_trading_snapshots`.
  - Existing derived event timestamps are preserved, gaps are resolved only
    after successful valuation, and any failure rolls back external sessions as
    well as service-owned sessions.

- `test/paper_trading/services/test_nav_series.py`
  - Added a real SQLite repository-to-builder integration test.

- `test/paper_trading/services/test_snapshot_recalculation_service.py`
  - Updated focused service expectations to the replay-backed recalculation
    contract and its baseline guard.

## Follow-up verification

Command:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

Output:

```text
============================= 79 passed in 16.36s ==============================
```

Command:

```text
uv run ruff check paper_trading/domain/nav_replay.py paper_trading/services/nav_series.py paper_trading/services/snapshot_service.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

Output:

```text
All checks passed!
```

Follow-up concerns:

- The replay materializer intentionally remains within the four-file Task 3
  scope and uses existing repository replacement APIs; full PostgreSQL
  integration verification remains the orchestrator's responsibility.
- The focused legacy mock cases now verify the baseline guard rather than
  invoking the removed per-date snapshot-generation path.
- Added focused coverage that a replay/baseline failure rolls back a
  caller-owned SQLAlchemy session.

## Final follow-up implementation

- `paper_trading/services/nav_series.py`
  - Preserved the legacy positional callable constructor form while making the
    repository-backed `list_replay_events` path the default when a repository
    is supplied.
  - Added deterministic settlement-ledger deduplication and corporate-action
    ledger exclusion.

- `paper_trading/domain/nav_replay.py`
  - Added cumulative deposit/withdrawal/net-cash-flow state to every point.
  - Trade replay now validates sides, tracks market+symbol holdings, includes
    buy fees in cost, and reduces sell cost using average cost.
  - Corporate actions update market+symbol quantity/cost/cash state.
  - Missing valuations leave cash, holdings, costs, shares, and cumulative
    flow state intact for subsequent events.

- `paper_trading/services/snapshot_recalculation_service.py`
  - Materialized snapshots now write replay cumulative cash-flow values and
    preserve stale/gap valuation metadata through replay valuation events.
  - Existing bounded replacement and external-session rollback behavior remain
    enforced.

- Tests added for positional/default builder compatibility, gap state
  preservation, cumulative cash flow, trade average cost and fees, multi-market
  symbol separation, corporate-action quantity/cost/cash updates, and invalid
  trade sides.

## Final verification

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

```text
============================= 84 passed in 15.61s ==============================
```

```text
uv run ruff format paper_trading/domain/nav_replay.py paper_trading/services/nav_series.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_recalculation_service.py
uv run ruff check paper_trading/domain/nav_replay.py paper_trading/services/nav_series.py paper_trading/services/snapshot_service.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
```

```text
2 files reformatted, 4 files left unchanged
All checks passed!
```

`git diff --check`: passed.
