# Blackroom Shareholder Selling Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make shareholder-selling blackroom bans start from the announcement date and reset existing active bans when a shareholder sells again.

**Architecture:** Add a small active-record lookup to `BlackroomService`, then update `ShareholderSellingPunishmentService` to create or reset records based on that lookup. Keep storage behavior unchanged: `update_blackroom_record()` already recomputes `expire_at` when `start_at` or `ban_days` changes.

**Tech Stack:** Python 3.11+, pytest, unittest.mock, pandas, existing `poetry run` command conventions.

---

## File Structure

- Modify `monitor/blackroom_service.py`
  - Add `get_active_record(stock_code, market)` business method.
  - Add `active_record(...)` alias for internal service-style use.
  - Reuse `storage.list_active_blackroom_records(market=...)` and existing `_serialize(...)`.
- Modify `monitor/shareholder_selling_punishment.py`
  - Parse row `ann_date` as UTC midnight.
  - Use `BlackroomService.get_active_record(...)` instead of `is_banned(...)`.
  - Create new records with `start_at=announcement_start`.
  - Reset existing records with `update_record(...)`.
  - Track `added`, `reset`, `skipped`, and per-record `action`.
  - Deduplicate repeated rows for the same stock by keeping the latest `ann_date` row.
- Modify `test/monitor/test_blackroom_service.py`
  - Cover active record lookup success and not-found behavior.
- Modify `test/monitor/test_shareholder_selling_punishment.py`
  - Cover announcement-date starts, active-record reset, latest-row dedupe, counts, and invalid `ann_date` failure.

---

### Task 1: Add active blackroom record lookup

**Files:**
- Modify: `test/monitor/test_blackroom_service.py`
- Modify: `monitor/blackroom_service.py`

- [ ] **Step 1: Write failing tests for active record lookup**

Add these tests after `test_is_banned_uses_active_records()` in `test/monitor/test_blackroom_service.py`:

```python
def test_get_active_record_returns_matching_serialized_record():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [
        _record(id=3, stock_code="000001"),
        _record(id=7, stock_code="600519"),
    ]

    result = BlackroomService(storage=storage).get_active_record("600519", "A")

    assert result["success"] is True
    assert result["data"]["id"] == 7
    assert result["data"]["stock_code"] == "600519"
    storage.list_active_blackroom_records.assert_called_once_with(market="A")


def test_get_active_record_returns_none_when_stock_not_active():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="000001")]

    result = BlackroomService(storage=storage).get_active_record("600519", "A")

    assert result == {
        "success": True,
        "code": "OK",
        "message": "active record checked",
        "data": None,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_service.py::test_get_active_record_returns_matching_serialized_record test/monitor/test_blackroom_service.py::test_get_active_record_returns_none_when_stock_not_active -v
```

Expected: FAIL with `AttributeError: 'BlackroomService' object has no attribute 'get_active_record'`.

- [ ] **Step 3: Implement `get_active_record`**

In `monitor/blackroom_service.py`, add this method after `is_banned(...)` and before `is_buy_banned(...)`:

```python
    def get_active_record(self, stock_code: str, market: str) -> dict[str, Any]:
        try:
            self._validate_stock_code(stock_code)
            self._validate_market(market)

            active = self.storage.list_active_blackroom_records(market=market)
            for record in active:
                if getattr(record, "stock_code", None) == stock_code:
                    return self._result(
                        True,
                        "OK",
                        "active record checked",
                        self._serialize(record),
                    )

            return self._result(True, "OK", "active record checked", None)
        except BlackroomValidationError as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, "STORAGE_ERROR", str(exc), None)
```

Then add this alias in the public short aliases section after `check(...)`:

```python
    def active_record(self, stock_code: str, market: str) -> dict[str, Any]:
        return self.get_active_record(stock_code=stock_code, market=market)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_service.py::test_get_active_record_returns_matching_serialized_record test/monitor/test_blackroom_service.py::test_get_active_record_returns_none_when_stock_not_active -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

Only commit if the user explicitly requested commits. If committing is allowed, run:

```bash
git add test/monitor/test_blackroom_service.py monitor/blackroom_service.py
git commit -m "feat: add active blackroom record lookup"
```

---

### Task 2: Write shareholder-selling reset tests

**Files:**
- Modify: `test/monitor/test_shareholder_selling_punishment.py`

- [ ] **Step 1: Add datetime imports used by new assertions**

Change the import block at the top of `test/monitor/test_shareholder_selling_punishment.py` from:

```python
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
```

to:

```python
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
```

- [ ] **Step 2: Replace old skip test with create-and-reset behavior test**

Replace `test_sync_dedupes_per_stock_skips_existing_and_adds_new(...)` with:

```python
def test_sync_dedupes_per_stock_resets_existing_and_adds_new(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock(spec_set=["stk_holdertrade"])
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [
            {"ts_code": "600519.SH", "ann_date": "20250101", "holder_name": "股东A"},
            {"ts_code": "600519.SH", "ann_date": "20250102", "holder_name": "股东B"},
            {"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"},
        ]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.get_active_record.side_effect = [
        {
            "success": True,
            "code": "OK",
            "message": "",
            "data": {"id": 9, "stock_code": "600519", "market": "A"},
        },
        {"success": True, "code": "OK", "message": "", "data": None},
    ]
    blackroom_service.update_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "record updated",
        "data": {"id": 9},
    }
    blackroom_service.ban.return_value = {
        "success": True,
        "code": "OK",
        "message": "record created",
        "data": {"id": 11},
    }

    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert list(result.keys()) == ["success", "code", "message", "data"]
    assert result["success"] is True
    assert result["code"] == "OK"
    assert result["data"]["fetched"] == 3
    assert result["data"]["unique_stocks"] == 2
    assert result["data"]["added"] == 1
    assert result["data"]["reset"] == 1
    assert result["data"]["skipped"] == 0
    assert result["data"]["records"] == [
        {
            "stock_code": "600519",
            "market": "A",
            "ann_date": "20250102",
            "holder_name": "股东B",
            "action": "reset",
        },
        {
            "stock_code": "000001",
            "market": "A",
            "ann_date": "20250103",
            "holder_name": "股东C",
            "action": "added",
        },
    ]

    pro_client.stk_holdertrade.assert_called_once_with(
        start_date="20250101", end_date="20250131", in_de="DE"
    )
    blackroom_service.get_active_record.assert_any_call("600519", "A")
    blackroom_service.get_active_record.assert_any_call("000001", "A")
    blackroom_service.update_record.assert_called_once_with(
        9,
        start_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        ban_days=30,
        remaining_days=30,
        source="shareholder_selling",
        note="股东减持公告 20250102 / 股东B",
    )
    blackroom_service.ban.assert_called_once_with(
        stock_code="000001",
        market="A",
        ban_days=30,
        start_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        source="shareholder_selling",
        note="股东减持公告 20250103 / 股东C",
    )
```

- [ ] **Step 3: Update empty-provider expectation with `reset` count**

In `test_sync_returns_success_with_zero_counts_when_tushare_empty(...)`, change the expected `data` dict to include `reset`: 

```python
        "data": {
            "fetched": 0,
            "unique_stocks": 0,
            "added": 0,
            "reset": 0,
            "skipped": 0,
            "records": [],
        },
```

Then replace the old assertion:

```python
    blackroom_service.is_banned.assert_not_called()
```

with:

```python
    blackroom_service.get_active_record.assert_not_called()
```

- [ ] **Step 4: Update failure-path tests to use active lookup**

In `test_sync_stops_and_propagates_when_check_fails(...)`, rename the mocked failing call from `is_banned` to `get_active_record`:

```python
    blackroom_service.get_active_record.return_value = {
        "success": False,
        "code": "BLACKROOM_CHECK_FAILED",
        "message": "check failed",
        "data": None,
    }
```

Change the final assertions to:

```python
    blackroom_service.get_active_record.assert_called_once_with("000001", "A")
    blackroom_service.ban.assert_not_called()
```

In `test_sync_stops_and_propagates_when_add_fails(...)`, change:

```python
    blackroom_service.is_banned.return_value = {
        "success": True,
        "code": "OK",
        "message": "",
        "data": {"banned": False},
    }
```

to:

```python
    blackroom_service.get_active_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "",
        "data": None,
    }
```

Change that test's final assertions to:

```python
    blackroom_service.get_active_record.assert_called_once_with("000001", "A")
    blackroom_service.ban.assert_called_once_with(
        stock_code="000001",
        market="A",
        ban_days=30,
        start_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        source="shareholder_selling",
        note="股东减持公告 20250103 / 股东C",
    )
