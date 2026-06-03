# Blackroom Countdown Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor blackroom from CRUD/expire-at management into business-named ban/unban services backed by remaining-day countdown semantics.

**Architecture:** Keep persistence operations in `storage/storage_db.py`, introduce `BlackroomService` as the business API, add `BlackroomCountdownService` for daily decrement/delete, and make shareholder-selling sync call the blackroom business API. Preserve compatibility aliases and old CLI commands while adding business-named commands.

**Tech Stack:** Python 3.11+, SQLAlchemy ORM, argparse CLI, pytest, Poetry. All project Python/test commands must use `poetry run`.

**Execution precondition:** Before implementation, create an isolated git worktree via `superpowers:using-git-worktrees`. Do not implement this plan directly in the current `/data/frog` checkout.

---

## File Structure

- Modify: `storage/model/blackroom_record.py` — add `remaining_days` column.
- Modify: `storage/storage_db.py` — create/list/update/delete active blackroom records using `remaining_days`; add stock-level delete and countdown helpers.
- Create: `monitor/validation.py` — shared validators for stock code, market, positive int, bool, datetime, and YYYYMMDD ranges.
- Create: `monitor/blackroom_service.py` — business-named service with stable `{success, code, message, data}` payloads.
- Modify: `monitor/blackroom_management_service.py` — compatibility shim exporting `BlackroomManagementService` as a subclass/alias of `BlackroomService`.
- Create: `monitor/blackroom_countdown.py` — service that runs countdown and returns stable payloads.
- Modify: `monitor/shareholder_selling_punishment.py` — keep `ShareholderSellingPunishmentService` as the sync service name and route it through `BlackroomService`.
- Modify: `tools/stock_monitor_cli.py` — import new service names, add `ban`, `unban`, `countdown`, and `sync-shareholder-selling` wiring while preserving old commands.
- Modify: `test/storage/test_blackroom_storage_db.py` — update active semantics and add countdown/storage deletion tests.
- Create: `test/monitor/test_blackroom_service.py` — new business service tests.
- Create: `test/monitor/test_blackroom_countdown.py` — countdown service tests.
- Modify: `test/monitor/test_blackroom_management_service.py` — reduce to compatibility coverage or update imports to new service.
- Modify: `test/monitor/test_shareholder_selling_punishment.py` if present, otherwise add focused tests in a new file for the renamed sync service.
- Modify: `test/tools/test_stock_monitor_cli.py` — new business command tests plus old command compatibility assertions.
- Modify: `docs/superpowers/specs/2026-06-01-blackroom-countdown-refactor-design.md` only if implementation reveals a spec correction is necessary.

## Task 0: Create Worktree Before Any Code Changes

**Files:** none in the implementation worktree yet.

- [ ] **Step 1: Invoke required worktree skill**

Use `superpowers:using-git-worktrees` before touching code. The worktree should be created from the current branch with a descriptive name such as `blackroom-countdown-refactor`.

- [ ] **Step 2: Verify worktree location**

Run from the new worktree root:

```bash
git --no-pager status --short
```

Expected: no unrelated tracked modifications in the implementation worktree. Untracked docs from the planning checkout do not need to be present unless deliberately copied.

## Task 1: Add Shared Monitor Validators

**Files:**
- Create: `monitor/validation.py`
- Test: `test/monitor/test_validation.py`

- [ ] **Step 1: Write failing validator tests**

Create `test/monitor/test_validation.py`:

