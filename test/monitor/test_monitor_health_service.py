from datetime import datetime, timezone
from types import SimpleNamespace

from monitor.domain_enums import MonitorEvaluationErrorKind
from monitor.monitor_health import MONITOR_ERROR_SUMMARIES
from monitor.monitor_health_service import MonitorOperationalState, MonitorTargetHealthService


def _target(target_id: int, **updates: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": target_id,
        "stock_code": "600519",
        "market": "A",
        "frequency": "daily",
        "workflow": "scheduled",
        "enabled": True,
        "paused": False,
        "last_state": False,
        "last_checked_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "triggered_at": None,
        "latest_error_kind": None,
        "latest_error_detail": None,
        "latest_error_at": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


class FakeStorage:
    def __init__(self, targets: list[SimpleNamespace]):
        self.targets = targets

    def list_monitor_target_health(self) -> list[SimpleNamespace]:
        return self.targets

    def list_monitor_target_health_page(self, *, page: int, page_size: int) -> tuple[list[SimpleNamespace], int]:
        start = (page - 1) * page_size
        return self.targets[start : start + page_size], len(self.targets)


def test_get_health_derives_states_summary_and_safe_target_fields():
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(1, enabled=False, paused=True, last_state=True),
                _target(2, enabled=True, paused=True, last_state=False),
                _target(3, enabled=True, paused=False, last_state=False, frequency="intraday"),
            ]
        )
    )

    health = service.get_health()

    assert [target["operational_state"] for target in health["items"]] == [
        MonitorOperationalState.DISABLED,
        MonitorOperationalState.PAUSED,
        MonitorOperationalState.RUNNING,
    ]
    assert health["summary"] == {
        "total": 3,
        "running": 1,
        "paused": 1,
        "disabled": 1,
        "triggered": 1,
        "daily": 2,
        "intraday": 1,
    }
    assert health["items"][0]["workflow"] == "scheduled"
    assert {"condition", "note", "evidence"}.isdisjoint(health["items"][0])
    assert health["page"] == 1
    assert health["page_size"] == 50
    assert health["total_count"] == 3
    assert health["total_pages"] == 1
    assert "targets" not in health


def test_get_health_serializes_valid_and_corrupt_latest_errors():
    occurred_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(1),
                _target(
                    2,
                    latest_error_kind=MonitorEvaluationErrorKind.MARKET_DATA.value,
                    latest_error_detail="provider timed out",
                    latest_error_at=occurred_at,
                ),
                _target(
                    3,
                    latest_error_kind="corrupt",
                    latest_error_detail="must not be exposed",
                    latest_error_at=occurred_at,
                ),
            ]
        )
    )

    targets = service.get_health()["items"]

    assert targets[0]["latest_error"] is None
    assert targets[1]["latest_error"] == {
        "kind": MonitorEvaluationErrorKind.MARKET_DATA,
        "summary": MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.MARKET_DATA],
        "detail": "provider timed out",
        "occurred_at": occurred_at,
    }
    assert targets[2]["latest_error"] == {
        "kind": MonitorEvaluationErrorKind.UNKNOWN,
        "summary": MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.UNKNOWN],
        "detail": None,
        "occurred_at": occurred_at,
    }


def test_get_health_resanitizes_legacy_sensitive_valid_error_detail():
    occurred_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    service = MonitorTargetHealthService(
        storage=FakeStorage(
            [
                _target(
                    1,
                    latest_error_kind="storage",
                    latest_error_detail="ValueError: X-Api-Key: leaked https://example.com/x#fragment /srv/frog/a.py",
                    latest_error_at=occurred_at,
                )
            ]
        )
    )

    error = service.get_health()["items"][0]["latest_error"]
    assert error["kind"] == MonitorEvaluationErrorKind.STORAGE
    assert error["summary"] == MONITOR_ERROR_SUMMARIES[MonitorEvaluationErrorKind.STORAGE]
    for sensitive in ("ValueError:", "leaked", "example.com", "fragment", "/srv/frog/a.py"):
        assert sensitive not in (error["detail"] or "")


def test_health_summary_is_not_limited_to_the_current_page():
    service = MonitorTargetHealthService(storage=FakeStorage([_target(1), _target(2, enabled=False, last_state=True)]))

    health = service.get_health(page=2, page_size=1)

    assert health["summary"] == {
        "total": 2,
        "running": 1,
        "paused": 0,
        "disabled": 1,
        "triggered": 1,
        "daily": 2,
        "intraday": 0,
    }
    assert [target["id"] for target in health["items"]] == [2]
    assert health["page"] == 2
    assert health["page_size"] == 1
    assert health["total_count"] == 2
    assert health["total_pages"] == 2


def test_health_empty_results_return_first_page():
    health = MonitorTargetHealthService(storage=FakeStorage([])).get_health(page=4, page_size=5)

    assert health == {
        "summary": {"total": 0, "running": 0, "paused": 0, "disabled": 0, "triggered": 0, "daily": 0, "intraday": 0},
        "items": [],
        "page": 1,
        "page_size": 5,
        "total_count": 0,
        "total_pages": 0,
    }
