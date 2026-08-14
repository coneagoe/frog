# Issue 59 Final Fix Report

## Findings Resolution

1. Critical migration allowlist: resolved in `monitor/storage/enum_migration.py`.
   Both `_CONDITION_CHECK_SQL` and `_NORMALIZED_CONDITION_CHECK` now include
   `close_cross_ma`. PostgreSQL regression coverage inserts an A-share daily
   `close_cross_ma` condition after migration and verifies the inserted row.

2. Important target-service scope validation: resolved in
   `monitor/monitor_target_service.py`. `add_target` validates that
   `close_cross_ma` is limited to market `A` and frequency `daily`.
   `update_target` obtains the persisted target when condition, market, or
   frequency changes and validates the effective combination. Invalid requests
   return the existing `VALIDATION_ERROR` result. The runner's defensive skip
   for persisted corrupt/nonconforming targets remains unchanged.

3. Deferred intraday runner coverage: resolved in
   `test/monitor/test_monitor_runner.py`. A persisted intraday
   `close_cross_ma` target is skipped without final-close retrieval, realtime
   pricing, email, or state mutation.

4. Deferred implicit-date runner coverage: resolved in
   `test/monitor/test_monitor_runner.py`. The module `datetime` seam is frozen
   at 2026-06-04 00:30 Asia/Shanghai and confirms omitted `as_of_date` is
   passed to storage retrieval as `date(2026, 6, 4)`.

## Verification

- `uv run pytest test/monitor/test_monitor_target_service.py::test_add_target_rejects_close_cross_ma_outside_a_share_daily_scope test/monitor/test_monitor_target_service.py::test_update_target_rejects_close_cross_ma_scope_changes test/monitor/test_monitor_runner.py::test_final_close_intraday_target_skips_without_provider_or_state_update test/monitor/test_monitor_runner.py::test_final_close_without_as_of_date_uses_current_shanghai_date -v`
  - 4 passed.
- `tools/run_tests.sh test/monitor/storage/test_enum_migration.py::test_apply_accepts_a_share_daily_close_cross_ma_condition -v`
  - 1 passed using the isolated PostgreSQL `test_db` container.
- `uv run pytest test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py -v`
  - 52 passed.
- `tools/run_tests.sh test/monitor/storage/test_enum_migration.py -v`
  - 20 passed using the isolated PostgreSQL `test_db` container.
- `uv run pytest test/monitor/test_condition.py test/monitor/test_condition_validation.py test/monitor/test_monitor_target_service.py test/monitor/test_price_fetcher.py test/monitor/test_monitor_runner.py test/dags/test_monitor_stock_daily.py -v`
  - 106 passed.
- `uv run ruff format --check monitor/monitor_target_service.py monitor/storage/enum_migration.py test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py test/monitor/storage/test_enum_migration.py`
  - passed.
- `uv run ruff check monitor/monitor_target_service.py monitor/storage/enum_migration.py test/monitor/test_monitor_target_service.py test/monitor/test_monitor_runner.py test/monitor/storage/test_enum_migration.py`
  - all checks passed.
- `uv run mypy monitor/monitor_target_service.py monitor/storage/enum_migration.py`
  - success with no issues in 2 source files; mypy printed only pre-existing unused-config-section notes.

## Documentation Decision

Invoked `update_doc` before committing. Checked `docs/stock_monitor.md`; no
documentation edit was needed because it already describes `close_cross_ma` as
A-share daily-only and storage-HFQ based. This correction restores validation
and migration support for that existing contract without changing user-facing
behavior. No other documentation is affected.

## Commit

- Implementation and tests: `65297e2 fix: enforce final close MA crossover scope`

## Self Review

- Confirmed the migration CHECK definition and its normalized verifier carry
  the same ordered allowlist.
- Confirmed joint scope validation is applied to both add and effective update
  state, while unrelated update paths remain unchanged.
- Confirmed the runner retains defensive skipping for invalid persisted rows.
- Confirmed no production changes touch `price_cross_ma` or `price_vs_ma`.
- Confirmed `git diff --check` was clean before the implementation commit.
