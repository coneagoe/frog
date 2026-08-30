# Task 2 Report: Ordered Event Adapter and Repository Reads

## Status

Task 2 round 4 final review coverage is complete. The authoritative evidence
is the focused SQLite/domain run, the PostgreSQL-backed repository run, and
the scoped Ruff check recorded below.

## Scope

Modified only:

- `paper_trading/storage/repository.py`
- `test/paper_trading/storage/test_repository.py`
- this report

No Task 3+ files and no matching or settlement code were modified.

## Changes

- Added a parameterized SQLite/PostgreSQL write-stage failure regression for
  `replace_trading_snapshots()`. It creates two existing trading snapshots,
  calls the real `save_trading_snapshot()` for replacement writes, injects an
  exception from the second `before_flush` after the first replacement write,
  calls `expire_all()`, reloads through an independent Session, and verifies
  the old range's complete persisted field signatures including `created_at`,
  count, and ID set are restored. The original Session is queried again to
  verify it remains usable.
- Added a PostgreSQL-backed repository fixture using an isolated schema and the
  canonical paper-trading enum migration. The parity test writes the same
  account, order/trade, cash-ledger, corporate-action, and valuation facts to
  SQLite and PostgreSQL and compares ordered event identity, `event_at`,
  quality status, and complete payloads.
- Normalized replay Decimal payloads through the existing account-money,
  NAV, and share quantizers. This removes SQLite binary-float residue while
  preserving the repository's 12-decimal precision contract.
- Applied Ruff import ordering and line wrapping in the two touched source/test
  files.

Previously verified Task 2 behavior remains covered: cash-ledger event
classification, creation baseline and latest bounded baseline selection,
complete corporate-action payload, invalid legacy/naive timestamps, stable
ordering, cash-only account selection, and mixed-dividend economic assertions.

## Verification

### Scoped Ruff

Command:

```text
uv run ruff check paper_trading/storage/repository.py test/paper_trading/storage/test_repository.py
```

Output:

```text
All checks passed!
```

Exit status: `0`.

### Focused SQLite/domain tests

Command:

```text
uv run pytest test/paper_trading/storage/test_repository.py test/paper_trading/domain/test_nav_replay.py -v
```

Output summary:

```text
collected 129 items
======================= 127 passed, 2 skipped in 52.70s =======================
```

The two skipped parameter cases are the PostgreSQL rollback and parity cases
because this direct command does not provide `TEST_POSTGRESQL_URL`. This is
expected and is not the PostgreSQL evidence path.

Exit status: `0`.

### PostgreSQL-backed repository tests

Command:

```text
tools/run_tests.sh test/paper_trading/storage/test_repository.py -v
```

Relevant runner output:

```text
Container issue-82-nav-series-test_db-1 Healthy
collected 115 items
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[sqlite_repository] PASSED
test/paper_trading/storage/test_repository.py::test_replace_trading_snapshots_restores_all_old_rows_when_second_write_fails[postgres_repository] PASSED
test/paper_trading/storage/test_repository.py::test_list_replay_events_preserves_decimal_payload_across_sqlite_and_postgresql PASSED
============================= 115 passed in 54.26s =============================
```

Exit status: `0`. The parity test ran against the isolated PostgreSQL service;
it was not skipped or blocked.

### Whitespace

Command:

```text
git diff --check
```

Output: no findings. Exit status: `0`.

## Concerns and limits

- The direct focused command reports the PostgreSQL rollback and parity cases as
  skipped by design; the required `tools/run_tests.sh` run provides the actual
  PostgreSQL results. No PostgreSQL case was blocked under the runner.
- The runner emits the existing locale warning
  `setlocale: LC_ALL: cannot change locale (en_US.UTF-8)` and Docker's
  `No services to build` warning. Neither affected test execution.
- The parity assertion compares event ordering identity, `event_at`, quality
  status, and complete payload values. SQLite timezone-aware columns load as
  naive datetimes in this project; the test explicitly records SQLite
  `INVALID` versus PostgreSQL `VALID` quality while comparing the event
  timestamp value and all other event content.

## Final result

Task 2 round 4 final review coverage is complete. SQLite and PostgreSQL both
verified replacement rollback and replay Decimal parity; no requested test is
blocked under the PostgreSQL runner.