```

- [ ] **Step 5: Add reset failure and invalid announcement date tests**

Append these tests to `test/monitor/test_shareholder_selling_punishment.py`:

```python
def test_sync_stops_and_propagates_when_reset_fails(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [{"ts_code": "000001.SZ", "ann_date": "20250103", "holder_name": "股东C"}]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.get_active_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "",
        "data": {"id": 5, "stock_code": "000001", "market": "A"},
    }
    blackroom_service.update_record.return_value = {
        "success": False,
        "code": "BLACKROOM_UPDATE_FAILED",
        "message": "update failed",
        "data": None,
    }
    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result == {
        "success": False,
        "code": "BLACKROOM_UPDATE_FAILED",
        "message": "update failed",
        "data": None,
    }
    blackroom_service.update_record.assert_called_once_with(
        5,
        start_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
        ban_days=30,
        remaining_days=30,
        source="shareholder_selling",
        note="股东减持公告 20250103 / 股东C",
    )
    blackroom_service.ban.assert_not_called()


def test_sync_rejects_invalid_announcement_date(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "token")

    pro_client = MagicMock()
    pro_client.stk_holdertrade.return_value = pd.DataFrame(
        [{"ts_code": "000001.SZ", "ann_date": "2025-01-03", "holder_name": "股东C"}]
    )
    _install_tushare_stub(monkeypatch, MagicMock(return_value=pro_client))

    blackroom_service = MagicMock()
    blackroom_service.get_active_record.return_value = {
        "success": True,
        "code": "OK",
        "message": "",
        "data": None,
    }
    service = ShareholderSellingPunishmentService(blackroom_service=blackroom_service)

    result = service.sync(start_date="20250101", end_date="20250131", ban_days=30)

    assert result["success"] is False
    assert result["code"] == "VALIDATION_ERROR"
    assert "ann_date" in result["message"]
    blackroom_service.ban.assert_not_called()
    blackroom_service.update_record.assert_not_called()
```

- [ ] **Step 6: Run tests to verify they fail for implementation reasons**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py -v
```

Expected: FAIL because `ShareholderSellingPunishmentService` still calls `is_banned(...)`, does not pass `start_at`, does not reset existing records, and does not return `reset` counts.

- [ ] **Step 7: Commit**

Only commit if the user explicitly requested commits. If committing is allowed, run:

```bash
git add test/monitor/test_shareholder_selling_punishment.py
git commit -m "test: cover shareholder selling ban reset"
```

---

### Task 3: Implement shareholder-selling create-or-reset behavior

**Files:**
- Modify: `monitor/shareholder_selling_punishment.py`

- [ ] **Step 1: Update imports**

In `monitor/shareholder_selling_punishment.py`, change:

```python
from datetime import datetime
```

to:

```python
from datetime import datetime, timezone
```

- [ ] **Step 2: Replace the sync loop counters and active-ban branch**

Inside `sync(...)`, replace the current counter setup:

```python
            added = 0
            skipped = 0
            records: list[dict[str, Any]] = []
```

with:

```python
            added = 0
            reset = 0
            skipped = 0
            records: list[dict[str, Any]] = []
```

Then replace the entire per-row block from:

```python
                check_result = self.blackroom_service.is_banned(stock_code, market)
                if not check_result.get("success"):
                    return self._propagate_failure(
                        check_result,
                        default_code="BLACKROOM_CHECK_FAILED",
                        default_message="blackroom check failed",
                    )
                banned = bool((check_result.get("data") or {}).get("banned"))
                if banned:
                    skipped += 1
                    continue

                note = f"股东减持公告 {ann_date} / {holder_name}"
                add_result = self.blackroom_service.ban(
                    stock_code=stock_code,
                    market=market,
                    ban_days=ban_days,
                    source="shareholder_selling",
                    note=note,
                )
                if not add_result.get("success"):
                    return self._propagate_failure(
                        add_result,
                        default_code="BLACKROOM_ADD_FAILED",
                        default_message="blackroom add failed",
                    )
                added += 1
                records.append(
                    {
                        "stock_code": stock_code,
                        "market": market,
                        "ann_date": ann_date,
                        "holder_name": holder_name,
                    }
                )
```

with:

```python
                try:
                    announcement_start = self._parse_announcement_date(ann_date)
                except ValueError as exc:
                    return self._result(False, "VALIDATION_ERROR", str(exc), None)
                note = f"股东减持公告 {ann_date} / {holder_name}"

                active_result = self.blackroom_service.get_active_record(stock_code, market)
                if not active_result.get("success"):
                    return self._propagate_failure(
                        active_result,
                        default_code="BLACKROOM_CHECK_FAILED",
                        default_message="blackroom check failed",
                    )

                active_record = active_result.get("data")
                if active_record:
                    record_id = active_record.get("id")
                    update_result = self.blackroom_service.update_record(
                        record_id,
                        start_at=announcement_start,
                        ban_days=ban_days,
                        remaining_days=ban_days,
                        source="shareholder_selling",
                        note=note,
                    )
                    if not update_result.get("success"):
                        return self._propagate_failure(
                            update_result,
                            default_code="BLACKROOM_UPDATE_FAILED",
                            default_message="blackroom update failed",
                        )
                    reset += 1
                    action = "reset"
                else:
                    add_result = self.blackroom_service.ban(
                        stock_code=stock_code,
                        market=market,
                        ban_days=ban_days,
                        start_at=announcement_start,
                        source="shareholder_selling",
                        note=note,
                    )
                    if not add_result.get("success"):
                        return self._propagate_failure(
                            add_result,
                            default_code="BLACKROOM_ADD_FAILED",
                            default_message="blackroom add failed",
                        )
                    added += 1
                    action = "added"

                records.append(
                    {
                        "stock_code": stock_code,
                        "market": market,
                        "ann_date": ann_date,
                        "holder_name": holder_name,
                        "action": action,
                    }
                )
```

