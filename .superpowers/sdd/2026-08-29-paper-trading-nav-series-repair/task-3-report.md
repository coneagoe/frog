# Task 3 Report: Shared Replay and NAV Series

## Status

Complete for the recovered Task 3 scope.

## Changes

- `NavSeriesBuilder` preserves persisted INITIAL cash components, total assets,
  share count, cumulative deposits/withdrawals, and pending settlement state.
- Persisted imported position lots are reconstructed into INITIAL holdings and
  cost maps before replay. Current trade-derived aggregate positions are not
  treated as initial holdings, preventing double counting; legacy imported
  aggregate positions without lots remain supported as a fallback.
- `SnapshotRecalculationService` carries baseline holdings and costs into the
  replay-backed materializer.
- PostgreSQL recalculation coverage creates every table queried by
  `list_replay_events()` and its foreign-key dependencies, then invokes the
  real repository-backed `SnapshotRecalculationService.recalculate()`.
- No matching, settlement, or Task 4+ business files were modified.

## Verification

Local focused suite:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q
96 passed, 3 skipped
```

PostgreSQL-backed focused suite:

```text
tools/run_tests.sh test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q
99 passed
```

Scoped Ruff:

```text
uv run ruff format paper_trading/services/nav_series.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
uv run ruff check paper_trading/services/nav_series.py paper_trading/services/snapshot_recalculation_service.py test/paper_trading/services/test_snapshot_recalculation_service.py
All checks passed.
```

The PostgreSQL integration test verifies `cash_available=70`,
`cash_frozen=0` after consuming a persisted frozen buy allocation,
`pending_settlement=20`, imported holdings/cost, the accounting identity,
share count, zero-valued cumulative flow fields, and repeat recalculation
stability. The separate real PostgreSQL recalculation test also verifies
bounded snapshot persistence.

`git diff --check` passed.

## Concerns

- `replace_trading_snapshots()` replaces derived rows, so database row IDs are
  not treated as an idempotency contract; repeat recalculation is verified by
  stable dates and values instead.
- The repository settlement cash ledger does not persist a separate processing
  business date, so HK settlement timing remains normalized in the Task 3 NAV
  preparation layer from `PaperPendingSettlement.expected_settle_date`.
- Full repository-wide tests remain outside this scoped Task 3 verification.
