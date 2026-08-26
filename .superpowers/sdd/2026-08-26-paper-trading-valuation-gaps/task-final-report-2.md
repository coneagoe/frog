# Task 4 Final Fix Wave 2 Report

## Status

Complete.

## Findings Fixed

1. Historical valuation-only recalculation now passes `preserve_account_nav=True` and does not update the account's current live `share_count`, `net_asset_value`, or cumulative NAV state. Historical snapshot values are still recalculated.
2. In-place historical trading snapshots preserve their existing `event_at`. A regression test recalculates an older date after a newer point and verifies chronological repository ordering and event timestamps remain stable.
3. Exact-bar closes and suspended prior closes are validated as finite, strictly positive decimals. Missing, malformed, non-finite, zero, negative, and provider-error cases become deterministic valuation gaps with `invalid_close`, `missing_exact_bar`, `missing_prior_close`, or `market_data_error` details as applicable.

## Files Changed

- `paper_trading/services/snapshot_service.py`
- `paper_trading/services/snapshot_recalculation_service.py`
- `test/paper_trading/services/test_snapshot_recalculation_service.py`
- `test/paper_trading/services/test_analytics_service.py`
- `.superpowers/sdd/2026-08-26-paper-trading-valuation-gaps/task-final-report-2.md`

## Exact Commands And Results

- `uv run pytest test/paper_trading/services/test_snapshot_service.py test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/api/test_snapshot_recalculation_api.py test/paper_trading/services/test_analytics_service.py::test_total_return_and_risk_preserve_same_day_repository_order -q`
  - Passed: 45 passed, 1 existing Starlette/httpx deprecation warning.
- `uv run ruff format --check paper_trading/services/snapshot_recalculation_service.py paper_trading/services/snapshot_service.py test/paper_trading/api/test_snapshot_recalculation_api.py test/paper_trading/services/test_snapshot_recalculation_service.py`
  - Passed after formatting: 4 files already formatted.
- `uv run ruff check paper_trading/services/snapshot_recalculation_service.py paper_trading/services/snapshot_service.py test/paper_trading/api/test_snapshot_recalculation_api.py test/paper_trading/services/test_snapshot_recalculation_service.py test/paper_trading/services/test_analytics_service.py`
  - Passed: all checks passed.
- `uv run mypy paper_trading/services/snapshot_service.py paper_trading/services/snapshot_recalculation_service.py`
  - Passed: no issues found in 2 source files. Mypy emitted only the existing unused-override-section note from `pyproject.toml`.
- `git diff --check`
  - Passed before commit.

## Self-Review

- Normal snapshot generation retains its prior live-account NAV update and current-time event behavior; historical preservation is limited to recalculation mode.
- Existing trading snapshot identity is preserved by the repository upsert, and the historical timestamp is reused before the update.
- Invalid provider values cannot reach market-value arithmetic or produce valid snapshots.
- Provider exceptions in exact-bar and suspended-prior-close paths are converted to deterministic gap details.

## Concerns

- Focused pytest retains the existing Starlette/httpx deprecation warning.
- Broader repository validation remains outside this fix wave.
