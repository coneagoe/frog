## Task 1 review-fix report

- Changed files:
  - `paper_trading/storage/repository.py` — removed unused `snapshot_dates` assignment.
  - `paper_trading/services/snapshot_recalculation_service.py` — removed unused `SnapshotPointType` import.
- Ruff: `uv run ruff check paper_trading/storage/repository.py paper_trading/services/snapshot_recalculation_service.py`
  - Output: `All checks passed!`
- Focused tests:
  - Repository canonical tests: `2 passed, 136 deselected`.
  - Snapshot service metadata test: `1 passed, 41 deselected`.
  - Snapshot recalculation idempotent/historical tests: `2 passed, 20 deselected`.
  - The full focused three-file run reported `187 passed, 7 skipped, 8 failed`; the failures are pre-existing behavior/test mismatches outside this unused-symbol cleanup.
- Commit: `71231c00eca36e1248c570d17735752c6eea0fbc`