- [ ] **Step 3: Include `reset` in the result data**

In the success return `data` dict, change:

```python
                    "added": added,
                    "skipped": skipped,
                    "records": records,
```

to:

```python
                    "added": added,
                    "reset": reset,
                    "skipped": skipped,
                    "records": records,
```

- [ ] **Step 4: Add announcement-date parser**

Add this class method after `_validate_date(...)`:

```python
    @classmethod
    def _parse_announcement_date(cls, value: Any) -> datetime:
        try:
            cls._validate_date(value, "ann_date")
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        parsed = datetime.strptime(value, "%Y%m%d")
        return parsed.replace(tzinfo=timezone.utc)
```

- [ ] **Step 5: Keep latest announcement row when deduplicating stocks**

Replace `_build_unique_rows(...)` with:

```python
    def _build_unique_rows(self, data: Any) -> list[dict[str, Any]]:
        if data is None or getattr(data, "empty", False):
            return []

        rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        order: list[tuple[str, str]] = []
        for row in data.to_dict("records"):
            stock_code, market = self._normalize_ts_code(row.get("ts_code"))
            key = (stock_code, market)
            normalized_row = {
                "stock_code": stock_code,
                "market": market,
                "ann_date": str(row.get("ann_date") or ""),
                "holder_name": str(row.get("holder_name") or ""),
            }
            if key not in rows_by_key:
                rows_by_key[key] = normalized_row
                order.append(key)
                continue
            if normalized_row["ann_date"] > rows_by_key[key]["ann_date"]:
                rows_by_key[key] = normalized_row

        return [rows_by_key[key] for key in order]
```

- [ ] **Step 6: Run focused shareholder-selling tests**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py -v
```

Expected: PASS.

- [ ] **Step 7: Run blackroom service tests**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_service.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Only commit if the user explicitly requested commits. If committing is allowed, run:

```bash
git add monitor/shareholder_selling_punishment.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py monitor/blackroom_service.py
git commit -m "feat: reset blackroom bans on shareholder selling"
```

---

### Task 4: Final verification and documentation check

**Files:**
- Read/inspect: `docs/superpowers/specs/2026-06-10-blackroom-shareholder-selling-reset-design.md`
- Inspect git diff for all touched files

- [ ] **Step 1: Run focused tests**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py -v
```

Expected: PASS.

- [ ] **Step 2: Run formatting on touched Python files**

Run:

```bash
poetry run black monitor/shareholder_selling_punishment.py monitor/blackroom_service.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py
```

Expected: `All done!` or files reformatted successfully.

- [ ] **Step 3: Run import sorting on touched Python files**

Run:

```bash
poetry run isort monitor/shareholder_selling_punishment.py monitor/blackroom_service.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py
```

Expected: command exits 0.

- [ ] **Step 4: Re-run focused tests after formatting**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Inspect diff for unintended changes**

Run:

```bash
git diff -- monitor/shareholder_selling_punishment.py monitor/blackroom_service.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py docs/superpowers/specs/2026-06-10-blackroom-shareholder-selling-reset-design.md docs/superpowers/plans/2026-06-10-blackroom-shareholder-selling-reset.md
```

Expected: diff only contains approved shareholder-selling reset behavior, tests, spec, and this plan.

- [ ] **Step 6: Commit final state**

Only commit if the user explicitly requested commits. If committing is allowed, run:

```bash
git add monitor/shareholder_selling_punishment.py monitor/blackroom_service.py test/monitor/test_shareholder_selling_punishment.py test/monitor/test_blackroom_service.py docs/superpowers/specs/2026-06-10-blackroom-shareholder-selling-reset-design.md docs/superpowers/plans/2026-06-10-blackroom-shareholder-selling-reset.md
git commit -m "feat: reset shareholder selling blackroom bans"
```