```python
from datetime import datetime, timezone

import pytest

from monitor.validation import (
    validate_bool,
    validate_date_range,
    validate_datetime_or_none,
    validate_market,
    validate_positive_int,
    validate_stock_code,
    validate_yyyymmdd,
)


def test_validate_positive_int_rejects_bool_zero_and_negative():
    for value in (True, 0, -1, "1"):
        with pytest.raises(ValueError, match="days 必须是正整数"):
            validate_positive_int(value, "days")


def test_validate_bool_rejects_non_bool():
    with pytest.raises(ValueError, match="enabled 必须是布尔值"):
        validate_bool(1, "enabled")


def test_validate_stock_code_rejects_blank():
    with pytest.raises(ValueError, match="stock_code 不能为空"):
        validate_stock_code("  ")


def test_validate_market_uses_allowed_values():
    validate_market("A", {"A", "HK", "ETF"})
    with pytest.raises(ValueError, match="market 必须是"):
        validate_market("US", {"A", "HK", "ETF"})


def test_validate_datetime_or_none():
    validate_datetime_or_none(None, "start_at")
    validate_datetime_or_none(datetime(2026, 1, 1, tzinfo=timezone.utc), "start_at")
    with pytest.raises(ValueError, match="start_at 必须是 datetime 或 None"):
        validate_datetime_or_none("20260101", "start_at")


def test_validate_yyyymmdd_rejects_bad_dates():
    validate_yyyymmdd("20260131", "start_date")
    with pytest.raises(ValueError, match="start_date 必须是 YYYYMMDD 格式"):
        validate_yyyymmdd("2026-01-31", "start_date")
    with pytest.raises(ValueError):
        validate_yyyymmdd("20260231", "start_date")


def test_validate_date_range_rejects_reversed_range():
    validate_date_range("20260101", "20260131")
    with pytest.raises(ValueError, match="start_date 不能晚于 end_date"):
        validate_date_range("20260201", "20260131")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
poetry run pytest test/monitor/test_validation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'monitor.validation'`.

- [ ] **Step 3: Implement validators**

Create `monitor/validation.py`:

```python
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Collection

_YYYYMMDD_PATTERN = re.compile(r"^\d{8}$")


def validate_positive_int(value: Any, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} 必须是正整数")


def validate_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} 必须是布尔值")


def validate_stock_code(stock_code: Any) -> None:
    if not isinstance(stock_code, str) or not stock_code.strip():
        raise ValueError("stock_code 不能为空")


def validate_market(market: Any, allowed_markets: Collection[str]) -> None:
    if not isinstance(market, str) or market not in allowed_markets:
        raise ValueError(f"market 必须是 {sorted(allowed_markets)} 之一")


def validate_datetime_or_none(value: Any, field_name: str) -> None:
    if value is not None and not isinstance(value, datetime):
        raise ValueError(f"{field_name} 必须是 datetime 或 None")


def validate_yyyymmdd(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not _YYYYMMDD_PATTERN.match(value):
        raise ValueError(f"{field_name} 必须是 YYYYMMDD 格式")
    datetime.strptime(value, "%Y%m%d")


def validate_date_range(start_date: Any, end_date: Any) -> None:
    validate_yyyymmdd(start_date, "start_date")
    validate_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
poetry run pytest test/monitor/test_validation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit if commits are authorized**

If the user has explicitly authorized commits for implementation, run:

```bash
git add monitor/validation.py test/monitor/test_validation.py
git commit -m "refactor: add shared monitor validators"
```

If commits are not authorized, skip this step and continue with unstaged changes.

## Task 2: Change Storage to Remaining-Day Semantics

**Files:**
- Modify: `storage/model/blackroom_record.py`
- Modify: `storage/storage_db.py`
- Modify: `test/storage/test_blackroom_storage_db.py`

- [ ] **Step 1: Add failing model/storage tests**

Update `test/storage/test_blackroom_storage_db.py`:

```python
def test_blackroom_record_has_remaining_days_field():
    from storage.model import BlackroomRecord

    columns = {c.name for c in BlackroomRecord.__table__.columns}
    assert "remaining_days" in columns


def test_create_initializes_remaining_days_from_ban_days(sqlite_storage):
    db = sqlite_storage

    record = db.create_blackroom_record(stock_code="000001", ban_days=15)

    assert record.ban_days == 15
    assert record.remaining_days == 15


def test_active_records_use_remaining_days_not_expire_at(sqlite_storage):
    db = sqlite_storage
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    db.create_blackroom_record(stock_code="000001", enabled=True, ban_days=5, expire_at=past)
    db.create_blackroom_record(stock_code="000002", enabled=True, ban_days=0, remaining_days=0, expire_at=future)
    db.create_blackroom_record(stock_code="000003", enabled=False, ban_days=5, expire_at=future)

    active = db.list_active_blackroom_records()

    assert [r.stock_code for r in active] == ["000001"]


