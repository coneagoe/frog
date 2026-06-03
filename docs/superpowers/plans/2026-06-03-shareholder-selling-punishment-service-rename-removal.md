# Shareholder Selling Punishment Service Rename Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy `ShareholderSellingBlackroomSyncService` name from code and affected docs so the repo only uses `ShareholderSellingPunishmentService`.

**Architecture:** This is a hard cut-over, not a deprecation pass. The implementation removes the old alias from the service and CLI modules, updates tests to assert only the new class name, and rewrites affected internal docs so written guidance matches the code.

**Tech Stack:** Python 3.12, pytest, Poetry, Markdown docs, ripgrep for verification

---

## File Structure

- Modify: `monitor/shareholder_selling_punishment.py` — keep the implementation on `ShareholderSellingPunishmentService` and delete the old alias export.
- Modify: `tools/stock_monitor_cli.py` — stop re-exporting `ShareholderSellingBlackroomSyncService`.
- Modify: `test/monitor/test_shareholder_selling_punishment.py` — remove alias compatibility coverage and replace it with new-name-only coverage.
- Modify: `test/tools/test_stock_monitor_cli.py` — add a module-export regression test that forbids the old alias.
- Modify: `docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md` — replace the old class name in the DAG design doc.
- Modify: `docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md` — replace old code snippets and patch targets with the new class name.
- Modify: `docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md` — update the historic plan text so it no longer presents the old class name as current guidance.
- Modify: `docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md` — replace the old recommended class name with the new one.

### Task 1: Remove the service-module compatibility alias

**Files:**
- Modify: `test/monitor/test_shareholder_selling_punishment.py`
- Modify: `monitor/shareholder_selling_punishment.py`
- Test: `test/monitor/test_shareholder_selling_punishment.py`

- [ ] **Step 1: Write the failing test**

Replace the old alias-compatibility test at the top of `test/monitor/test_shareholder_selling_punishment.py` with this new test and remove the old-name import from the import block:

```python
import monitor.shareholder_selling_punishment as punishment_module
from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService


def test_only_new_sync_service_name_is_exported():
    bsvc = MagicMock()

    service = ShareholderSellingPunishmentService(blackroom_service=bsvc)

    assert service.blackroom_service is bsvc
    assert not hasattr(punishment_module, "ShareholderSellingBlackroomSyncService")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest test/monitor/test_shareholder_selling_punishment.py::test_only_new_sync_service_name_is_exported -v`
Expected: FAIL because `ShareholderSellingBlackroomSyncService` still exists on `monitor.shareholder_selling_punishment`.

- [ ] **Step 3: Write minimal implementation**

Delete the alias line at the bottom of `monitor/shareholder_selling_punishment.py` so the file ends like this:

```python
    def _propagate_failure(
        self, result: dict[str, Any], default_code: str, default_message: str
    ) -> dict[str, Any]:
        return self._result(
            False,
            str(result.get("code") or default_code),
            str(result.get("message") or default_message),
            result.get("data"),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest test/monitor/test_shareholder_selling_punishment.py::test_only_new_sync_service_name_is_exported -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add test/monitor/test_shareholder_selling_punishment.py monitor/shareholder_selling_punishment.py
git commit -m "refactor: drop legacy shareholder selling alias"
```

### Task 2: Remove the CLI alias and keep runtime references on the new name

**Files:**
- Modify: `tools/stock_monitor_cli.py`
- Modify: `test/tools/test_stock_monitor_cli.py`
- Test: `test/tools/test_stock_monitor_cli.py`
- Test: `test/dags/test_monitor_stock_daily.py`

- [ ] **Step 1: Write the failing tests**

Add this CLI-focused test near the existing blackroom sync tests in `test/tools/test_stock_monitor_cli.py`:

```python
import tools.stock_monitor_cli as stock_monitor_cli_module


def test_cli_module_exports_only_new_sync_service_name():
    assert hasattr(stock_monitor_cli_module, "ShareholderSellingPunishmentService")
    assert not hasattr(stock_monitor_cli_module, "ShareholderSellingBlackroomSyncService")
```

Do not change `test/dags/test_monitor_stock_daily.py`; it should continue patching the new name only:

```python
    monkeypatch.setattr(
        "monitor.shareholder_selling_punishment.ShareholderSellingPunishmentService",
        service,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest test/tools/test_stock_monitor_cli.py::test_cli_module_exports_only_new_sync_service_name test/dags/test_monitor_stock_daily.py -v`
Expected: FAIL because `tools.stock_monitor_cli` still defines `ShareholderSellingBlackroomSyncService`.

- [ ] **Step 3: Write minimal implementation**

Delete the CLI alias line in `tools/stock_monitor_cli.py` so the import/alias block looks like this:

```python
from monitor.shareholder_selling_punishment import (
    ShareholderSellingPunishmentService,
)

BlackroomManagementService = BlackroomService
```

Keep the dependency-injection types and constructor call on the new name:

```python
def main(
    argv: list[str] | None = None,
    service: MonitorTargetService | None = None,
    blackroom_service: BlackroomService | None = None,
    sync_service: ShareholderSellingPunishmentService | None = None,
    countdown_service: BlackroomCountdownService | None = None,
) -> int:
```

```python
    if cmd == "sync-shareholder-selling":
        effective_sync_service = sync_service or ShareholderSellingPunishmentService(
            blackroom_service=_get_bsvc()
        )
        return effective_sync_service.sync(
            start_date=args.start_date, end_date=args.end_date, ban_days=args.ban_days
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest test/tools/test_stock_monitor_cli.py::test_cli_module_exports_only_new_sync_service_name test/dags/test_monitor_stock_daily.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/stock_monitor_cli.py test/tools/test_stock_monitor_cli.py test/dags/test_monitor_stock_daily.py
git commit -m "refactor: remove old shareholder selling cli alias"
```

### Task 3: Update affected docs to the new class name only

**Files:**
- Modify: `docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md`
- Modify: `docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md`
- Modify: `docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md`
- Modify: `docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md`

- [ ] **Step 1: Run the failing doc search**

Run: `rg "ShareholderSellingBlackroomSyncService" docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md`
Expected: multiple matches in the four docs above.

- [ ] **Step 2: Rewrite the affected doc snippets**

Apply these replacements:

In `docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md` change:

```markdown
1. `sync_shareholder_selling_blackroom` calls `ShareholderSellingPunishmentService.sync(...)`.
```

In `docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md` change the monkeypatch/import snippets to:

```python
    monkeypatch.setattr(
        "monitor.shareholder_selling_punishment.ShareholderSellingPunishmentService",
        service,
    )
```

```python
def sync_shareholder_selling_blackroom(**context):
    """Sync shareholder-selling announcements into blackroom bans every scheduled day."""
    from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService

    run_date = _format_logical_date(context)
    result = ShareholderSellingPunishmentService().sync(
        start_date=run_date,
        end_date=run_date,
        ban_days=180,
    )
```

In `docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md` update the file-structure bullet and historical code snippets so they use only `ShareholderSellingPunishmentService`, for example:

```markdown
- Modify: `monitor/shareholder_selling_punishment.py` — keep `ShareholderSellingPunishmentService` as the sync service name and route it through `BlackroomService`.
```

```python
from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService


def test_only_new_sync_service_name_is_exported():
    bsvc = MagicMock()
    service = ShareholderSellingPunishmentService(blackroom_service=bsvc)
    assert service.blackroom_service is bsvc
```

In `docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md` change the recommended name block to:

```python
ShareholderSellingPunishmentService
```

- [ ] **Step 3: Run the doc search to verify it is clean**

Run: `rg "ShareholderSellingBlackroomSyncService" docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md
git commit -m "docs: update shareholder selling service name"
```

### Task 4: Final targeted verification

**Files:**
- Test: `test/monitor/test_shareholder_selling_punishment.py`
- Test: `test/dags/test_monitor_stock_daily.py`
- Test: `test/tools/test_stock_monitor_cli.py`
- Verify: `docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md`
- Verify: `docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md`
- Verify: `docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md`
- Verify: `docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md`

- [ ] **Step 1: Run the full targeted verification command**

Run: `poetry run pytest test/monitor/test_shareholder_selling_punishment.py test/dags/test_monitor_stock_daily.py test/tools/test_stock_monitor_cli.py`
Expected: all targeted tests pass.

- [ ] **Step 2: Run the final old-name search**

Run: `rg "ShareholderSellingBlackroomSyncService" monitor tools test/monitor/test_shareholder_selling_punishment.py test/tools/test_stock_monitor_cli.py docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md`
Expected: no matches.

- [ ] **Step 3: Commit the final clean state if needed**

If Task 4 made no new file changes, do not create an extra commit. If you had to make a small verification-driven fix, commit only those final edits:

```bash
git add monitor/shareholder_selling_punishment.py tools/stock_monitor_cli.py test/monitor/test_shareholder_selling_punishment.py test/dags/test_monitor_stock_daily.py test/tools/test_stock_monitor_cli.py docs/superpowers/specs/2026-06-03-monitor-blackroom-dag-design.md docs/superpowers/plans/2026-06-03-monitor-blackroom-dag.md docs/superpowers/plans/2026-06-01-blackroom-countdown-refactor.md docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md
git commit -m "refactor: finalize shareholder selling service rename"
```
