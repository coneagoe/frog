# Task 3 Report: Shared Replay and NAV Series

## Result

- INITIAL replay preserves persisted `cash_available`, `cash_frozen`,
  `pending_settlement`, `total_assets`, and cumulative cash-flow fields.
- Replay and recalculation use explicit `None` checks, preserving persisted
  `Decimal("0")` values.
- `NavSeriesBuilder.prepare(account_id)` remains the public replay preparation
  API used by recalculation.
- Cash-only requested dates are materialized; invalid valuation points preserve
  later replay state; expected missing/stale data is unavailable while provider
  failures are failed errors with rollback.
- Existing freeze/trade/release, HK expected settlement date, holdings/cost,
  corporate action, market+symbol, backdated cash-flow, idempotency, and
  external rollback behavior remains covered.
- No matching or settlement business files were modified.

## Tests

Focused local suite:

```text
uv run pytest test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q
94 passed, 2 skipped
```

PostgreSQL-backed Task 3 integration tests:

```text
tools/run_tests.sh test/paper_trading/domain/test_nav_replay.py test/paper_trading/services/test_nav_series.py test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py -q
96 passed
```

The PostgreSQL tests use isolated schemas and exercise persisted repository
events, real `SnapshotRecalculationService.recalculate()`, trading snapshots,
and cleanup. Scoped Ruff format/check and `git diff --check` passed.

## Concerns

- The repository settlement cash ledger does not persist a separate processing
  business date, so HK settlement timing is normalized in the Task 3 NAV
  preparation layer from `PaperPendingSettlement.expected_settle_date`.
- Full repository-wide tests remain outside this scoped Task 3 verification.