def test_delete_blackroom_records_by_stock(sqlite_storage):
    db = sqlite_storage
    db.create_blackroom_record(stock_code="000001", market="A", ban_days=5)
    db.create_blackroom_record(stock_code="000001", market="A", ban_days=10)
    db.create_blackroom_record(stock_code="000001", market="HK", ban_days=5)

    deleted = db.delete_blackroom_records_by_stock("000001", "A")

    assert deleted == 2
    assert [r.market for r in db.list_blackroom_records()] == ["HK"]


def test_countdown_decrements_and_deletes_expired(sqlite_storage):
    db = sqlite_storage
    db.create_blackroom_record(stock_code="000001", ban_days=2)
    db.create_blackroom_record(stock_code="000002", ban_days=1)
    db.create_blackroom_record(stock_code="000003", ban_days=3, enabled=False)

    result = db.countdown_blackroom_records()

    records = db.list_blackroom_records()

    assert result == {"decremented": 2, "deleted": 1}
    assert [(r.stock_code, r.remaining_days) for r in records] == [("000001", 1), ("000003", 3)]
```

Also update existing active tests in `TestListActiveBlackroomRecords` so they pass `ban_days`/`remaining_days` instead of relying on future `expire_at`.

- [ ] **Step 2: Run storage tests to verify failure**

Run:

```bash
poetry run pytest test/storage/test_blackroom_storage_db.py -q
```

Expected: FAIL because `remaining_days`, `delete_blackroom_records_by_stock`, and `countdown_blackroom_records` do not exist.

- [ ] **Step 3: Add model field**

Modify `storage/model/blackroom_record.py` to include:

```python
    remaining_days = Column(
        Integer,
        nullable=True,
        comment="剩余禁买天数；大于 0 表示仍处于倒计时封禁期",
    )
```

Place it immediately after `ban_days`.

- [ ] **Step 4: Update storage create/update/list/delete/countdown methods**

Modify `storage/storage_db.py` blackroom methods with these semantics:

```python
    def create_blackroom_record(
        self,
        stock_code: str,
        market: str = "A",
        ban_days: Optional[int] = None,
        remaining_days: Optional[int] = None,
        start_at: Optional[datetime] = None,
        expire_at: Optional[datetime] = None,
        source: str = "manual",
        note: Optional[str] = None,
        enabled: bool = True,
    ) -> Any:
        from .model.blackroom_record import BlackroomRecord

        effective_start = start_at or datetime.now(timezone.utc)
        if remaining_days is None:
            remaining_days = ban_days
        if expire_at is None and ban_days is not None:
            expire_at = effective_start + timedelta(days=ban_days)

        assert self.Session is not None
        session = self.Session()
        try:
            record = BlackroomRecord(
                stock_code=stock_code,
                market=market,
                ban_days=ban_days,
                remaining_days=remaining_days,
                start_at=effective_start,
                expire_at=expire_at,
                source=source,
                note=note,
                enabled=enabled,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

Update allowed fields in `update_blackroom_record` to include `remaining_days`. If `ban_days` is updated and `remaining_days` is not explicitly supplied, reset `remaining_days` to the new `ban_days`.

Replace `list_active_blackroom_records` filter with:

```python
            query = (
                session.query(BlackroomRecord)
                .filter_by(enabled=True)
                .filter(BlackroomRecord.remaining_days > 0)
            )
```

Add:

```python
    def delete_blackroom_records_by_stock(self, stock_code: str, market: str) -> int:
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            records = session.query(BlackroomRecord).filter_by(stock_code=stock_code, market=market).all()
            deleted = len(records)
            for record in records:
                session.delete(record)
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def countdown_blackroom_records(self) -> dict[str, int]:
        from .model.blackroom_record import BlackroomRecord

        assert self.Session is not None
        session = self.Session()
        try:
            records = (
                session.query(BlackroomRecord)
                .filter_by(enabled=True)
                .filter(BlackroomRecord.remaining_days > 0)
                .order_by(BlackroomRecord.id.asc())
                .all()
            )
            decremented = len(records)
            for record in records:
                record.remaining_days = int(record.remaining_days or 0) - 1
            expired = [record for record in records if int(record.remaining_days or 0) <= 0]
            deleted = len(expired)
            for record in expired:
                session.delete(record)
            session.commit()
            return {"decremented": decremented, "deleted": deleted}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 5: Run storage tests**

Run:

```bash
poetry run pytest test/storage/test_blackroom_storage_db.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit if commits are authorized**

```bash
git add storage/model/blackroom_record.py storage/storage_db.py test/storage/test_blackroom_storage_db.py
git commit -m "refactor: use remaining days for blackroom storage"
```

## Task 3: Introduce BlackroomService and Compatibility Shim

**Files:**
- Create: `monitor/blackroom_service.py`
- Modify: `monitor/blackroom_management_service.py`
- Create: `test/monitor/test_blackroom_service.py`
- Modify: `test/monitor/test_blackroom_management_service.py`

- [ ] **Step 1: Write failing BlackroomService tests**

Create `test/monitor/test_blackroom_service.py` with focused coverage:

```python
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from monitor.blackroom_service import BlackroomService
from monitor.blackroom_management_service import BlackroomManagementService


def _record(**overrides):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = {
        "id": 1,
        "stock_code": "600519",
        "market": "A",
        "ban_days": 30,
        "remaining_days": 30,
        "start_at": now,
        "expire_at": now + timedelta(days=30),
        "source": "manual",
        "note": "note",
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_ban_creates_record_with_remaining_days():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _record()
    service = BlackroomService(storage=storage)

    result = service.ban("600519", "A", 30, note="note")

    assert result["success"] is True
    assert result["data"]["remaining_days"] == 30
    _, kwargs = storage.create_blackroom_record.call_args
    assert kwargs["ban_days"] == 30
    assert kwargs["remaining_days"] == 30


def test_unban_deletes_by_record_id():
    storage = MagicMock()
    storage.delete_blackroom_record.return_value = True
    result = BlackroomService(storage=storage).unban(7)
    assert result == {"success": True, "code": "OK", "message": "record unbanned", "data": {"id": 7, "deleted": True}}


def test_unban_stock_deletes_by_stock_and_market():
    storage = MagicMock()
    storage.delete_blackroom_records_by_stock.return_value = 2
    result = BlackroomService(storage=storage).unban_stock("600519", "A")
    assert result["success"] is True
    assert result["data"] == {"stock_code": "600519", "market": "A", "deleted": 2}


def test_is_banned_uses_active_records():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="600519")]
    result = BlackroomService(storage=storage).is_banned("600519", "A")
    assert result["data"]["banned"] is True


def test_filter_buy_candidates_splits_allowed_and_banned():
    storage = MagicMock()
    storage.list_active_blackroom_records.return_value = [_record(stock_code="600519")]
    result = BlackroomService(storage=storage).filter_buy_candidates(["600519", "000001"], "A")
    assert result["data"] == {"allowed": ["000001"], "banned": ["600519"]}


def test_compatibility_class_still_exposes_old_add_name():
    storage = MagicMock()
    storage.create_blackroom_record.return_value = _record()
    service = BlackroomManagementService(storage=storage)
    result = service.add_record("600519", "A", 30)
    assert result["success"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_service.py -q
```

Expected: FAIL with missing `monitor.blackroom_service`.

- [ ] **Step 3: Implement BlackroomService**

Create `monitor/blackroom_service.py` by moving current logic from `monitor/blackroom_management_service.py` and changing public names:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from monitor.validation import (
    validate_bool,
    validate_datetime_or_none,
    validate_market,
    validate_positive_int,
    validate_stock_code,
)
from storage import get_storage


class BlackroomValidationError(ValueError):
    """Raised when blackroom record input is invalid."""


class BlackroomNotFoundError(LookupError):
    """Raised when a blackroom record cannot be found."""


class BlackroomService:
    _ALLOWED_MARKETS = {"A", "HK", "ETF"}
    _ALLOWED_SOURCES = {"manual", "shareholder_selling", "shareholder_reduction"}
    _ALLOWED_UPDATE_FIELDS = {
        "stock_code", "market", "ban_days", "remaining_days", "start_at", "expire_at", "source", "note", "enabled",
    }

    def __init__(self, storage: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage

    def ban(self, stock_code: str, market: str, ban_days: int, start_at: Optional[datetime] = None,
            source: str = "manual", note: Optional[str] = None, enabled: bool = True) -> dict[str, Any]:
        try:
            self._validate_stock_code(stock_code)
            self._validate_market(market)
            self._validate_source(source)
            self._validate_ban_days(ban_days)
            self._validate_bool(enabled, "enabled")
            validate_datetime_or_none(start_at, "start_at")
            effective_start = start_at if start_at is not None else datetime.now(timezone.utc)
            record = self.storage.create_blackroom_record(
                stock_code=stock_code, market=market, ban_days=ban_days, remaining_days=ban_days,
                start_at=effective_start, source=source, note=note, enabled=enabled,
            )
            return self._result(True, "OK", "record banned", self._serialize(record))
        except (BlackroomValidationError, ValueError) as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except Exception as exc:
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    def unban(self, record_id: int) -> dict[str, Any]:
        try:
            self._validate_record_id(record_id)
            deleted = self.storage.delete_blackroom_record(record_id)
            if not deleted:
                raise BlackroomNotFoundError(f"blackroom record not found: {record_id}")
            return self._result(True, "OK", "record unbanned", {"id": record_id, "deleted": True})
        except (BlackroomValidationError, ValueError) as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except BlackroomNotFoundError as exc:
            return self._result(False, "NOT_FOUND", str(exc), None)
        except Exception as exc:
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    def unban_stock(self, stock_code: str, market: str) -> dict[str, Any]:
        try:
            self._validate_stock_code(stock_code)
            self._validate_market(market)
            deleted = self.storage.delete_blackroom_records_by_stock(stock_code, market)
            return self._result(True, "OK", "stock unbanned", {"stock_code": stock_code, "market": market, "deleted": deleted})
        except (BlackroomValidationError, ValueError) as exc:
            return self._result(False, "VALIDATION_ERROR", str(exc), None)
        except Exception as exc:
            return self._result(False, "STORAGE_ERROR", str(exc), None)
```

Then copy/adapt the existing `get_record`, `list_records`, `update_record`, `filter_buy_candidates`, `is_buy_banned`, aliases, `get_status`, `_result`, `_serialize`, and `_to_iso` methods from `BlackroomManagementService`. Add `remaining_days` to `_serialize`. Ensure aliases map as follows:

```python
    def add_record(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.ban(*args, **kwargs)

    def remove_record(self, record_id: int) -> dict[str, Any]:
        return self.unban(record_id)

    def add(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.ban(*args, **kwargs)

    def remove(self, record_id: int) -> dict[str, Any]:
        return self.unban(record_id)

    def check(self, stock_code: str, market: str) -> dict[str, Any]:
        return self.is_banned(stock_code, market)

    def filter(self, candidates: List[str], market: str) -> dict[str, Any]:
        return self.filter_buy_candidates(candidates, market)
```

- [ ] **Step 4: Replace management service with compatibility shim**

Replace `monitor/blackroom_management_service.py` with:

```python
"""Compatibility wrapper for the renamed blackroom business service."""

from __future__ import annotations

from monitor.blackroom_service import (
    BlackroomNotFoundError,
    BlackroomService,
    BlackroomValidationError,
)


class BlackroomManagementService(BlackroomService):
    """Backward-compatible name for BlackroomService."""
```

- [ ] **Step 5: Run blackroom service tests**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_service.py test/monitor/test_blackroom_management_service.py -q
```

Expected: PASS after updating old tests for message changes where needed (`record created` may become `record banned`).

- [ ] **Step 6: Commit if commits are authorized**

```bash
git add monitor/blackroom_service.py monitor/blackroom_management_service.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_management_service.py
git commit -m "refactor: introduce blackroom business service"
```

## Task 4: Add BlackroomCountdownService

**Files:**
- Create: `monitor/blackroom_countdown.py`
- Create: `test/monitor/test_blackroom_countdown.py`

- [ ] **Step 1: Write failing countdown service tests**

Create `test/monitor/test_blackroom_countdown.py`:

```python
from unittest.mock import MagicMock

from monitor.blackroom_countdown import BlackroomCountdownService


def test_run_returns_stable_payload():
    storage = MagicMock()
    storage.countdown_blackroom_records.return_value = {"decremented": 12, "deleted": 3}

    result = BlackroomCountdownService(storage=storage).run()

    assert result == {
        "success": True,
        "code": "OK",
        "message": "countdown completed",
        "data": {"decremented": 12, "deleted": 3},
    }


def test_run_maps_storage_exception_to_storage_error():
    storage = MagicMock()
    storage.countdown_blackroom_records.side_effect = RuntimeError("db down")

    result = BlackroomCountdownService(storage=storage).run()

    assert result["success"] is False
    assert result["code"] == "STORAGE_ERROR"
    assert "db down" in result["message"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_countdown.py -q
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement countdown service**

Create `monitor/blackroom_countdown.py`:

```python
from __future__ import annotations

from typing import Any

from storage import get_storage


class BlackroomCountdownService:
    def __init__(self, storage: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage

    def run(self) -> dict[str, Any]:
        try:
            data = self.storage.countdown_blackroom_records()
            return self._result(True, "OK", "countdown completed", data)
        except Exception as exc:
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    @staticmethod
    def _result(success: bool, code: str, message: str, data: Any) -> dict[str, Any]:
        return {"success": success, "code": code, "message": message, "data": data}
```

- [ ] **Step 4: Run countdown tests**

Run:

```bash
poetry run pytest test/monitor/test_blackroom_countdown.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit if commits are authorized**

```bash
git add monitor/blackroom_countdown.py test/monitor/test_blackroom_countdown.py
git commit -m "feat: add blackroom countdown service"
```

## Task 5: Rename Shareholder Selling Sync Boundary

**Files:**
- Modify: `monitor/shareholder_selling_punishment.py`
- Test: existing or new `test/monitor/test_shareholder_selling_punishment.py`

- [ ] **Step 1: Write failing sync boundary test**

If `test/monitor/test_shareholder_selling_punishment.py` exists, add this test there; otherwise create it:

```python
from unittest.mock import MagicMock

from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService


def test_only_new_sync_service_name_is_exported():
    bsvc = MagicMock()
    service = ShareholderSellingPunishmentService(blackroom_service=bsvc)
    assert service.blackroom_service is bsvc
```

Also update existing tests so mocked blackroom services expect `.ban(...)` instead of `.add(...)`, while `.check(...)` may remain as a compatibility alias or move to `.is_banned(...)`.

- [ ] **Step 2: Run sync tests to verify failure**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py -q
```

Expected: FAIL until the new class exists.

- [ ] **Step 3: Rename class with compatibility alias**

Modify `monitor/shareholder_selling_punishment.py`:

```python
from monitor.blackroom_service import BlackroomService


class ShareholderSellingPunishmentService:
    def __init__(self, blackroom_service: BlackroomService | None = None) -> None:
        self.blackroom_service = BlackroomService() if blackroom_service is None else blackroom_service
```

Inside `sync`, replace:

```python
check_result = self.blackroom_service.check(stock_code, market)
add_result = self.blackroom_service.add(...)
```

with:

```python
check_result = self.blackroom_service.is_banned(stock_code, market)
add_result = self.blackroom_service.ban(
    stock_code=stock_code,
    market=market,
    ban_days=ban_days,
    source="shareholder_selling",
    note=note,
)
```

The service should keep the single class name and not add a second compatibility alias:

```python
class ShareholderSellingPunishmentService:
    def __init__(self, blackroom_service: BlackroomService | None = None) -> None:
        self.blackroom_service = BlackroomService() if blackroom_service is None else blackroom_service
```

- [ ] **Step 4: Fix validation bug while touching file**

Change the existing reversed date message from `start_date 不echo end_date` to:

```python
raise ValueError("start_date 不能晚于 end_date")
```

- [ ] **Step 5: Run sync tests**

Run:

```bash
poetry run pytest test/monitor/test_shareholder_selling_punishment.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit if commits are authorized**

```bash
git add monitor/shareholder_selling_punishment.py test/monitor/test_shareholder_selling_punishment.py
git commit -m "refactor: rename shareholder selling blackroom sync service"
```

## Task 6: Add Business-Named CLI Commands and Preserve Old Commands

**Files:**
- Modify: `tools/stock_monitor_cli.py`
- Modify: `test/tools/test_stock_monitor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add to `test/tools/test_stock_monitor_cli.py`:

```python
def test_blackroom_ban_calls_business_service():
    bsvc = MagicMock()
    bsvc.ban.return_value = {"success": True, "code": "OK", "message": "record banned", "data": {"id": 1}}

    exit_code = main(["blackroom", "ban", "--stock-code", "600519", "--market", "A", "--ban-days", "30"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.ban.assert_called_once_with(stock_code="600519", market="A", ban_days=30, note=None)


def test_blackroom_unban_by_id_calls_business_service():
    bsvc = MagicMock()
    bsvc.unban.return_value = {"success": True, "code": "OK", "message": "record unbanned", "data": {"id": 4}}

    exit_code = main(["blackroom", "unban", "--id", "4"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.unban.assert_called_once_with(4)


def test_blackroom_unban_by_stock_calls_business_service():
    bsvc = MagicMock()
    bsvc.unban_stock.return_value = {"success": True, "code": "OK", "message": "stock unbanned", "data": {"deleted": 2}}

    exit_code = main(["blackroom", "unban", "--stock-code", "600519", "--market", "A"], blackroom_service=bsvc)

    assert exit_code == 0
    bsvc.unban_stock.assert_called_once_with("600519", "A")


def test_blackroom_countdown_calls_countdown_service():
    countdown_service = MagicMock()
    countdown_service.run.return_value = {"success": True, "code": "OK", "message": "countdown completed", "data": {"deleted": 1}}

    exit_code = main(["blackroom", "countdown"], countdown_service=countdown_service)

    assert exit_code == 0
    countdown_service.run.assert_called_once_with()
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```bash
poetry run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: FAIL because parser/main does not know `ban`, `unban`, `countdown`, or `countdown_service`.

- [ ] **Step 3: Update CLI imports and typing**

Modify imports in `tools/stock_monitor_cli.py`:

```python
from monitor.blackroom_countdown import BlackroomCountdownService
from monitor.blackroom_service import BlackroomService
from monitor.shareholder_selling_punishment import ShareholderSellingPunishmentService
```

Keep compatibility imports only if tests patch old names; otherwise patch tests to new names.

Update `main` signature:

```python
def main(
    argv: list[str] | None = None,
    service: MonitorTargetService | None = None,
    blackroom_service: BlackroomService | None = None,
    sync_service: ShareholderSellingPunishmentService | None = None,
    countdown_service: BlackroomCountdownService | None = None,
) -> int:
```

- [ ] **Step 4: Add parser commands**

In `build_parser`, add `ban` with the same args as `add`, add `unban`, and add `countdown`:

```python
    br_ban = blackroom_subparsers.add_parser("ban", help="封禁股票进入黑屋")
    br_ban.add_argument("--stock-code", required=True, help="股票代码")
    br_ban.add_argument("--market", required=True, help="市场，例如 A/HK/ETF")
    br_ban.add_argument("--ban-days", type=int, required=True, help="禁买天数")
    br_ban.add_argument("--note", default=None, help="备注")

    br_unban = blackroom_subparsers.add_parser("unban", help="解除黑屋封禁")
    br_unban.add_argument("--id", type=int, default=None, dest="record_id", help="记录ID")
    br_unban.add_argument("--stock-code", default=None, help="股票代码")
    br_unban.add_argument("--market", default=None, help="市场，例如 A/HK/ETF")

    blackroom_subparsers.add_parser("countdown", help="执行黑屋剩余天数倒计时")
```

- [ ] **Step 5: Wire handlers**

Update `_handle_blackroom` signature and logic:

```python
def _handle_blackroom(args, bsvc=None, sync_service=None, countdown_service=None):
    def _get_bsvc() -> BlackroomService:
        return bsvc or BlackroomService()

    if cmd in {"ban", "add"}:
        return _get_bsvc().ban(stock_code=args.stock_code, market=args.market, ban_days=args.ban_days, note=args.note)
    if cmd == "unban":
        if args.record_id is not None:
            return _get_bsvc().unban(args.record_id)
        if args.stock_code is not None and args.market is not None:
            return _get_bsvc().unban_stock(args.stock_code, args.market)
        return {"success": False, "code": "VALIDATION_ERROR", "message": "unban requires --id or both --stock-code and --market", "data": None}
    if cmd == "remove":
        return _get_bsvc().unban(args.record_id)
    if cmd == "countdown":
        svc = countdown_service or BlackroomCountdownService()
        return svc.run()
```

Change sync construction to use `ShareholderSellingPunishmentService(blackroom_service=_get_bsvc())`.

- [ ] **Step 6: Run CLI tests**

Run:

```bash
poetry run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS after updating old `add`/`remove` tests to assert `.ban`/`.unban` or keeping compatibility mocks that expose both names.

- [ ] **Step 7: Commit if commits are authorized**

```bash
git add tools/stock_monitor_cli.py test/tools/test_stock_monitor_cli.py
git commit -m "feat: add business blackroom CLI commands"
```

## Task 7: Run Focused Integration Checks and Update Docs if Needed

**Files:**
- Modify docs only if commands or behavior differ from the spec.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
poetry run pytest test/storage/test_blackroom_storage_db.py test/monitor/test_validation.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_countdown.py test/monitor/test_shareholder_selling_punishment.py test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Run formatting on touched Python files**

Run:

```bash
poetry run black monitor/validation.py monitor/blackroom_service.py monitor/blackroom_management_service.py monitor/blackroom_countdown.py monitor/shareholder_selling_punishment.py storage/model/blackroom_record.py storage/storage_db.py tools/stock_monitor_cli.py test/monitor/test_validation.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_countdown.py test/monitor/test_shareholder_selling_punishment.py test/storage/test_blackroom_storage_db.py test/tools/test_stock_monitor_cli.py
poetry run isort monitor/validation.py monitor/blackroom_service.py monitor/blackroom_management_service.py monitor/blackroom_countdown.py monitor/shareholder_selling_punishment.py storage/model/blackroom_record.py storage/storage_db.py tools/stock_monitor_cli.py test/monitor/test_validation.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_countdown.py test/monitor/test_shareholder_selling_punishment.py test/storage/test_blackroom_storage_db.py test/tools/test_stock_monitor_cli.py
```

Expected: commands complete without errors.

- [ ] **Step 3: Run focused tests again after formatting**

Run:

```bash
poetry run pytest test/storage/test_blackroom_storage_db.py test/monitor/test_validation.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_countdown.py test/monitor/test_shareholder_selling_punishment.py test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Inspect docs impact with update_doc skill**

Invoke `update_doc`. If CLI user-facing command docs exist for stock monitor blackroom commands, update them to mention `ban`, `unban`, and `countdown` plus old command compatibility. If no dedicated docs exist, report that no additional docs were required beyond the spec/plan.

- [ ] **Step 5: Final repository checks before claiming completion**

Invoke `verification-before-completion`, then run at minimum:

```bash
poetry run pytest test/storage/test_blackroom_storage_db.py test/monitor/test_validation.py test/monitor/test_blackroom_service.py test/monitor/test_blackroom_countdown.py test/monitor/test_shareholder_selling_punishment.py test/tools/test_stock_monitor_cli.py -q
git --no-pager status --short
```

Expected: focused tests PASS; git status contains only intended files.

- [ ] **Step 6: Commit if commits are authorized**

```bash
git add docs tools monitor storage test
git commit -m "test: verify blackroom countdown refactor"
```

Skip this step unless the user explicitly authorized commits.

## Self-Review

### Spec coverage

- `BlackroomService` business naming: Tasks 3 and 6.
- `remaining_days` model and active semantics: Task 2.
- `BlackroomCountdownService`: Task 4.
- Storage-owned DB operations: Task 2.
- Shared validation: Task 1.
- Shareholder selling service boundary: Task 5.
- CLI command migration and compatibility: Task 6.
- Testing and docs verification: Task 7.

### Placeholder scan

No placeholder markers or open-ended implementation instructions are intentionally left in this plan. Each task includes concrete files, tests, commands, and expected outcomes.

### Type consistency

The plan consistently uses `BlackroomService`, `BlackroomCountdownService`, `ShareholderSellingPunishmentService`, `remaining_days`, `ban`, `unban`, `unban_stock`, `is_banned`, and `filter_buy_candidates` across tasks.
